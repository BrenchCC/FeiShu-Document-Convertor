import logging
import posixpath
import re
import urllib.parse

from dataclasses import dataclass
from typing import Optional
from typing import Protocol

from data.models import DocumentPlanItem
from data.models import ImportManifest
from data.models import ImportSkipped
from data.source_adapters import SourceAdapter


logger = logging.getLogger(__name__)


@dataclass
class LlmResolution:
    """LLM resolution output for one ambiguous TOC link.

    Args:
        selected_path: Selected source-relative markdown path.
        confidence: Confidence value in range [0, 1].
        reason: Optional short reasoning text.
    """

    selected_path: str = ""
    confidence: float = 0.0
    reason: str = ""


@dataclass
class TocLinkRef:
    """One markdown link extracted from TOC content.

    Args:
        line_no: 1-based line number in TOC file.
        label: Link label text.
        raw_target: Raw markdown link target text.
    """

    line_no: int
    label: str
    raw_target: str


class TocAmbiguityResolver(Protocol):
    """Protocol for LLM-based TOC ambiguity resolver."""

    def resolve_toc_ambiguity(
        self,
        link_text: str,
        raw_target: str,
        candidate_paths: list[str],
        toc_context: str
    ) -> LlmResolution:
        """Resolve one ambiguous TOC target path.

        Args:
            link_text: TOC link text.
            raw_target: Raw markdown target.
            candidate_paths: Candidate source-relative paths.
            toc_context: Nearby TOC lines for context.
        """


