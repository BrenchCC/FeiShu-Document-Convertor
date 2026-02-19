import unittest

from core.orchestration_planner import LlmResolution
from core.orchestration_planner import OrchestrationPlanner
from data.models import SourceDocument


class PlannerSource:
    """Fake source adapter for planner tests."""

    def __init__(self, docs: dict[str, SourceDocument], paths: list[str]) -> None:
        self.docs = docs
        self.paths = paths

    def list_markdown(self) -> list[str]:
        """List markdown paths.

        Args:
            self: Source instance.
        """

        return list(self.paths)

    def read_markdown(self, relative_path: str) -> SourceDocument:
        """Read one markdown document.

        Args:
            self: Source instance.
            relative_path: Source-relative markdown path.
        """

        return self.docs[relative_path]


class FakeResolver:
    """Fake ambiguity resolver for planner tests."""

    def __init__(self, selected_path: str, confidence: float) -> None:
        self.selected_path = selected_path
        self.confidence = confidence
        self.calls = 0

    def resolve_toc_ambiguity(
        self,
        link_text: str,
        raw_target: str,
        candidate_paths: list[str],
        toc_context: str
    ) -> LlmResolution:
        """Return deterministic path selection.

        Args:
            self: Resolver instance.
            link_text: Link text.
            raw_target: Raw target text.
            candidate_paths: Candidate path list.
            toc_context: Nearby TOC context.
        """

        self.calls += 1
        return LlmResolution(
            selected_path = self.selected_path,
            confidence = self.confidence,
            reason = "test"
        )


