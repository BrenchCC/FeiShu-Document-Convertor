import json
import logging
import re

from typing import Any

from core.orchestration_planner import LlmResolution
from utils.http_client import HttpClient


logger = logging.getLogger(__name__)


class OpenAICompatibleLlmClient:
    """OpenAI-compatible chat completion client for TOC ambiguity fallback."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        http_client: HttpClient
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.http_client = http_client

    def is_ready(self) -> bool:
        """Check whether required config for LLM calls exists.

        Args:
            self: LLM client instance.
        """

        return bool(self.base_url and self.api_key and self.model)

    def resolve_toc_ambiguity(
        self,
        link_text: str,
        raw_target: str,
        candidate_paths: list[str],
        toc_context: str
    ) -> LlmResolution:
        """Resolve one TOC ambiguity using minimal structured prompt.

        Args:
            link_text: Link label text.
            raw_target: Raw markdown target text.
            candidate_paths: Candidate source-relative paths.
            toc_context: Nearby TOC context lines.
        """

        if not self.is_ready():
            return LlmResolution()
        if not candidate_paths:
            return LlmResolution()

        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        prompt_payload = {
            "link_text": link_text,
            "raw_target": raw_target,
            "candidate_paths": candidate_paths[:12],
            "toc_context": toc_context
        }

        try:
            response = self.http_client.request(
                method = "POST",
                url = endpoint,
                headers = {
                    "Authorization": f"Bearer {self.api_key}"
                },
                json_body = {
                    "model": self.model,
                    "temperature": 0,
                    "max_tokens": 120,
                    "response_format": {
                        "type": "json_object"
                    },
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Resolve markdown TOC link ambiguity. "
                                "Return strict JSON only: "
                                "{\"selected_path\":\"...\",\"confidence\":0.0,\"reason\":\"...\"}. "
                                "selected_path must be one of candidate_paths, or empty string if unsure."
                            )
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                prompt_payload,
                                ensure_ascii = False
                            )
                        }
                    ]
                }
            )
            payload = response.json()
        except Exception as exc:
            logger.warning("LLM request failed for TOC ambiguity: %s", str(exc))
            return LlmResolution()

        content = self._extract_message_content(payload = payload)
        if not content:
            return LlmResolution()

        parsed = self._parse_json_text(text = content)
        if not parsed:
            return LlmResolution()

        selected = str(parsed.get("selected_path", "")).strip()
        confidence = self._safe_float(parsed.get("confidence", 0.0))
        reason = str(parsed.get("reason", "")).strip()
        return LlmResolution(
            selected_path = selected,
            confidence = confidence,
            reason = reason
        )

    def generate_folder_nav_markdown(
        self,
        context_markdown: str,
        documents: list[dict[str, str]]
    ) -> str:
        """Generate one folder navigation markdown by LLM.

        Args:
            context_markdown: Root README/TOC markdown context.
            documents: Created document items with source path and metadata.
        """

        if not self.is_ready():
            return ""
        if not documents:
            return ""

        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        payload_docs = []
        for item in documents[:500]:
            payload_docs.append(
                {
                    "path": str(item.get("path", "")).strip(),
                    "title": str(item.get("title", "")).strip(),
                    "relative_dir": str(item.get("relative_dir", "")).strip(),
                    "toc_label": str(item.get("toc_label", "")).strip()
                }
            )

        prompt_payload = {
            "context_markdown": context_markdown[:12000],
            "documents": payload_docs
        }

        try:
            response = self.http_client.request(
                method = "POST",
                url = endpoint,
                headers = {
                    "Authorization": f"Bearer {self.api_key}"
                },
                json_body = {
                    "model": self.model,
                    "temperature": 0.1,
                    "max_tokens": 1500,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You generate one Markdown navigation document. "
                                "Use heading + bullet structure. "
                                "Every bullet link target must be one source path from documents.path. "
                                "Do not output code fences. "
                                "Output Markdown only."
                            )
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                prompt_payload,
                                ensure_ascii = False
                            )
                        }
                    ]
                }
            )
            payload = response.json()
        except Exception as exc:
            logger.warning("LLM request failed for folder nav generation: %s", str(exc))
            return ""

        content = self._extract_message_content(payload = payload)
        if not content:
            return ""
        return self._strip_markdown_fence(text = content).strip()

    def _extract_message_content(self, payload: dict[str, Any]) -> str:
        """Extract assistant message content from OpenAI-compatible payload.

        Args:
            payload: JSON payload from completion API.
        """

        choices = payload.get("choices", [])
        if not choices:
            return ""
        message = (choices[0] or {}).get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            fragments = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text_value = item.get("text", "")
                if text_value:
                    fragments.append(str(text_value))
            return "".join(fragments)
        return ""

    def _parse_json_text(self, text: str) -> dict[str, Any]:
        """Parse JSON object from LLM text output.

        Args:
            text: Raw response text.
        """

        content = text.strip()
        if not content:
            return {}

        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", content, flags = re.DOTALL)
        if not match:
            return {}

        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
        return {}

    def _safe_float(self, value: Any) -> float:
        """Parse float safely from arbitrary value.

        Args:
            value: Raw numeric value.
        """

        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if parsed < 0.0:
            return 0.0
        if parsed > 1.0:
            return 1.0
        return parsed

    def _strip_markdown_fence(self, text: str) -> str:
        """Strip wrapped markdown code fence from model output.

        Args:
            text: Raw model output text.
        """

        value = (text or "").strip()
        if not value.startswith("```"):
            return value

        lines = value.splitlines()
        if len(lines) >= 2 and lines[0].strip().startswith("```"):
            body = lines[1:]
            if body and body[-1].strip().startswith("```"):
                body = body[:-1]
            return "\n".join(body).strip()
        return value