class OrchestrationPlanner:
    """Build stable import ordering from markdown paths and optional TOC."""

    MD_LINK_PATTERN = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<target>[^)]+)\)")
    INDEX_STEMS = {"readme", "index", "table_of_contents", "toc"}
    ROOT_FILTER_STEMS = {"readme"}

    def __init__(
        self,
        source_adapter: SourceAdapter,
        llm_resolver: Optional[TocAmbiguityResolver] = None,
        llm_confidence_threshold: float = 0.6,
        skip_root_readme: bool = False
    ) -> None:
        self.source_adapter = source_adapter
        self.llm_resolver = llm_resolver
        self.llm_confidence_threshold = llm_confidence_threshold
        self.skip_root_readme = skip_root_readme

    def build_manifest(
        self,
        markdown_paths: list[str],
        structure_order: str = "toc_first",
        toc_file: str = "TABLE_OF_CONTENTS.md",
        llm_fallback: str = "toc_ambiguity",
        llm_max_calls: int = 3
    ) -> ImportManifest:
        """Build an ordered document manifest.

        Args:
            markdown_paths: Source-relative markdown file paths.
            structure_order: Ordering strategy, one of toc_first/path.
            toc_file: TOC markdown path relative to source root.
            llm_fallback: LLM fallback mode, one of off/toc_ambiguity.
            llm_max_calls: Max number of LLM calls per run.
        """

        normalized_paths = []
        for path in markdown_paths:
            normalized = self._normalize_relative_path(path = path)
            if normalized:
                normalized_paths.append(normalized)
        normalized_paths = sorted(normalized_paths)
        if not normalized_paths:
            return ImportManifest(items = [])

        skipped_items: list[ImportSkipped] = []
        filtered_root_paths: list[str] = []
        effective_paths: list[str] = []
        for path in normalized_paths:
            if self._is_root_readme_skipped(path = path):
                filtered_root_paths.append(path)
                skipped_items.append(
                    ImportSkipped(
                        path = path,
                        reason = "root_readme_filtered"
                    )
                )
                continue
            effective_paths.append(path)

        if not effective_paths:
            return ImportManifest(
                items = [],
                skipped_items = skipped_items
            )

        if structure_order != "toc_first":
            return self._build_path_manifest(
                paths = effective_paths,
                skipped_items = skipped_items
            )

        toc_content, toc_path = self._load_toc_content(
            markdown_paths = effective_paths,
            toc_file = toc_file
        )
        if not toc_content:
            return self._build_path_manifest(
                paths = effective_paths,
                skipped_items = skipped_items
            )

        toc_links = self._parse_toc_links(toc_content = toc_content)
        if not toc_links:
            return self._build_path_manifest(
                paths = effective_paths,
                skipped_items = skipped_items
            )

        path_lookup, basename_lookup = self._build_path_lookup(paths = effective_paths)
        filtered_root_lookup = {
            path.lower(): path for path in filtered_root_paths
        }
        toc_dir = posixpath.dirname(toc_path)
        toc_lines = toc_content.splitlines()

        ordered_paths: list[str] = []
        seen_paths: set[str] = set()
        path_to_label: dict[str, str] = {}

        unresolved_lines: list[str] = []
        ambiguous_links: list[tuple[TocLinkRef, list[str]]] = []
        matched_links = 0
        ambiguous_count = 0

        for link in toc_links:
            normalized_target = self._normalize_link_target(
                target = link.raw_target,
                toc_dir = toc_dir
            )
            if normalized_target and normalized_target.lower() in filtered_root_lookup:
                skipped_items.append(
                    ImportSkipped(
                        path = filtered_root_lookup[normalized_target.lower()],
                        reason = "root_readme_filtered"
                    )
                )
                continue

            candidate_paths = self._resolve_link_candidates(
                raw_target = link.raw_target,
                toc_dir = toc_dir,
                path_lookup = path_lookup,
                basename_lookup = basename_lookup
            )

            if len(candidate_paths) == 1:
                selected = candidate_paths[0]
                matched_links += 1
                if selected not in seen_paths:
                    ordered_paths.append(selected)
                    seen_paths.add(selected)
                    path_to_label[selected] = link.label
                continue

            if len(candidate_paths) > 1:
                ambiguous_count += 1
                ambiguous_links.append((link, candidate_paths))
                continue

            unresolved_lines.append(
                f"line {link.line_no}: [{link.label}]({link.raw_target}) -> no_match"
            )

        llm_calls = 0
        llm_used = False
        if (
            llm_fallback == "toc_ambiguity"
            and self.llm_resolver
            and llm_max_calls > 0
            and ambiguous_links
        ):
            for link, candidates in ambiguous_links:
                if llm_calls >= llm_max_calls:
                    unresolved_lines.append(
                        (
                            f"line {link.line_no}: [{link.label}]({link.raw_target}) -> "
                            f"llm_limit_exceeded candidates = {', '.join(candidates)}"
                        )
                    )
                    continue

                llm_used = True
                llm_calls += 1
                context = self._build_toc_context(
                    toc_lines = toc_lines,
                    line_no = link.line_no
                )
                resolution = self.llm_resolver.resolve_toc_ambiguity(
                    link_text = link.label,
                    raw_target = link.raw_target,
                    candidate_paths = candidates,
                    toc_context = context
                )

                selected = self._normalize_relative_path(path = resolution.selected_path)
                if (
                    selected in candidates
                    and resolution.confidence >= self.llm_confidence_threshold
                ):
                    matched_links += 1
                    if selected not in seen_paths:
                        ordered_paths.append(selected)
                        seen_paths.add(selected)
                        path_to_label[selected] = link.label
                    continue

                unresolved_lines.append(
                    (
                        f"line {link.line_no}: [{link.label}]({link.raw_target}) -> "
                        f"llm_unresolved candidates = {', '.join(candidates)}"
                    )
                )
        else:
            for link, candidates in ambiguous_links:
                unresolved_lines.append(
                    (
                        f"line {link.line_no}: [{link.label}]({link.raw_target}) -> "
                        f"ambiguous candidates = {', '.join(candidates)}"
                    )
                )

        for path in effective_paths:
            if path in seen_paths:
                continue
            ordered_paths.append(path)
            seen_paths.add(path)

        items = [
            self._build_plan_item(
                path = path,
                order = index,
                toc_label = path_to_label.get(path, "")
            )
            for index, path in enumerate(ordered_paths)
        ]

        return ImportManifest(
            items = items,
            unresolved_links = unresolved_lines,
            llm_used = llm_used,
            llm_calls = llm_calls,
            toc_links = len(toc_links),
            matched_links = matched_links,
            ambiguous_links = ambiguous_count,
            fallback_count = len(unresolved_lines),
            skipped_items = skipped_items
        )

    def _build_path_manifest(
        self,
        paths: list[str],
        skipped_items: Optional[list[ImportSkipped]] = None
    ) -> ImportManifest:
        """Build simple path-sorted manifest without TOC parsing.

        Args:
            paths: Normalized source-relative markdown paths.
            skipped_items: Optional skipped import items.
        """

        items = [
            self._build_plan_item(path = path, order = index)
            for index, path in enumerate(sorted(paths))
        ]
        return ImportManifest(
            items = items,
            skipped_items = skipped_items or []
        )

    def _build_plan_item(self, path: str, order: int, toc_label: str = "") -> DocumentPlanItem:
        """Create one document plan item.

        Args:
            path: Source-relative markdown path.
            order: Stable index.
            toc_label: Optional TOC label.
        """

        relative_dir = posixpath.dirname(path)
        if relative_dir == ".":
            relative_dir = ""
        stem = posixpath.splitext(posixpath.basename(path))[0].lower()
        return DocumentPlanItem(
            path = path,
            order = order,
            is_index = stem in self.INDEX_STEMS,
            relative_dir = relative_dir,
            toc_label = toc_label
        )

    def _build_path_lookup(self, paths: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Build normalized path lookup maps.

        Args:
            paths: Normalized source-relative markdown paths.
        """

        path_lookup: dict[str, list[str]] = {}
        basename_lookup: dict[str, list[str]] = {}
        for path in paths:
            normalized = self._normalize_relative_path(path = path)
            if not normalized:
                continue

            normalized_key = normalized.lower()
            path_lookup.setdefault(normalized_key, []).append(normalized)

            basename = posixpath.basename(normalized).lower()
            basename_lookup.setdefault(basename, []).append(normalized)
        return path_lookup, basename_lookup

    def _load_toc_content(self, markdown_paths: list[str], toc_file: str) -> tuple[str, str]:
        """Load TOC markdown content if present.

        Args:
            markdown_paths: Source markdown paths.
            toc_file: TOC file path relative to source root.
        """

        toc_candidate = self._normalize_relative_path(path = toc_file)
        if not toc_candidate:
            return "", ""

        lookup = {self._normalize_relative_path(path = item).lower(): item for item in markdown_paths}
        toc_path = lookup.get(toc_candidate.lower(), "")
        if not toc_path:
            return "", ""

        try:
            toc_doc = self.source_adapter.read_markdown(relative_path = toc_path)
            return toc_doc.markdown, toc_path
        except Exception as exc:
            logger.warning("Failed to read toc_file = %s: %s", toc_path, str(exc))
            return "", ""

    def _parse_toc_links(self, toc_content: str) -> list[TocLinkRef]:
        """Extract markdown links that target .md files.

        Args:
            toc_content: TOC markdown text.
        """

        links: list[TocLinkRef] = []
        for index, line in enumerate(toc_content.splitlines(), start = 1):
            for match in self.MD_LINK_PATTERN.finditer(line):
                label = (match.group("label") or "").strip()
                target = (match.group("target") or "").strip()
                normalized_target = self._normalize_link_target(target = target, toc_dir = "")
                if not normalized_target:
                    continue
                if not normalized_target.lower().endswith(".md"):
                    continue
                links.append(
                    TocLinkRef(
                        line_no = index,
                        label = label,
                        raw_target = target
                    )
                )
        return links

    def _resolve_link_candidates(
        self,
        raw_target: str,
        toc_dir: str,
        path_lookup: dict[str, list[str]],
        basename_lookup: dict[str, list[str]]
    ) -> list[str]:
        """Resolve one TOC target into source path candidates.

        Args:
            raw_target: Raw target text from markdown link.
            toc_dir: TOC parent directory.
            path_lookup: Normalized path lookup.
            basename_lookup: Basename lookup.
        """

        normalized_target = self._normalize_link_target(target = raw_target, toc_dir = toc_dir)
        if not normalized_target:
            return []

        exact = path_lookup.get(normalized_target.lower(), [])
        if exact:
            return sorted(set(exact))

        basename = posixpath.basename(normalized_target).lower()
        candidates = basename_lookup.get(basename, [])
        if not candidates:
            return []

        if "/" in normalized_target:
            suffix = normalized_target.lower()
            suffix_filtered = [
                item for item in candidates
                if item.lower().endswith(suffix)
            ]
            if suffix_filtered:
                return sorted(set(suffix_filtered))
        return sorted(set(candidates))

    def _build_toc_context(self, toc_lines: list[str], line_no: int, window: int = 2) -> str:
        """Build compact TOC nearby context for LLM fallback.

        Args:
            toc_lines: TOC lines.
            line_no: 1-based target line number.
            window: Number of surrounding lines on each side.
        """

        if not toc_lines or line_no <= 0:
            return ""

        start = max(1, line_no - window)
        end = min(len(toc_lines), line_no + window)
        context_lines = []
        for index in range(start, end + 1):
            context_lines.append(f"{index}: {toc_lines[index - 1]}")
        return "\n".join(context_lines)

    def _normalize_link_target(self, target: str, toc_dir: str) -> str:
        """Normalize one markdown link target path.

        Args:
            target: Raw markdown link target.
            toc_dir: TOC parent directory.
        """

        normalized_target = self._normalize_relative_path(path = target)
        if not normalized_target:
            return ""

        if toc_dir:
            normalized_target = posixpath.normpath(
                posixpath.join(toc_dir, normalized_target)
            )
        return normalized_target.lstrip("/")

    def _normalize_relative_path(self, path: str) -> str:
        """Normalize source-relative path for matching.

        Args:
            path: Raw path text.
        """

        value = urllib.parse.unquote((path or "").strip())
        if not value:
            return ""

        parsed = urllib.parse.urlparse(value)
        if parsed.scheme:
            return ""

        value = value.replace("\\", "/")
        value = value.split("#", 1)[0]
        value = value.split("?", 1)[0]
        if not value:
            return ""

        normalized = posixpath.normpath(value)
        if normalized in {"", "."}:
            return ""

        normalized = normalized.lstrip("/")
        if normalized.startswith("../"):
            return ""
        return normalized

    def _is_root_readme_skipped(self, path: str) -> bool:
        """Check whether source path should be skipped by root README rule.

        Args:
            path: Normalized source-relative path.
        """

        if not self.skip_root_readme:
            return False

        normalized = (path or "").strip().replace("\\", "/").strip("/")
        if "/" in normalized:
            return False
        stem = posixpath.splitext(normalized)[0].lower()
        return stem in self.ROOT_FILTER_STEMS
