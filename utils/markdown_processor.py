import os
import re
import urllib.parse

from pathlib import Path
from typing import Dict
from typing import List

from data.models import AssetRef
from data.models import ProcessedMarkdown


class MarkdownProcessor:
    """Parse markdown assets and math expressions."""

    MD_IMAGE_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)")
    HTML_IMAGE_PATTERN = re.compile(
        r"<img\s+[^>]*src=[\"'](?P<url>[^\"']+)[\"'][^>]*>",
        flags = re.IGNORECASE
    )
    BLOCK_FORMULA_PATTERN = re.compile(r"\$\$[\s\S]+?\$\$")
    INLINE_FORMULA_PATTERN = re.compile(r"(?<!\$)\$(?!\$)([^\n$]|\\\$)+?(?<!\$)\$(?!\$)")

    def extract_assets_and_math(self, md_text: str, base_path_or_url: str) -> ProcessedMarkdown:
        """Extract image assets and formula count from markdown.

        Args:
            md_text: Original markdown text.
            base_path_or_url: Base path or URL used for relative image resolution.
        """

        asset_urls = []
        seen = set()

        for match in self.MD_IMAGE_PATTERN.finditer(md_text):
            url = match.group("url").strip()
            if url and url not in seen:
                seen.add(url)
                asset_urls.append(url)

        for match in self.HTML_IMAGE_PATTERN.finditer(md_text):
            url = match.group("url").strip()
            if url and url not in seen:
                seen.add(url)
                asset_urls.append(url)

        assets = []
        for original_url in asset_urls:
            resolved_url = self._resolve_url(
                source_url = original_url,
                base_path_or_url = base_path_or_url
            )
            assets.append(
                AssetRef(
                    original_url = original_url,
                    resolved_url = resolved_url
                )
            )

        formula_count = len(self.BLOCK_FORMULA_PATTERN.findall(md_text))
        formula_count += len(self.INLINE_FORMULA_PATTERN.findall(md_text))

        return ProcessedMarkdown(
            markdown = md_text,
            assets = assets,
            formula_count = formula_count
        )

    def replace_asset_links(
        self,
        md_text: str,
        token_map: Dict[str, str],
        image_url_template: str
    ) -> str:
        """Replace image links with Feishu-accessible links.

        Args:
            md_text: Markdown text.
            token_map: Mapping from original/resolved url to media token.
            image_url_template: URL template with {token} placeholder.
        """

        def _replace_md(match: re.Match) -> str:
            alt = match.group("alt")
            source_url = match.group("url").strip()
            token = token_map.get(source_url)
            if not token:
                return match.group(0)
            converted_url = image_url_template.format(token = token)
            return f"![{alt}]({converted_url})"

        def _replace_html(match: re.Match) -> str:
            source_url = match.group("url").strip()
            token = token_map.get(source_url)
            if not token:
                return match.group(0)
            converted_url = image_url_template.format(token = token)
            return match.group(0).replace(source_url, converted_url)

        replaced = self.MD_IMAGE_PATTERN.sub(_replace_md, md_text)
        replaced = self.HTML_IMAGE_PATTERN.sub(_replace_html, replaced)
        return replaced

    def _resolve_url(self, source_url: str, base_path_or_url: str) -> str:
        """Resolve relative image path to an absolute path/url.

        Args:
            source_url: Original image url in markdown.
            base_path_or_url: Base path or URL.
        """

        if source_url.startswith("http://") or source_url.startswith("https://"):
            return source_url
        if source_url.startswith("data:"):
            return source_url

        if base_path_or_url.startswith("http://") or base_path_or_url.startswith("https://"):
            return urllib.parse.urljoin(base_path_or_url, source_url)

        return str((Path(base_path_or_url) / source_url).resolve())

    def map_original_and_resolved_tokens(
        self,
        assets: List[AssetRef]
    ) -> Dict[str, str]:
        """Create token lookup map for replacement.

        Args:
            assets: Asset list with media tokens filled.
        """

        token_map: Dict[str, str] = {}
        for asset in assets:
            if not asset.media_token:
                continue
            token_map[asset.original_url] = asset.media_token
            token_map[asset.resolved_url] = asset.media_token
            decoded = urllib.parse.unquote(asset.original_url)
            token_map[decoded] = asset.media_token
            basename_key = os.path.basename(asset.original_url)
            if basename_key:
                token_map[basename_key] = asset.media_token
        return token_map