class TestOrchestrationPlanner(unittest.TestCase):
    """Tests for TOC-aware orchestration planner."""

    def _doc(self, path: str, markdown: str = "# x") -> SourceDocument:
        """Build one fake source document.

        Args:
            self: Test case instance.
            path: Relative path.
            markdown: Markdown content.
        """

        relative_dir = ""
        if "/" in path:
            relative_dir = path.rsplit("/", 1)[0]
        return SourceDocument(
            path = path,
            title = path,
            markdown = markdown,
            assets = [],
            relative_dir = relative_dir,
            base_ref = "/tmp",
            source_type = "local"
        )

    def test_toc_first_orders_docs_before_path_tail(self) -> None:
        """TOC links should drive leading document order.

        Args:
            self: Test case instance.
        """

        toc = (
            "# TOC\n"
            "- [Chapter 2](./b/ch2.md)\n"
            "- [Chapter 1](./a/ch1.md)\n"
        )
        docs = {
            "TABLE_OF_CONTENTS.md": self._doc(path = "TABLE_OF_CONTENTS.md", markdown = toc),
            "a/ch1.md": self._doc(path = "a/ch1.md"),
            "b/ch2.md": self._doc(path = "b/ch2.md"),
            "README.md": self._doc(path = "README.md")
        }
        source = PlannerSource(
            docs = docs,
            paths = ["README.md", "a/ch1.md", "TABLE_OF_CONTENTS.md", "b/ch2.md"]
        )
        planner = OrchestrationPlanner(source_adapter = source)

        manifest = planner.build_manifest(
            markdown_paths = source.list_markdown(),
            structure_order = "toc_first",
            toc_file = "TABLE_OF_CONTENTS.md",
            llm_fallback = "off",
            llm_max_calls = 0
        )

        self.assertEqual(manifest.items[0].path, "b/ch2.md")
        self.assertEqual(manifest.items[1].path, "a/ch1.md")
        self.assertEqual(manifest.toc_links, 2)
        self.assertEqual(manifest.matched_links, 2)

    def test_path_order_used_when_toc_missing(self) -> None:
        """Path ordering should be used when TOC file does not exist.

        Args:
            self: Test case instance.
        """

        docs = {
            "b.md": self._doc(path = "b.md"),
            "a.md": self._doc(path = "a.md")
        }
        source = PlannerSource(
            docs = docs,
            paths = ["b.md", "a.md"]
        )
        planner = OrchestrationPlanner(source_adapter = source)

        manifest = planner.build_manifest(
            markdown_paths = source.list_markdown(),
            structure_order = "toc_first",
            toc_file = "TABLE_OF_CONTENTS.md",
            llm_fallback = "off",
            llm_max_calls = 0
        )

        self.assertEqual(
            [item.path for item in manifest.items],
            ["a.md", "b.md"]
        )
        self.assertEqual(manifest.toc_links, 0)

    def test_llm_fallback_resolves_ambiguous_toc_link_with_call_cap(self) -> None:
        """Ambiguous TOC targets should use LLM fallback within call cap.

        Args:
            self: Test case instance.
        """

        toc = (
            "# TOC\n"
            "- [Intro](./intro.md)\n"
            "- [Another Intro](./intro.md)\n"
        )
        docs = {
            "TABLE_OF_CONTENTS.md": self._doc(path = "TABLE_OF_CONTENTS.md", markdown = toc),
            "part1/intro.md": self._doc(path = "part1/intro.md"),
            "part2/intro.md": self._doc(path = "part2/intro.md")
        }
        source = PlannerSource(
            docs = docs,
            paths = ["TABLE_OF_CONTENTS.md", "part1/intro.md", "part2/intro.md"]
        )
        resolver = FakeResolver(
            selected_path = "part2/intro.md",
            confidence = 0.92
        )
        planner = OrchestrationPlanner(
            source_adapter = source,
            llm_resolver = resolver
        )

        manifest = planner.build_manifest(
            markdown_paths = source.list_markdown(),
            structure_order = "toc_first",
            toc_file = "TABLE_OF_CONTENTS.md",
            llm_fallback = "toc_ambiguity",
            llm_max_calls = 1
        )

        self.assertEqual(manifest.items[0].path, "part2/intro.md")
        self.assertEqual(manifest.llm_used, True)
        self.assertEqual(manifest.llm_calls, 1)
        self.assertLessEqual(resolver.calls, 1)

    def test_root_readme_filtered_but_subdir_readme_kept(self) -> None:
        """Root README should be filtered while subdir README remains included.

        Args:
            self: Test case instance.
        """

        docs = {
            "README.md": self._doc(path = "README.md"),
            "TABLE_OF_CONTENTS.md": self._doc(path = "TABLE_OF_CONTENTS.md"),
            "sub/README.md": self._doc(path = "sub/README.md")
        }
        source = PlannerSource(
            docs = docs,
            paths = ["sub/README.md", "README.md", "TABLE_OF_CONTENTS.md"]
        )
        planner = OrchestrationPlanner(source_adapter = source)

        manifest = planner.build_manifest(
            markdown_paths = source.list_markdown(),
            structure_order = "path",
            toc_file = "TABLE_OF_CONTENTS.md",
            llm_fallback = "off",
            llm_max_calls = 0
        )

        self.assertEqual(len(manifest.items), 2)
        self.assertEqual(
            [item.path for item in manifest.items],
            ["TABLE_OF_CONTENTS.md", "sub/README.md"]
        )
        self.assertTrue(all(item.is_index for item in manifest.items))
        self.assertEqual(len(manifest.skipped_items), 1)
        self.assertEqual(manifest.skipped_items[0].path, "README.md")

    def test_toc_link_to_root_readme_recorded_as_skipped(self) -> None:
        """TOC links to filtered root README should be reported as skipped.

        Args:
            self: Test case instance.
        """

        toc = (
            "# TOC\n"
            "- [Root Readme](./README.md)\n"
            "- [Sub Readme](./sub/README.md)\n"
        )
        docs = {
            "TABLE_OF_CONTENTS.md": self._doc(path = "TABLE_OF_CONTENTS.md", markdown = toc),
            "README.md": self._doc(path = "README.md"),
            "sub/README.md": self._doc(path = "sub/README.md")
        }
        source = PlannerSource(
            docs = docs,
            paths = ["TABLE_OF_CONTENTS.md", "README.md", "sub/README.md"]
        )
        planner = OrchestrationPlanner(source_adapter = source)

        manifest = planner.build_manifest(
            markdown_paths = source.list_markdown(),
            structure_order = "toc_first",
            toc_file = "TABLE_OF_CONTENTS.md",
            llm_fallback = "off",
            llm_max_calls = 0
        )

        self.assertEqual([item.path for item in manifest.items], ["sub/README.md", "TABLE_OF_CONTENTS.md"])
        self.assertEqual(len(manifest.unresolved_links), 0)
        self.assertGreaterEqual(len(manifest.skipped_items), 1)
        self.assertIn(
            "root_readme_filtered",
            [item.reason for item in manifest.skipped_items]
        )
        self.assertTrue(all(item.is_index for item in manifest.items))

    def test_root_index_filtered_but_subdir_index_kept(self) -> None:
        """Root index should be filtered while subdir index remains included.

        Args:
            self: Test case instance.
        """

        docs = {
            "index.md": self._doc(path = "index.md"),
            "TABLE_OF_CONTENTS.md": self._doc(path = "TABLE_OF_CONTENTS.md"),
            "sub/index.md": self._doc(path = "sub/index.md")
        }
        source = PlannerSource(
            docs = docs,
            paths = ["index.md", "TABLE_OF_CONTENTS.md", "sub/index.md"]
        )
        planner = OrchestrationPlanner(source_adapter = source)

        manifest = planner.build_manifest(
            markdown_paths = source.list_markdown(),
            structure_order = "path",
            toc_file = "TABLE_OF_CONTENTS.md",
            llm_fallback = "off",
            llm_max_calls = 0
        )

        self.assertEqual(
            [item.path for item in manifest.items],
            ["TABLE_OF_CONTENTS.md", "sub/index.md"]
        )
        self.assertEqual(
            [item.path for item in manifest.skipped_items],
            ["index.md"]
        )
        self.assertEqual(
            [item.reason for item in manifest.skipped_items],
            ["root_readme_filtered"]
        )


if __name__ == "__main__":
    unittest.main()
