import dataclasses

from dataclasses import dataclass
from typing import List


@dataclass
class AssetRef:
    """Represents one image resource referenced by markdown.

    Args:
        original_url: Raw url string found in markdown or HTML img tag.
        resolved_url: Absolute http url or local absolute path after resolution.
        local_cache_path: Temporary path used to cache downloaded image.
        sha256: Hash of the binary content for deduplication.
        media_token: Token returned by Feishu media upload API.
    """

    original_url: str
    resolved_url: str
    local_cache_path: str = ""
    sha256: str = ""
    media_token: str = ""


@dataclass
class SourceDocument:
    """Represents one markdown file from local path or GitHub.

    Args:
        path: Relative markdown path under source root.
        title: Target document title derived from markdown heading or filename.
        markdown: Original markdown content.
        assets: Parsed image references from markdown body.
        relative_dir: Directory path used to create wiki hierarchy.
        base_ref: Base path/url used to resolve relative image links.
        source_type: Source identifier such as local or github.
    """

    path: str
    title: str
    markdown: str
    assets: List[AssetRef]
    relative_dir: str
    base_ref: str
    source_type: str


@dataclass
class ProcessedMarkdown:
    """Markdown parsing output.

    Args:
        markdown: Markdown after optional preprocessing.
        assets: Parsed image references.
        formula_count: Number of detected formula expressions.
    """

    markdown: str
    assets: List[AssetRef]
    formula_count: int


@dataclass
class ImportFailure:
    """One failed import item.

    Args:
        path: Document path that failed to import.
        reason: Error summary.
    """

    path: str
    reason: str


@dataclass
class ImportSkipped:
    """One skipped import item.

    Args:
        path: Document path that is skipped.
        reason: Skip reason summary.
    """

    path: str
    reason: str


@dataclass
class ImportResult:
    """Final task result for one import run.

    Args:
        total: Total markdown files discovered.
        success: Successfully imported file count.
        failed: Failed file count.
        skipped: Skipped file count.
        failures: Detailed failures.
        skipped_items: Detailed skipped items.
        created_docs: Successfully created documents.
    """

    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    failures: List[ImportFailure] = dataclasses.field(default_factory = list)
    skipped_items: List[ImportSkipped] = dataclasses.field(default_factory = list)
    created_docs: List["CreatedDocRecord"] = dataclasses.field(default_factory = list)


@dataclass
class DocumentPlanItem:
    """One planned markdown import item after ordering.

    Args:
        path: Source-relative markdown path.
        order: Final stable order index.
        is_index: Whether this file is an index-like markdown.
        relative_dir: Source-relative directory path.
        toc_label: Optional label extracted from TOC link text.
    """

    path: str
    order: int
    is_index: bool
    relative_dir: str
    toc_label: str = ""


@dataclass
class ImportManifest:
    """Document orchestration plan for one import run.

    Args:
        items: Ordered markdown import items.
        unresolved_links: Unresolved TOC links summary.
        llm_used: Whether LLM fallback was called.
        llm_calls: Number of LLM calls used in this run.
        toc_links: Total markdown links parsed from TOC.
        matched_links: Links successfully resolved into source paths.
        ambiguous_links: Links with multiple candidate paths.
        fallback_count: Links not resolved by LLM fallback.
        skipped_items: Skipped items collected during planning.
    """

    items: List[DocumentPlanItem] = dataclasses.field(default_factory = list)
    unresolved_links: List[str] = dataclasses.field(default_factory = list)
    llm_used: bool = False
    llm_calls: int = 0
    toc_links: int = 0
    matched_links: int = 0
    ambiguous_links: int = 0
    fallback_count: int = 0
    skipped_items: List[ImportSkipped] = dataclasses.field(default_factory = list)


@dataclass
class CreatedDocRecord:
    """Created document record used for post-import navigation output.

    Args:
        path: Source-relative markdown path.
        title: Final document title used in create API.
        document_id: Created document id.
        doc_url: Optional direct document URL.
        wiki_node_token: Optional wiki node token after move operation.
    """

    path: str
    title: str
    document_id: str
    doc_url: str = ""
    wiki_node_token: str = ""


@dataclass
class WikiNodeRef:
    """Represents one wiki node in the destination knowledge base.

    Args:
        space_id: Target wiki space id.
        node_token: Node token used by follow-up APIs.
        title: Node display title.
        parent_token: Parent node token.
    """

    space_id: str
    node_token: str
    title: str
    parent_token: str
