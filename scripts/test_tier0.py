#!/usr/bin/env python3
"""Regression tests for scripts/tier0.py.

Each fixture pins down a case the sweep must catch or must leave alone, so a change to the
script that quietly turns a sweep into a guaranteed pass is noticed. Patterns naming the
other platform are assembled from parts, as in common.py, so this file cannot trip the sweep.

Run with: python3 scripts/test_tier0.py
"""
import ast
import inspect
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402
import tier0  # noqa: E402
from common import load_settings, source_entries  # noqa: E402

FENCE = "`" * 3


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


DEFAULT_HEADER = "status: unverified\nlast_verified: 2026-10-06\nverify_with: n/a"
DEFAULT_SOURCE = "team knowledge (2026-10-06), unverified"


class FixtureRepo:
    """A throwaway handbook plus sibling repos tree for one test."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "handbook"
        self.root.mkdir()
        self._orig = None

    def __enter__(self):
        self._orig = (tier0.HANDBOOK_ROOT, tier0.SIBLING_REPOS_ROOT)
        tier0.HANDBOOK_ROOT = self.root
        tier0.SIBLING_REPOS_ROOT = self.tmp
        return self

    def __exit__(self, *exc):
        tier0.HANDBOOK_ROOT, tier0.SIBLING_REPOS_ROOT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def page(self, relpath: str, body: str = "# page\n", frontmatter: str | None = None, sources: list | None = None):
        """A page. The sources go to the final section '## Sources' and the header gets `sources_count`, unless the header given
        already holds a `sources:` list (the old form, which a test of that form writes on purpose). A page whose header is given
        without `sources_count` and with no `sources` has neither."""
        fm = frontmatter if frontmatter is not None else DEFAULT_HEADER
        if "sources:" in fm:
            write(self.root / relpath, f"---\n{fm}\n---\n\n{body}")
            return
        if sources is None and (frontmatter is None or "sources_count" in fm):
            sources = [DEFAULT_SOURCE]
        if sources is not None:
            if "sources_count" not in fm:
                fm = f"{fm}\nsources_count: {len(sources)}"
            body = body.rstrip("\n") + "\n\n## Sources\n\n" + "\n".join("- " + s for s in sources) + "\n"
        write(self.root / relpath, f"---\n{fm}\n---\n\n{body}")

    def fenced(self, relpath: str, *commands: str):
        self.page(relpath, "# page\n\n" + FENCE + "bash\n" + "\n".join(commands) + "\n" + FENCE + "\n")


def blank():
    return {"blocking": [], "warning": [], "info": []}


def checks(report, bucket="blocking"):
    return [f["check"] for f in report[bucket]]


class FrontmatterTests(unittest.TestCase):
    def test_second_colon_in_a_source_is_caught(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", frontmatter=(
                "status: unverified\nlast_verified: 2026-10-06\nverify_with: n/a\nsources:\n"
                "  - live: curl https://example.invalid/health (state: OK)"))
            r = blank()
            tier0.sweep_yaml_frontmatter(r)
            self.assertEqual(checks(r), ["broken-frontmatter-yaml"])

    def test_missing_key_is_caught(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", frontmatter="status: unverified\nlast_verified: 2026-10-06")
            r = blank()
            tier0.sweep_yaml_frontmatter(r)
            self.assertEqual(checks(r), ["missing-frontmatter-key"])

    def test_a_page_with_no_frontmatter_is_caught_but_the_root_files_are_exempt(self):
        with FixtureRepo() as fx:
            for name in ("README.md", "CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md"):
                write(fx.root / name, "# a root file of the project\n")
            write(fx.root / "reference" / "a.md", "# no frontmatter\n")
            write(fx.root / "reference" / "README.md", "# a nested README is not the root one\n")
            r = blank()
            tier0.sweep_yaml_frontmatter(r)
            self.assertEqual(sorted(f["detail"].split(":")[0] for f in r["blocking"]),
                             ["reference/README.md", "reference/a.md"])


class LinkIntegrityTests(unittest.TestCase):
    def test_broken_link_blocks_and_orphan_warns(self):
        with FixtureRepo() as fx:
            write(fx.root / "README.md", "[gone](reference/missing.md)\n")
            fx.page("reference/orphan.md")
            r = blank()
            tier0.sweep_link_integrity(r)
            self.assertEqual(checks(r), ["broken-link"])
            self.assertEqual(checks(r, "warning"), ["orphaned-page"])

    def test_a_page_that_the_index_lists_is_not_an_orphan_and_one_it_does_not_list_is(self):
        with FixtureRepo() as fx:
            write(fx.root / "README.md", "# readme\n")
            fx.page("reference/listed.md")
            fx.page("reference/unlisted.md")
            write(fx.root / "INDEX.md", "# INDEX\n\n| Page | Title |\n|---|---|\n| reference/listed.md | T |\n")
            r = blank()
            tier0.sweep_link_integrity(r)
            self.assertEqual([f["detail"] for f in r["warning"]], ["INDEX.md", "reference/unlisted.md"])

    def test_a_linked_page_is_not_an_orphan(self):
        with FixtureRepo() as fx:
            write(fx.root / "README.md", "[a](reference/a.md)\n")
            fx.page("reference/a.md")
            r = blank()
            tier0.sweep_link_integrity(r)
            self.assertEqual((checks(r), checks(r, "warning")), ([], []))


class SourcesPathExistsTests(unittest.TestCase):
    def test_sibling_repo_path_checked_against_the_sibling_root(self):
        with FixtureRepo() as fx:
            write(fx.tmp / "other-repo" / "modules" / "a" / "main.tf", "")
            fx.page("reference/a.md", sources=["other-repo/modules/a/main.tf", "other-repo/modules/gone/main.tf"])
            r = blank()
            tier0.sweep_sources_path_exists(r)
            self.assertEqual(len(r["warning"]), 1)
            self.assertIn("modules/gone/main.tf", r["warning"][0]["detail"])

    def test_cross_reference_to_a_page_in_this_repo_is_not_looked_up_in_the_sibling_root(self):
        with FixtureRepo() as fx:
            fx.page("reference/b.md")
            fx.page("reference/a.md", sources=["reference/b.md"])
            r = blank()
            tier0.sweep_sources_path_exists(r)
            self.assertEqual(r["warning"], [])

    def test_cross_reference_to_a_page_under_process_is_looked_up_in_this_repo(self):
        with FixtureRepo() as fx:
            fx.page("process/b.md")
            fx.page("reference/a.md", sources=["process/b.md", "process/gone.md"])
            r = blank()
            tier0.sweep_sources_path_exists(r)
            self.assertEqual(len(r["warning"]), 1)
            self.assertIn("process/gone.md", r["warning"][0]["detail"])


class SourcesSectionTests(unittest.TestCase):
    """The sources are the final section '## Sources' and the header says how many (process/frontmatter.md)."""

    def sweep(self):
        r = blank()
        tier0.sweep_sources_section(r)
        return r

    def test_a_page_with_a_section_and_the_right_count_passes(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", sources=["team knowledge (2026-10-06), unverified: a claim", "live: curl https://example.invalid/health (state: OK)"])
            r = self.sweep()
            self.assertEqual((checks(r), checks(r, "warning")), ([], []))

    def test_a_count_that_is_not_the_number_of_entries_blocks(self):
        for count, entries in ((3, 2), (1, 2), (0, 1)):
            with self.subTest(count=count), FixtureRepo() as fx:
                fx.page("reference/a.md", frontmatter=DEFAULT_HEADER + f"\nsources_count: {count}", sources=["x"] * entries)
                r = self.sweep()
                self.assertEqual(checks(r), ["sources-count-mismatch"])
                self.assertIn(f"says {count}", r["blocking"][0]["detail"])

    def test_a_count_that_is_not_a_whole_number_blocks(self):
        for bad in ("two", "1.5", "true"):
            with self.subTest(bad=bad), FixtureRepo() as fx:
                fx.page("reference/a.md", frontmatter=DEFAULT_HEADER + f"\nsources_count: {bad}", sources=["x", "y"])
                self.assertEqual(checks(self.sweep()), ["sources-count-mismatch"])

    def test_a_page_without_the_section_blocks(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", frontmatter=DEFAULT_HEADER + "\nsources_count: 1", sources=[])
            write(fx.root / "reference/a.md", "---\n" + DEFAULT_HEADER + "\nsources_count: 1\n---\n\n# page\n\ntext\n")
            self.assertEqual(checks(self.sweep()), ["missing-sources-section"])

    def test_a_heading_after_the_section_blocks_and_a_heading_inside_a_fence_does_not(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", frontmatter=DEFAULT_HEADER + "\nsources_count: 1", sources=["x"])
            path = fx.root / "reference/a.md"
            write(path, path.read_text() + "\n## Notes\n\ntext\n")
            self.assertEqual(checks(self.sweep()), ["sources-section-not-last"])
        with FixtureRepo() as fx:
            fx.page("reference/a.md", frontmatter=DEFAULT_HEADER + "\nsources_count: 1", sources=["x"])
            fx.page("reference/b.md", body="# page\n\n" + FENCE + "\n## Sources\n" + FENCE + "\n", sources=["x"])
            self.assertEqual(checks(self.sweep()), [])

    def test_an_entry_wrapped_onto_a_second_line_blocks(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", sources=["a long entry\n  that continues here"])
            self.assertEqual(checks(self.sweep()), ["sources-entry-malformed"])

    def test_a_second_colon_in_an_entry_is_no_longer_a_problem(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", sources=["live: curl https://example.invalid/health (state: OK)"])
            r = blank()
            tier0.sweep_yaml_frontmatter(r)
            self.assertEqual((checks(r), checks(self.sweep())), ([], []))

    def test_the_entries_are_read_in_order_with_the_marker_removed(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", sources=["one: first", "two", "other-repo/x.tf, commit abc1234"])
            content = (fx.root / "reference/a.md").read_text()
            self.assertEqual(source_entries(content), (["one: first", "two", "other-repo/x.tf, commit abc1234"], []))

    def test_the_old_list_in_the_header_is_forbidden_and_the_same_entries_in_the_section_pass(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", frontmatter=DEFAULT_HEADER + "\nsources:\n  - one\n  - two")
            r = self.sweep()
            self.assertEqual(checks(r), ["sources-in-front-matter"])
            self.assertIn("process/frontmatter.md", r["blocking"][0]["detail"])
        with FixtureRepo() as fx:
            fx.page("reference/a.md", sources=["one", "two"])
            self.assertEqual(checks(self.sweep()), [])

    def test_the_old_list_is_not_read_as_the_entries_of_a_page(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", frontmatter=DEFAULT_HEADER + "\nsources:\n  - one\n  - two: second")
            self.assertEqual(source_entries((fx.root / "reference/a.md").read_text()), ([], [("missing-sources-section", "no '## Sources' section at the end of the page")]))

    def test_a_page_with_neither_form_lacks_the_key(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", frontmatter=DEFAULT_HEADER)
            r = blank()
            tier0.sweep_yaml_frontmatter(r)
            self.assertEqual(checks(r), ["missing-frontmatter-key"])
            self.assertIn("sources_count", r["blocking"][0]["detail"])


class SplitFrontmatterTests(unittest.TestCase):
    def test_a_dashed_line_inside_a_value_does_not_close_the_header(self):
        from common import split_frontmatter, parse_frontmatter
        text = "---\nstatus: unverified\nsummary: a ---b and more\nverify_with: n/a\n---\n\n# T\n"
        raw, body = split_frontmatter(text)
        self.assertIn("verify_with: n/a", raw)
        self.assertEqual(body, "\n\n# T\n")
        self.assertEqual(parse_frontmatter(text)[0]["summary"], "a ---b and more")

    def test_no_closing_line_or_no_opening_line_means_no_header(self):
        from common import split_frontmatter
        self.assertEqual(split_frontmatter("---\nstatus: x\n# T\n")[0], None)
        self.assertEqual(split_frontmatter("# T\n---\nx\n---\n")[0], None)
        self.assertEqual(split_frontmatter("----\nx\n---\n")[0], None)


class SourceEntryEdgeTests(unittest.TestCase):
    PAGE = "---\nstatus: unverified\nsources_count: 1\n---\n\n# T\n\n{body}\n## Sources\n\n{entries}"

    def test_a_tilde_block_that_holds_a_backtick_line_does_not_end_early(self):
        body = "~~~\n" + "`" * 3 + "\n~~~\n"
        entries, problems = source_entries(self.PAGE.format(body=body, entries="- a\n"))
        self.assertEqual((entries, problems), (["a"], []))

    def test_a_longer_fence_is_closed_only_by_a_fence_at_least_as_long(self):
        body = "`" * 4 + "\n## Sources\n" + "`" * 3 + "\nstill inside\n" + "`" * 4 + "\n"
        entries, problems = source_entries(self.PAGE.format(body=body, entries="- a\n"))
        self.assertEqual((entries, problems), (["a"], []))

    def test_an_empty_entry_is_malformed(self):
        entries, problems = source_entries(self.PAGE.format(body="", entries="- \n- b\n"))
        self.assertEqual(entries, ["b"])
        self.assertEqual([c for c, _ in problems], ["sources-entry-malformed"])


class SourcesPlaceTests(unittest.TestCase):
    """Every sweep that read the entries of the header reads the section now: a failing and a passing case for each."""

    def test_a_cited_path_in_the_section_that_is_gone_is_found_and_one_that_exists_is_not(self):
        with FixtureRepo() as fx:
            write(fx.tmp / "other-repo" / "modules" / "a" / "main.tf", "")
            fx.page("reference/gone.md", sources=["other-repo/modules/gone/main.tf (read 2026-10-27)"])
            fx.page("reference/there.md", sources=["other-repo/modules/a/main.tf (read 2026-10-27)"])
            r = blank()
            tier0.sweep_sources_path_exists(r)
            self.assertEqual([f["detail"].split(":")[0] for f in r["warning"]], ["reference/gone.md"])

    def test_a_tag_pin_a_live_entry_and_team_knowledge_are_not_looked_up(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", sources=["other-repo @ git-abc123 (read 2026-10-27)", "live: curl x/y 2026-10-27 (ok)", "team knowledge (2026-10-27), unverified: x/y"])
            r = blank()
            tier0.sweep_sources_path_exists(r)
            self.assertEqual((r["warning"], r["info"]), ([], []))

    def test_text_that_looks_like_an_entry_outside_the_section_is_not_read(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", body="# page\n\n- other-repo/modules/gone/main.tf\n", sources=["team knowledge (2026-10-06), unverified"])
            r = blank()
            tier0.sweep_sources_path_exists(r)
            self.assertEqual(r["warning"], [])


def sized(fx, rel: str, size: int):
    """A Markdown file of exactly `size` bytes."""
    write(fx.root / rel, "x" * (size - 1) + "\n")


class SizeBudgetTests(unittest.TestCase):
    """A page over 60 KB, CLAUDE.md and INDEX.md over 40 KB, and the ratchet list of the pages that are over today."""

    def sweep(self):
        r = blank()
        tier0.sweep_size_budget(r)
        return r

    def test_a_page_at_the_budget_passes_and_one_byte_over_warns(self):
        with FixtureRepo() as fx:
            sized(fx, "operations/at.md", 60_000)
            sized(fx, "operations/over.md", 60_001)
            r = self.sweep()
            self.assertEqual(checks(r, "warning"), ["size-over-budget"])
            self.assertIn("operations/over.md is 60001 bytes, 1 over", r["warning"][0]["detail"])
            self.assertEqual(r["blocking"], [])

    def test_claude_md_and_the_index_have_a_budget_of_40_kb(self):
        with FixtureRepo() as fx:
            sized(fx, "CLAUDE.md", 40_000)
            sized(fx, "INDEX.md", 40_000)
            sized(fx, "README.md", 45_000)
            self.assertEqual(checks(self.sweep(), "warning"), [])
        with FixtureRepo() as fx:
            sized(fx, "CLAUDE.md", 40_001)
            sized(fx, "INDEX.md", 40_001)
            r = self.sweep()
            self.assertEqual([f["detail"].split(" ")[0] for f in r["warning"]], ["CLAUDE.md", "INDEX.md"])

    def test_a_listed_page_is_held_to_its_line_not_to_the_budget(self):
        with FixtureRepo() as fx:
            write(fx.root / "scripts/size-budget.txt", "# a comment\n\noperations/big.md 90000  # its size on the day\n")
            sized(fx, "operations/big.md", 90_000)
            r = self.sweep()
            self.assertEqual((checks(r, "warning"), checks(r, "info")), ([], []))
        with FixtureRepo() as fx:
            write(fx.root / "scripts/size-budget.txt", "operations/big.md 90000\n")
            sized(fx, "operations/big.md", 90_001)
            r = self.sweep()
            self.assertEqual(checks(r, "warning"), ["size-over-ratchet"])
            self.assertIn("1 over the 90000", r["warning"][0]["detail"])

    def test_the_generated_index_over_its_budget_is_told_how_to_shrink_and_not_to_split_a_page(self):
        with FixtureRepo() as fx:
            sized(fx, "INDEX.md", 40_001)
            sized(fx, "operations/big.md", 60_001)
            details = {f["detail"].split(" ")[0]: f["detail"] for f in self.sweep()["warning"]}
            self.assertIn("shorten the summaries", details["INDEX.md"])
            self.assertNotIn("shorten the summaries", details["operations/big.md"])
            self.assertIn("split it", details["operations/big.md"])

    def test_claude_md_on_the_list_may_not_grow(self):
        with FixtureRepo() as fx:
            write(fx.root / "scripts/size-budget.txt", "CLAUDE.md 43561\n")
            sized(fx, "CLAUDE.md", 43_561)
            self.assertEqual(checks(self.sweep(), "warning"), [])
            sized(fx, "CLAUDE.md", 43_562)
            self.assertEqual(checks(self.sweep(), "warning"), ["size-over-ratchet"])

    def test_a_page_that_shrank_is_told_to_lower_its_line_and_one_back_within_budget_to_drop_it(self):
        with FixtureRepo() as fx:
            write(fx.root / "scripts/size-budget.txt", "operations/a.md 90000\noperations/b.md 90000\noperations/c.md 90000\n")
            sized(fx, "operations/a.md", 89_000)  # within the slack of 1000: nothing to say
            sized(fx, "operations/b.md", 88_999)
            sized(fx, "operations/c.md", 59_000)
            r = self.sweep()
            self.assertEqual(checks(r, "warning"), [])
            self.assertEqual([(f["check"], f["detail"].split(" ")[0]) for f in r["info"]],
                             [("size-ratchet-slack", "operations/b.md"), ("size-ratchet-obsolete", "operations/c.md")])

    def test_a_line_for_a_file_that_does_not_exist_and_a_bad_line_warn(self):
        with FixtureRepo() as fx:
            write(fx.root / "scripts/size-budget.txt", "operations/gone.md 70000\nnot a line\noperations/x.md 7\noperations/x.md 8\n")
            sized(fx, "operations/x.md", 5)
            r = self.sweep()
            self.assertEqual(sorted(checks(r, "warning")), ["size-budget-bad-line", "size-budget-bad-line", "size-ratchet-file-gone"])

    def test_the_list_is_read_by_a_pure_function_and_the_increases_are_found(self):
        limits, bad = tier0.read_size_budget("a.md 10\n# c\nb.md 20 # d\nb.md 30\nc.md x\n")
        self.assertEqual((limits, bad), ({"a.md": 10, "b.md": 20}, [4, 5]))
        base = {"a.md": 100, "b.md": 200}
        self.assertEqual(tier0.ratchet_increases(base, {"a.md": 100, "b.md": 150}), [])
        self.assertEqual(tier0.ratchet_increases(base, {"b.md": 200}), [])
        found = tier0.ratchet_increases(base, {"a.md": 101, "b.md": 200, "c.md": 5})
        self.assertEqual(len(found), 2)
        self.assertIn("a.md was 100 bytes and its line now says 101", found[0])
        self.assertIn("c.md is a new line (5 bytes)", found[1])

    def merged_list(self, fx, text):
        """The list as it is on origin/main: a repository in the fixture with that ref."""
        write(fx.root / "scripts/size-budget.txt", text)
        for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "x", "--no-verify"],
                     ["update-ref", "refs/remotes/origin/main", "HEAD"]):
            subprocess.run(["git", "-C", str(fx.root), *args], check=True, capture_output=True, env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})

    def test_a_line_raised_or_added_after_the_list_was_merged_warns_and_a_lowered_one_does_not(self):
        with FixtureRepo() as fx:
            sized(fx, "operations/a.md", 70_000)
            sized(fx, "operations/b.md", 80_000)
            self.merged_list(fx, "operations/a.md 70000\noperations/b.md 80000\n")
            write(fx.root / "scripts/size-budget.txt", "operations/a.md 70000\noperations/b.md 80000\n")
            self.assertEqual(checks(self.sweep(), "warning"), [])
            sized(fx, "operations/a.md", 69_000)
            sized(fx, "operations/b.md", 59_000)
            write(fx.root / "scripts/size-budget.txt", "operations/a.md 69000\n")  # one line lowered, one removed
            self.assertEqual(checks(self.sweep(), "warning"), [])
            sized(fx, "operations/b.md", 85_000)
            sized(fx, "operations/c.md", 61_000)
            write(fx.root / "scripts/size-budget.txt", "operations/a.md 70000\noperations/b.md 85000\noperations/c.md 61000\n")
            r = self.sweep()
            self.assertEqual(checks(r, "warning"), ["size-ratchet-raised", "size-ratchet-raised"])
            self.assertIn("operations/b.md was 80000 bytes and its line now says 85000", r["warning"][0]["detail"])
            self.assertIn("operations/c.md is a new line", r["warning"][1]["detail"])

    def test_without_a_merged_list_nothing_is_compared(self):
        with FixtureRepo() as fx:
            sized(fx, "operations/a.md", 70_000)
            write(fx.root / "scripts/size-budget.txt", "operations/a.md 70000\n")
            subprocess.run(["git", "-C", str(fx.root), "init", "-q"], check=True, capture_output=True, env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
            self.assertEqual(checks(self.sweep(), "warning"), [])


def indexed_front(extra: str) -> str:
    return "status: unverified\nlast_verified: 2026-10-27\nverify_with: n/a\n" + extra + "sources_count: 1"


class VerificationAgeTests(unittest.TestCase):
    """A `verified` page whose date is more than 30 days old, a date that is not a date, and a date in the future.

    The day of the tests is far from the real one, so that a sweep that read the clock instead of its argument would fail them.
    """

    TODAY = date(2030, 1, 15)

    def ago(self, days):
        return self.TODAY - timedelta(days=days)

    def findings(self, pages):
        return tier0.age_findings(pages, self.TODAY)

    def test_a_verified_page_is_aged_after_thirty_days_and_not_on_the_thirtieth(self):
        got = self.findings({"operations/old.md": ("verified", self.ago(31)), "operations/edge.md": ("verified", self.ago(30))})
        self.assertEqual([(b, c) for b, c, _ in got], [("warning", "verification-aged")])
        self.assertIn(f"operations/old.md: verified on {self.ago(31)}, 31 days ago (limit 30)", got[0][2])

    def test_an_unverified_or_stale_page_does_not_age(self):
        old = self.ago(400)
        self.assertEqual(self.findings({"a.md": ("unverified", old), "b.md": ("stale", old), "c.md": (None, old), "d.md": ("Verified", old)}), [])

    def test_a_record_does_not_age_but_its_date_is_still_read(self):
        old = self.ago(400)
        records = {
            "operations/releases/r.md": ("verified", old),
            "architecture/retrospectives/r.md": ("verified", old),
        }
        self.assertEqual(self.findings(records), [])
        self.assertEqual([c for _, c, _ in self.findings({"operations/releases/r.md": ("verified", "soon")})], ["last-verified-unreadable"])

    def test_a_value_that_is_not_a_calendar_date_is_unreadable_whatever_the_status(self):
        values = ["soon", None, "2026-13-45", "2026-1-5", "20261030", 20261030, 2026.1, True, ["2026-10-30"], ""]
        got = self.findings({f"p{i}.md": ("unverified", v) for i, v in enumerate(values)})
        self.assertEqual({c for _, c, _ in got}, {"last-verified-unreadable"})
        self.assertEqual(len(got), len(values))

    def test_a_date_after_today_is_reported_and_today_is_not(self):
        got = self.findings({"a.md": ("verified", self.ago(-1)), "b.md": ("verified", self.ago(0))})
        self.assertEqual([(c, d.split(":")[0]) for _, c, d in got], [("last-verified-in-the-future", "a.md")])

    def test_a_quoted_date_with_spaces_and_a_datetime_are_read_like_a_date(self):
        old = self.ago(60)
        got = self.findings({"a.md": ("verified", f" {old} "), "b.md": ("verified", datetime(old.year, old.month, old.day, 12, 0)), "c.md": ("verified", str(old))})
        self.assertEqual([c for _, c, _ in got], ["verification-aged"] * 3)

    def test_the_sweep_reads_the_header_of_every_page_with_the_day_it_is_given(self):
        def header(day, status="verified"):
            return f"status: {status}\nlast_verified: {day}\nverify_with: n/a"

        with FixtureRepo() as fx:
            fx.page("operations/aged.md", frontmatter=header(self.ago(61)))
            fx.page("operations/quoted.md", frontmatter=header(f'"{self.ago(61)}"'))
            fx.page("operations/fresh.md", frontmatter=header(self.ago(1)))
            fx.page("operations/unverified.md", frontmatter=header(self.ago(61), "unverified"))
            fx.page("operations/future.md", frontmatter=header(self.ago(-5)))
            fx.page("operations/word.md", frontmatter=header("soon"))
            fx.page("operations/empty.md", frontmatter=header(""))
            fx.page("operations/number.md", frontmatter=header("20301231"))
            fx.page("operations/nodate.md", frontmatter="status: verified\nverify_with: n/a")
            fx.page("operations/broken.md", frontmatter=f"status: verified\nlast_verified: [{self.ago(61)}\nverify_with: n/a")
            write(fx.root / "README.md", "# no header\n")
            r = blank()
            tier0.sweep_verification_age(r, today=self.TODAY)
            self.assertEqual(
                sorted((f["check"], f["detail"].split(":")[0]) for f in r["warning"]),
                [
                    ("last-verified-in-the-future", "operations/future.md"),
                    ("last-verified-unreadable", "operations/empty.md"),
                    ("last-verified-unreadable", "operations/number.md"),
                    ("last-verified-unreadable", "operations/word.md"),
                    ("verification-aged", "operations/aged.md"),
                    ("verification-aged", "operations/quoted.md"),
                ],
            )
            self.assertEqual(r["blocking"], [])

    def test_an_unquoted_date_that_does_not_exist_is_a_broken_header_and_no_sweep_crashes(self):
        with FixtureRepo() as fx:
            fx.page("operations/typo.md", frontmatter="status: verified\nlast_verified: 2030-13-45\nverify_with: n/a\nsources_count: 1")
            fx.page("operations/aged.md", frontmatter=f"status: verified\nlast_verified: {self.ago(61)}\nverify_with: n/a\nsources_count: 1")
            r = blank()
            tier0.sweep_yaml_frontmatter(r)
            tier0.sweep_verification_age(r, today=self.TODAY)
            self.assertEqual(checks(r), ["broken-frontmatter-yaml"])
            self.assertIn("operations/typo.md", r["blocking"][0]["detail"])
            self.assertEqual(checks(r, "warning"), ["verification-aged"])

    def test_an_empty_message_of_the_parser_still_gives_a_reason(self):
        real = common.yaml.safe_load
        try:
            common.yaml.safe_load = lambda raw: (_ for _ in ()).throw(ValueError())
            self.assertEqual(common.parse_frontmatter("---\nx: 1\n---\n"), (None, "ValueError"))
        finally:
            common.yaml.safe_load = real

    def test_the_limit_the_code_uses_is_the_one_the_page_states(self):
        page = (Path(__file__).resolve().parent.parent / "process" / "verification.md").read_text()
        self.assertIn(f"({tier0.VERIFIED_MAX_AGE_DAYS} unless", page)  # the default limit; handbook.cfg may change it

    def test_the_sweep_is_run_by_tier_0(self):
        names = {n.id for n in ast.walk(ast.parse(inspect.getsource(tier0.selected_sweeps))) if isinstance(n, ast.Name)}
        self.assertIn("sweep_verification_age", names)
        self.assertIn("sweep_first_run", names)


class IndexFieldTests(unittest.TestCase):
    """`summary:` and `keywords:` of the pages that INDEX.md lists (scripts/make-index.sh)."""

    def sweep(self, fx):
        r = blank()
        tier0.sweep_index_fields(r)
        return r

    def test_a_page_without_summary_is_a_warning_and_a_page_with_one_is_not(self):
        with FixtureRepo() as fx:
            fx.page("operations/a.md", frontmatter=indexed_front(""))
            fx.page("operations/b.md", frontmatter=indexed_front("summary: What the page answers\nkeywords: page\n"))
            r = self.sweep(fx)
            self.assertEqual(checks(r, "warning"), ["missing-summary"])
            self.assertIn("operations/a.md", r["warning"][0]["detail"])
            self.assertEqual(r["blocking"], [])

    def test_an_empty_summary_counts_as_missing(self):
        with FixtureRepo() as fx:
            fx.page("process/a.md", frontmatter=indexed_front("summary:\n"))
            self.assertEqual(checks(self.sweep(fx), "warning"), ["missing-summary"])

    def test_a_summary_of_160_characters_passes_and_161_blocks(self):
        with FixtureRepo() as fx:
            fx.page("operations/ok.md", frontmatter=indexed_front("summary: " + "a" * 160 + "\n"))
            r = self.sweep(fx)
            self.assertEqual((checks(r), checks(r, "warning")), ([], []))
        with FixtureRepo() as fx:
            fx.page("operations/long.md", frontmatter=indexed_front("summary: " + "a" * 161 + "\n"))
            r = self.sweep(fx)
            self.assertEqual(checks(r), ["summary-too-long"])
            self.assertIn("161", r["blocking"][0]["detail"])

    def test_keywords_over_the_limit_block(self):
        with FixtureRepo() as fx:
            fx.page("operations/a.md", frontmatter=indexed_front("summary: s\nkeywords: " + ", ".join(["word"] * 30) + "\n"))
            self.assertEqual(checks(self.sweep(fx)), ["keywords-too-long"])
        with FixtureRepo() as fx:
            fx.page("operations/a.md", frontmatter=indexed_front("summary: s\nkeywords: " + ", ".join(["word"] * 10) + "\n"))
            self.assertEqual(checks(self.sweep(fx)), [])

    def test_a_value_the_script_would_read_differently_from_the_parser_blocks(self):
        for extra in ('summary: "quoted"\n', "summary: 'quoted'\n", "summary: text # a comment\n", "summary: one | two\n",
                      "summary: >\n  folded text\n", "summary: 2026\n", "summary: s\nkeywords: a | b\n", 'summary: s\nkeywords: "a, b"\n'):
            with self.subTest(extra=extra), FixtureRepo() as fx:
                fx.page("reference/a.md", frontmatter=indexed_front(extra))
                self.assertEqual(checks(self.sweep(fx)), ["frontmatter-not-plain"])

    def test_a_plain_value_with_a_comma_a_hyphen_and_a_hash_without_a_space_passes(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", "# page\n\nX-Y works with C# under a limit.\n", frontmatter=indexed_front("summary: How X-Y works, with C# and a 50% limit (since 2026-10-27)\nkeywords: x-y, c#, limit\n"))
            r = self.sweep(fx)
            self.assertEqual((checks(r), checks(r, "warning")), ([], []))

    def test_a_second_colon_in_a_summary_is_a_broken_front_matter(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", frontmatter=indexed_front("summary: Two colons: break the parser\n"))
            r = blank()
            tier0.sweep_yaml_frontmatter(r)
            self.assertEqual(checks(r), ["broken-frontmatter-yaml"])

    def test_a_keyword_the_page_never_mentions_is_a_warning_and_one_it_mentions_is_not(self):
        with FixtureRepo() as fx:
            fx.page("operations/a.md", "# a\n\nThe tunnel client reads the Envoy image.\n",
                    frontmatter=indexed_front("summary: s\nkeywords: Envoy, ImagePullBackOff\n"))
            r = self.sweep(fx)
            self.assertEqual(checks(r, "warning"), ["keyword-not-in-page"])
            self.assertIn("ImagePullBackOff", r["warning"][0]["detail"])
            self.assertEqual(r["blocking"], [])
        with FixtureRepo() as fx:
            fx.page("operations/a.md", "# a\n\nThe tunnel client reads the Envoy image and shows ImagePullBackOff.\n",
                    frontmatter=indexed_front("summary: s\nkeywords: envoy, imagepullbackoff\n"))
            r = self.sweep(fx)
            self.assertEqual((checks(r), checks(r, "warning")), ([], []))

    def test_a_keyword_found_only_on_the_keywords_line_does_not_count(self):
        with FixtureRepo() as fx:
            fx.page("operations/a.md", "# a\n\nNothing about it.\n", frontmatter=indexed_front("summary: s\nkeywords: onlyhere\n"))
            self.assertEqual(checks(self.sweep(fx), "warning"), ["keyword-not-in-page"])

    def test_a_keyword_that_only_the_summary_the_header_or_the_sources_mention_is_a_warning(self):
        for label, kwargs in (
            ("summary", dict(body="# a\n\nNothing.\n", frontmatter=indexed_front("summary: gamma question\nkeywords: gamma\n"))),
            ("header", dict(body="# a\n\nNothing.\n", frontmatter=indexed_front("summary: s\nkeywords: n/a\n"))),
            ("sources", dict(body="# a\n\nNothing.\n", frontmatter=indexed_front("summary: s\nkeywords: delta\n"), sources=["delta is only in the sources"])),
        ):
            with self.subTest(where=label), FixtureRepo() as fx:
                fx.page("operations/a.md", **kwargs)
                self.assertEqual(checks(self.sweep(fx), "warning"), ["keyword-not-in-page"])
        with FixtureRepo() as fx:
            fx.page("operations/a.md", "# a\n\nThe delta lives in the text.\n", frontmatter=indexed_front("summary: s\nkeywords: delta\n"), sources=["delta"])
            self.assertEqual(checks(self.sweep(fx), "warning"), [])

    def test_pages_outside_the_index_folders_are_not_asked_for_a_summary(self):
        with FixtureRepo() as fx:
            fx.page("scripts/tools/README.md", frontmatter=indexed_front(""))
            write(fx.root / "README.md", "# readme\n")
            r = self.sweep(fx)
            self.assertEqual((checks(r), checks(r, "warning")), ([], []))


class IndexCurrentTests(unittest.TestCase):
    """INDEX.md equals what scripts/make-index.sh prints (the script itself is tested in test_make_index.py)."""

    def sweep(self):
        r = blank()
        tier0.sweep_index_current(r)
        return r

    def generate(self, fx):
        out = subprocess.run(["bash", str(tier0.MAKE_INDEX), "--root", str(fx.root)], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_a_current_index_passes(self):
        with FixtureRepo() as fx:
            fx.page("operations/a.md", frontmatter=indexed_front("summary: s\n"))
            self.generate(fx)
            self.assertEqual(checks(self.sweep()), [])

    def test_a_missing_index_blocks(self):
        with FixtureRepo() as fx:
            fx.page("operations/a.md", frontmatter=indexed_front("summary: s\n"))
            self.assertEqual(checks(self.sweep()), ["index-missing"])

    def test_an_index_that_a_changed_summary_left_behind_blocks_and_regenerating_fixes_it(self):
        with FixtureRepo() as fx:
            fx.page("operations/a.md", frontmatter=indexed_front("summary: First\n"))
            self.generate(fx)
            fx.page("operations/a.md", frontmatter=indexed_front("summary: Second\n"))
            r = self.sweep()
            self.assertEqual(checks(r), ["index-out-of-date"])
            self.assertIn("scripts/make-index.sh", r["blocking"][0]["detail"])
            self.generate(fx)
            self.assertEqual(checks(self.sweep()), [])

    def test_a_new_page_not_in_the_index_blocks(self):
        with FixtureRepo() as fx:
            fx.page("operations/a.md", frontmatter=indexed_front("summary: s\n"))
            self.generate(fx)
            fx.page("operations/b.md", frontmatter=indexed_front("summary: s\n"))
            self.assertEqual(checks(self.sweep()), ["index-out-of-date"])

    def test_index_md_needs_no_front_matter_and_is_a_valid_link_target(self):
        with FixtureRepo() as fx:
            write(fx.root / "INDEX.md", "# INDEX\n")
            write(fx.root / "README.md", "[the index](INDEX.md)\n")
            r = blank()
            tier0.sweep_yaml_frontmatter(r)
            tier0.sweep_link_integrity(r)
            self.assertEqual((checks(r), checks(r, "warning")), ([], []))


class MermaidTests(unittest.TestCase):
    def diagram(self, body, caption="As of 2026-10-06.", fence_lang="mermaid", close=True):
        text = "# page\n\n" + (caption + "\n\n" if caption else "") + FENCE + fence_lang + "\n" + body + "\n" + (FENCE + "\n" if close else "")
        return text

    def run_sweep(self, text):
        with FixtureRepo() as fx:
            fx.page("architecture/d.md", text)
            r = blank()
            tier0.sweep_mermaid(r)
            return r

    def test_a_good_diagram_with_a_date_is_clean(self):
        r = self.run_sweep(self.diagram("flowchart LR\n  A --> B"))
        self.assertEqual((r["blocking"], r["warning"]), ([], []))

    def test_an_unclosed_block_blocks(self):
        r = self.run_sweep(self.diagram("flowchart LR\n  A --> B", close=False))
        self.assertEqual(checks(r), ["mermaid-unclosed"])

    def test_text_that_is_not_a_diagram_type_blocks(self):
        r = self.run_sweep(self.diagram("just some words"))
        self.assertEqual(checks(r), ["mermaid-unknown-type"])

    def test_an_empty_block_blocks(self):
        r = self.run_sweep(self.diagram(""))
        self.assertEqual(checks(r), ["mermaid-empty"])

    def test_a_diagram_without_a_date_only_warns(self):
        r = self.run_sweep(self.diagram("sequenceDiagram\n  A->>B: hi", caption=""))
        self.assertEqual((r["blocking"], [f["check"] for f in r["warning"]]), ([], ["mermaid-no-date"]))

    def test_a_comment_line_before_the_type_is_allowed(self):
        r = self.run_sweep(self.diagram("%% note\nflowchart TB\n  A --> B"))
        self.assertEqual((r["blocking"], r["warning"]), ([], []))

    def test_other_code_blocks_are_not_looked_at(self):
        r = self.run_sweep("# page\n\n" + FENCE + "bash\nnot a diagram\n" + FENCE + "\n")
        self.assertEqual((r["blocking"], r["warning"]), ([], []))

def chars(*codepoints: int) -> str:
    """Characters built from code points, so that this file holds none of the characters the language sweep detects."""
    return "".join(chr(c) for c in codepoints)


class NonEnglishTextTests(unittest.TestCase):
    """CLAUDE.md, "Records are in English and are formulations, not conversations": a letter outside the Latin alphabet blocks."""

    CYRILLIC = chars(0x0420, 0x0435, 0x0442, 0x0440, 0x043E)
    CJK = chars(0x4E2D, 0x6587)
    GREEK = chars(0x03B1, 0x03B2)
    ARABIC_LETTER = chars(0x0627, 0x0644)
    ARABIC_LETTER_MARK = chars(0x061C)
    # Not letters, or Latin letters: all of these must pass.
    ACCENTED_LATIN = chars(0x00E9, 0x00FC, 0x00F1, 0x00C5, 0x0142, 0x00DF)
    SYMBOLS = chars(0x2192, 0x21D2, 0x2500, 0x2502, 0x2514, 0x2713, 0x00B0, 0x00D7, 0x2264, 0x1F600, 0x1F680)
    ZERO_WIDTH = chars(0x200B, 0x200C, 0x200D, 0xFEFF, 0x2060)
    OTHER_LATIN = chars(0xFF21, 0xFF42, 0x00B5, 0x00AA, 0x00BA, 0xFB01)

    def run_sweep(self, relpath: str, content: str):
        with FixtureRepo() as fx:
            write(fx.root / relpath, content)
            r = blank()
            tier0.sweep_non_english_text(r)
            return r

    def test_a_cyrillic_line_blocks(self):
        r = self.run_sweep("reference/a.md", "# page\n\nA line with " + self.CYRILLIC + " in it.\n")
        self.assertEqual(checks(r), ["non-english-text"])

    def test_a_cjk_line_blocks(self):
        r = self.run_sweep("reference/a.md", "# page\n\n" + self.CJK + "\n")
        self.assertEqual(checks(r), ["non-english-text"])

    def test_a_greek_line_blocks(self):
        r = self.run_sweep("reference/a.md", "# page\n\n" + self.GREEK + "\n")
        self.assertEqual(checks(r), ["non-english-text"])

    def test_an_arabic_letter_blocks(self):
        r = self.run_sweep("reference/a.md", "# page\n\n" + self.ARABIC_LETTER + "\n")
        self.assertEqual(checks(r), ["non-english-text"])

    def test_the_arabic_letter_mark_blocks(self):
        r = self.run_sweep("reference/a.md", "# page\n\ntext" + self.ARABIC_LETTER_MARK + "more\n")
        self.assertEqual(checks(r), ["non-english-text"])

    def test_arrows_box_drawing_emoji_and_symbols_pass(self):
        r = self.run_sweep("reference/a.md", "# page\n\n" + self.SYMBOLS + "\n")
        self.assertEqual(checks(r), [])

    def test_accents_on_latin_letters_pass(self):
        r = self.run_sweep("reference/a.md", "# page\n\ncaf" + self.ACCENTED_LATIN + "\n")
        self.assertEqual(checks(r), [])

    def test_zero_width_characters_pass(self):
        r = self.run_sweep("reference/a.md", "# page\n\nword" + self.ZERO_WIDTH + "word\n")
        self.assertEqual(checks(r), [])

    def test_fullwidth_and_ligature_latin_letters_pass(self):
        r = self.run_sweep("reference/a.md", "# page\n\n" + self.OTHER_LATIN + "\n")
        self.assertEqual(checks(r), [])

    def test_the_finding_names_the_line_and_the_script_but_never_the_text(self):
        r = self.run_sweep("reference/a.md", "# page\n\nfine\n" + self.CYRILLIC + "\n")
        self.assertEqual(len(r["blocking"]), 1)
        detail = r["blocking"][0]["detail"]
        self.assertIn("reference/a.md:4", detail)
        self.assertIn("CYRILLIC", detail)
        self.assertNotIn(self.CYRILLIC, detail)

    def test_every_kind_of_text_file_is_read_not_only_markdown(self):
        for relpath in ("scripts/x.py", ".github/workflows/x.yml", "scripts/x.sh", "reference/x.json", "reference/x.txt", ".githooks/pre-commit"):
            with self.subTest(relpath=relpath):
                r = self.run_sweep(relpath, "# comment " + self.CYRILLIC + "\n")
                self.assertEqual(checks(r), ["non-english-text"])

    def test_a_binary_file_is_skipped(self):
        with FixtureRepo() as fx:
            (fx.root / "reference").mkdir()
            (fx.root / "reference" / "blob.bin").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xd8\x80")
            (fx.root / "reference" / "pic.png").write_bytes(self.CYRILLIC.encode("utf-8"))
            r = blank()
            tier0.sweep_non_english_text(r)
            self.assertEqual(checks(r), [])

    def test_a_text_file_in_another_encoding_is_a_finding_not_a_pass(self):
        samples = {
            "latin1.md": "caf\u00e9 and more text\n".encode("latin-1"),
            "sjis.md": chars(0x65E5, 0x672C, 0x8A9E).encode("shift_jis"),
            "gbk.md": chars(0x4E2D, 0x6587).encode("gbk"),
            "utf16.md": "# page\n".encode("utf-16"),
        }
        for name, data in samples.items():
            with self.subTest(name=name), FixtureRepo() as fx:
                (fx.root / "reference").mkdir()
                (fx.root / "reference" / name).write_bytes(data)
                r = blank()
                tier0.sweep_non_english_text(r)
                self.assertEqual(checks(r), ["non-english-text"])
                self.assertIn("not valid UTF-8", r["blocking"][0]["detail"])

    def test_a_file_name_with_a_foreign_letter_is_a_finding(self):
        r = self.run_sweep("reference/" + self.CYRILLIC + ".md", "# page\n")
        self.assertEqual(checks(r), ["non-english-text"])
        self.assertIn("file name", r["blocking"][0]["detail"])

    def test_direction_controls_fail_but_the_left_and_right_marks_pass(self):
        for cp in (0x061C, 0x202A, 0x202B, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069):
            with self.subTest(codepoint=hex(cp)):
                r = self.run_sweep("reference/a.md", "# page\n\ntext" + chr(cp) + "more\n")
                self.assertEqual(checks(r), ["non-english-text"])
        r = self.run_sweep("reference/a.md", "# page\n\ntext" + chars(0x200E, 0x200F) + "more\n")
        self.assertEqual(checks(r), [])

    def test_signs_of_units_and_modifier_letters_of_latin_pass(self):
        r = self.run_sweep("reference/a.md", "# page\n\n" + chars(0x03BC) + "s " + chars(0x2126, 0x212A, 0x212B) + " d" + chars(0x02BC) + "etat " + chars(0x1D43) + "\n")
        self.assertEqual(checks(r), [])

    def test_a_modifier_letter_of_another_alphabet_still_fails(self):
        r = self.run_sweep("reference/a.md", "# page\n\n" + chars(0x1D78) + "\n")
        self.assertEqual(checks(r), ["non-english-text"])

    def test_line_numbers_are_those_of_an_editor(self):
        # U+2028 is not a line break for an editor, so the foreign line is line 4 and not line 5.
        r = self.run_sweep("reference/a.md", "# page\n\ntext" + chars(0x2028) + "more\n" + self.CYRILLIC + "\n")
        self.assertIn("reference/a.md:4:", r["blocking"][0]["detail"])

    def test_in_a_git_repository_only_tracked_files_are_read(self):
        with FixtureRepo() as fx:
            write(fx.root / "tracked.md", "# page\n\n" + self.CYRILLIC + "\n")
            write(fx.root / "scratch.md", "# page\n\n" + self.CYRILLIC + "\n")
            subprocess.run(["git", "init", "-q"], cwd=fx.root, check=True)
            subprocess.run(["git", "add", "tracked.md"], cwd=fx.root, check=True)
            r = blank()
            tier0.sweep_non_english_text(r)
            self.assertEqual([f["detail"].split(":")[0] for f in r["blocking"]], ["tracked.md"])

    def test_the_sources_of_the_sweep_hold_none_of_what_it_detects(self):
        from common import foreign_scripts
        for path in sorted(Path(__file__).resolve().parent.glob("*.py")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertEqual(foreign_scripts(line), [], f"{path.name}:{lineno}")


class QuotedMessageTests(unittest.TestCase):
    """The warning on phrases that introduce the quotation of a person. It never blocks."""

    def run_sweep(self, body: str):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", body)
            r = blank()
            tier0.sweep_quoted_message(r)
            return r

    def assertWarns(self, body: str):
        r = self.run_sweep(body)
        self.assertEqual((r["blocking"], checks(r, "warning")), ([], ["quoted-message"]), body)

    def assertQuiet(self, body: str):
        r = self.run_sweep(body)
        self.assertEqual((r["blocking"], r["warning"]), ([], []), body)

    def test_a_person_and_a_speech_verb_followed_by_a_quotation_warns(self):
        self.assertWarns('The user said "do it now" about the plan.\n')
        self.assertWarns('The SRE asked: "can this wait until Monday?"\n')
        self.assertWarns('The developer told us that "the build is fine".\n')
        self.assertWarns('She answered, and then added \u201cdone\u201d.\n')

    def test_wrote_or_replied_followed_by_a_quotation_warns(self):
        self.assertWarns('He wrote: "see the attached".\n')
        self.assertWarns('They replied "later".\n')

    def test_users_and_guillemets_are_covered_but_a_session_log_is_not_a_speaker(self):
        self.assertWarns('Users said \u00abdo it\u00bb in the thread.\n')
        self.assertQuiet('A session log that says "start with the connector" is a log line.\n')
        self.assertQuiet('The session folder that says "kept" is a field name.\n')

    def test_the_introducing_phrases_warn(self):
        self.assertWarns("The decision, in his own words, was to wait.\n")
        self.assertWarns("The decision in the owner's words was to wait.\n")
        self.assertWarns("These are the quoted words of the owner.\n")
        self.assertWarns("The decision in the words of the owner was to wait.\n")
        self.assertWarns("These are the exact words of the owner.\n")
        self.assertWarns("The text was copied word for word.\n")
        self.assertWarns("The text is given verbatim.\n")
        self.assertWarns("The decision, as relayed, was to wait.\n")
        self.assertWarns("The decision was relayed by another session.\n")
        self.assertWarns("The sentence was translated from the original.\n")

    def test_a_sentence_without_a_quotation_or_a_phrase_is_quiet(self):
        self.assertQuiet("The owner decided on 2026-10-23 that traces are kept for 365 days.\n")
        self.assertQuiet("The user asked for nothing else, and the SRE agreed.\n")

    def test_a_page_or_a_log_that_says_something_is_not_a_person(self):
        self.assertQuiet('The page says "not a valid command" for that name.\n')
        self.assertQuiet('The pull request body said "All CI checks pass".\n')
        self.assertQuiet('The Users page says "Failed to load tenant members".\n')

    def test_code_in_backticks_and_fenced_blocks_is_not_looked_at(self):
        self.assertQuiet('Run `echo "the user said hello"` to see it.\n')
        self.assertQuiet("```bash\necho 'the user said \"hello\"'\n```\n")

    def test_the_finding_names_the_line_and_the_phrase_but_never_the_text(self):
        r = self.run_sweep('# page\n\nThe user said "a secret plan".\n')
        detail = r["warning"][0]["detail"]
        self.assertIn("reference/a.md:", detail)
        self.assertNotIn("secret plan", detail)


GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false"]


def git_repo_with_file(path: Path, relpath: str) -> str:
    """A git repository at `path` with one commit that holds `relpath`; returns the abbreviated hash of that commit."""
    write(path / relpath, "a = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "add", relpath], cwd=path, check=True)
    subprocess.run(["git", *GIT_IDENTITY, "commit", "-q", "-m", "one"], cwd=path, check=True)
    return subprocess.run(["git", "log", "-1", "--format=%h", "--", relpath], cwd=path, check=True, capture_output=True, text=True).stdout.strip()


class SiblingCloneInAHookTests(unittest.TestCase):
    """A git hook exports GIT_DIR and GIT_INDEX_FILE for the repository being committed; `git -C OTHER` must still read the other one."""

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in tier0.GIT_REPOSITORY_VARIABLES}

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_run_in_sibling_answers_from_the_other_repository_inside_a_hook(self):
        # The failure the helper prevents, shown with the plain run(): with GIT_DIR set, `git -C` answers from that repository.
        with FixtureRepo() as fx:
            pin = git_repo_with_file(fx.tmp / "other-repo", "src/x.txt")
            subprocess.run(["git", "init", "-q"], cwd=fx.root, check=True)
            os.environ["GIT_DIR"] = str(fx.root / ".git")
            args = ["git", "-C", str(fx.tmp / "other-repo"), "log", "-1", "--format=%h", "--", "src/x.txt"]
            self.assertEqual(tier0.run(args)[1].strip(), "")
            self.assertEqual(tier0.run_in_sibling(args)[1].strip(), pin)


DEFAULT_SETTINGS = {
    "record_style": "strict",
    "verified_max_age_days": 30,
    "index_folders": ("architecture", "operations", "process", "reference"),
    "record_folders": ("operations/releases", "architecture/retrospectives"),
}


class SettingsTests(unittest.TestCase):
    """handbook.cfg: the defaults, the two keys, and a mistake that is reported and not ignored."""

    def load(self, text=None):
        with FixtureRepo() as fx:
            if text is not None:
                write(fx.root / "handbook.cfg", text)
            return load_settings(fx.root)

    def test_a_missing_file_means_the_defaults(self):
        self.assertEqual(self.load(), (DEFAULT_SETTINGS, []))

    def test_both_keys_are_read(self):
        got = self.load("[handbook]\nrecord_style = off\nverified_max_age_days = 90\n")
        self.assertEqual(got, ({**DEFAULT_SETTINGS, "record_style": "off", "verified_max_age_days": 90}, []))

    def test_comments_are_skipped_and_a_value_may_hold_a_hash(self):
        got = self.load("# a note\n[handbook]\n# another\nrecord_style = strict\n")
        self.assertEqual(got, (DEFAULT_SETTINGS, []))

    def test_every_mistake_is_a_problem_and_keeps_the_default(self):
        for text, expected in (
            ("[handbook]\nrecord_style = loose\n", "record_style is 'loose'"),
            ("[handbook]\nverified_max_age_days = 0\n", "verified_max_age_days is '0'"),
            ("[handbook]\nverified_max_age_days = 3.5\n", "verified_max_age_days is '3.5'"),
            ("[handbook]\nverified_max_age_days = -4\n", "verified_max_age_days is '-4'"),
            ("[handbook]\nrecord_stile = off\n", "unknown key record_stile"),
            ("[other]\nrecord_style = off\n", "unknown section [other]"),
            ("record_style = off\n", "File contains no section headers"),
        ):
            settings, problems = self.load(text)
            self.assertEqual(settings, DEFAULT_SETTINGS, text)
            self.assertEqual(len(problems), 1, text)
            self.assertIn(expected, problems[0], text)

    def test_the_sweep_reports_a_problem_as_blocking(self):
        with FixtureRepo() as fx:
            write(fx.root / "handbook.cfg", "[handbook]\nrecord_stile = off\n")
            r = blank()
            tier0.sweep_settings(r)
            self.assertEqual(checks(r), ["settings-problem"])

    def test_record_style_off_leaves_out_exactly_the_three_record_sweeps(self):
        strict = {s.__name__ for s in tier0.selected_sweeps({"record_style": "strict"})}
        off = {s.__name__ for s in tier0.selected_sweeps({"record_style": "off"})}
        self.assertEqual(strict - off, set(tier0.RECORD_STYLE_SWEEPS))
        self.assertEqual(off - strict, set())

    def test_the_age_limit_of_the_file_is_the_one_the_sweep_uses(self):
        with FixtureRepo() as fx:
            write(fx.root / "handbook.cfg", "[handbook]\nverified_max_age_days = 10\n")
            fx.page("operations/a.md", frontmatter="status: verified\nlast_verified: 2030-01-01\nverify_with: n/a\nsources_count: 1")
            r = blank()
            tier0.sweep_verification_age(r, today=date(2030, 1, 12))
            self.assertEqual(checks(r, "warning"), ["verification-aged"])
            r = blank()
            tier0.sweep_verification_age(r, today=date(2030, 1, 11))
            self.assertEqual(checks(r, "warning"), [])


class FolderSettingsTests(unittest.TestCase):
    """`index_folders` and `record_folders` of handbook.cfg: what is read, what is refused, and that the sweeps use them."""

    def load(self, text):
        with FixtureRepo() as fx:
            write(fx.root / "handbook.cfg", text)
            return load_settings(fx.root)

    def test_the_lists_are_read_with_spaces_and_a_trailing_slash_dropped_and_a_nested_path_allowed(self):
        settings, problems = self.load("[handbook]\nindex_folders = docs/handbook/ , runbooks,reference\nrecord_folders = runbooks/postmortems\n")
        self.assertEqual(problems, [])
        self.assertEqual(settings["index_folders"], ("docs/handbook", "runbooks", "reference"))
        self.assertEqual(settings["record_folders"], ("runbooks/postmortems",))

    def test_no_record_folder_is_allowed_and_no_index_folder_is_not(self):
        settings, problems = self.load("[handbook]\nrecord_folders =\n")
        self.assertEqual((settings["record_folders"], problems), ((), []))
        settings, problems = self.load("[handbook]\nindex_folders =\n")
        self.assertEqual(settings["index_folders"], DEFAULT_SETTINGS["index_folders"])
        self.assertEqual(len(problems), 1)
        self.assertIn("needs at least one folder", problems[0])

    def test_every_bad_list_is_one_problem_and_keeps_the_default(self):
        for value, expected in (
            ("a,,b", "has ''"),
            ("/abs", "has '/abs'"),
            ("../up", "has '../up'"),
            ("docs/../up", "has 'docs/../up'"),
            (".hidden", "has '.hidden'"),
            ("docs/.cache", "has 'docs/.cache'"),
            ("my folder", "has 'my folder'"),
            ("a\\b", "has 'a\\\\b'"),
            ("a,b,a", "lists 'a' twice"),
            ("docs,docs/api", "'docs/api', which is inside 'docs'"),
        ):
            settings, problems = self.load(f"[handbook]\nindex_folders = {value}\n")
            self.assertEqual(settings["index_folders"], DEFAULT_SETTINGS["index_folders"], value)
            self.assertEqual(len(problems), 1, value)
            self.assertIn(expected, problems[0], value)

    def test_the_index_sweep_reads_the_pages_of_the_configured_folders_only(self):
        with FixtureRepo() as fx:
            write(fx.root / "handbook.cfg", "[handbook]\nindex_folders = docs\n")
            fx.page("docs/a.md", frontmatter=indexed_front(""))
            fx.page("operations/b.md", frontmatter=indexed_front(""))
            r = blank()
            tier0.sweep_index_fields(r)
            self.assertEqual([f["detail"].split(":")[0] for f in r["warning"]], ["docs/a.md"])

    def test_a_record_folder_of_the_file_does_not_age_and_the_default_one_does_once_it_is_replaced(self):
        pages = {"journal/x.md": ("verified", date(2030, 1, 1)), "operations/releases/r.md": ("verified", date(2030, 1, 1))}
        today = date(2030, 3, 1)
        self.assertEqual([d.split(":")[0] for _, _, d in tier0.age_findings(pages, today, 30, ("journal/",))], ["operations/releases/r.md"])
        self.assertEqual([d.split(":")[0] for _, _, d in tier0.age_findings(pages, today)], ["journal/x.md"])
        with FixtureRepo() as fx:
            write(fx.root / "handbook.cfg", "[handbook]\nrecord_folders = journal\n")
            fx.page("journal/x.md", frontmatter="status: verified\nlast_verified: 2000-01-01\nverify_with: n/a\nsources_count: 1")
            fx.page("operations/releases/r.md", frontmatter="status: verified\nlast_verified: 2000-01-01\nverify_with: n/a\nsources_count: 1")
            r = blank()
            tier0.sweep_verification_age(r, today=date(2030, 1, 1))
            self.assertEqual([f["detail"].split(":")[0] for f in r["warning"]], ["operations/releases/r.md"])

    def test_a_source_that_starts_with_a_configured_folder_is_looked_up_in_this_repo(self):
        with FixtureRepo() as fx:
            write(fx.root / "handbook.cfg", "[handbook]\nindex_folders = docs/handbook\n")
            fx.page("docs/handbook/b.md")
            fx.page("docs/handbook/a.md", sources=["docs/handbook/b.md", "docs/handbook/gone.md"])
            r = blank()
            tier0.sweep_sources_path_exists(r)
            self.assertEqual(len(r["warning"]), 1)
            self.assertIn("docs/handbook/gone.md", r["warning"][0]["detail"])


class ProjectFilesTests(unittest.TestCase):
    """The root files of a project (README, CONTRIBUTING, SECURITY) and the folders of tooling (.github) are not pages."""

    def test_a_root_file_is_not_an_orphan_and_the_same_name_in_a_folder_is(self):
        with FixtureRepo() as fx:
            for name in ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md"):
                write(fx.root / name, "# root\n")
            fx.page("reference/SECURITY.md")
            r = blank()
            tier0.sweep_link_integrity(r)
            self.assertEqual([f["detail"] for f in r["warning"]], ["reference/SECURITY.md"])

    def test_a_markdown_file_in_a_folder_that_starts_with_a_dot_is_not_a_page(self):
        with FixtureRepo() as fx:
            write(fx.root / ".github" / "PULL_REQUEST_TEMPLATE.md", "No front matter, and a [broken](link.md)\n")
            write(fx.root / ".venv" / "lib" / "README.md", "# a dependency\n")
            fx.page("reference/a.md")
            self.assertEqual([p.relative_to(fx.root).as_posix() for p in common.iter_markdown_files(fx.root)], ["reference/a.md"])
            r = blank()
            tier0.sweep_yaml_frontmatter(r)
            tier0.sweep_link_integrity(r)
            self.assertEqual(checks(r), [])


class ForeignIdentifierTests(unittest.TestCase):
    """The list of identifiers of another project or handbook that must not appear here."""

    def test_the_list_skips_comments_and_blank_lines_and_flags_what_is_not_a_pattern(self):
        patterns, bad = tier0.read_foreign_identifiers("# a note\n\nalpha-[0-9]+\n  Beta  \n(unclosed\n.*\n")
        self.assertEqual([p.pattern for p in patterns], ["alpha-[0-9]+", "Beta"])
        self.assertEqual(bad, [5, 6])

    def test_a_pattern_matches_without_regard_to_case_and_reports_the_line_only(self):
        patterns, _ = tier0.read_foreign_identifiers("alpha-[0-9]+\n")
        got = tier0.foreign_identifier_findings(patterns, {"a.md": "fine\nsee ALPHA-42 here\n", "b.md": "alpha only\n"})
        self.assertEqual(got, [("a.md", 2)])

    def test_the_sweep_blocks_a_hit_anywhere_but_not_in_the_list(self):
        with FixtureRepo() as fx:
            write(fx.root / "scripts" / "foreign-identifiers.txt", "# the only place that names them\nalpha-[0-9]+\n")
            fx.page("reference/clean.md", "# clean\n")
            fx.page("reference/dirty.md", "# dirty\n\nuses alpha-7\n")
            write(fx.root / "notes" / "x.txt", "alpha-9\n")
            r = blank()
            tier0.sweep_foreign_identifiers(r)
            hit = (fx.root / "reference/dirty.md").read_text().splitlines().index("uses alpha-7") + 1
            self.assertEqual(sorted(f["detail"] for f in r["blocking"]), ["notes/x.txt:1", f"reference/dirty.md:{hit}"])
            self.assertEqual(set(checks(r)), {"foreign-identifier"})

    def test_a_bad_line_is_blocking_and_no_list_means_nothing_to_check(self):
        with FixtureRepo() as fx:
            r = blank()
            tier0.sweep_foreign_identifiers(r)
            self.assertEqual(checks(r), [])
            write(fx.root / "scripts" / "foreign-identifiers.txt", "(unclosed\n")
            tier0.sweep_foreign_identifiers(r)
            self.assertEqual(checks(r), ["foreign-identifiers-bad-line"])


class FirstRunTests(unittest.TestCase):
    """While FIRST-RUN.md exists the interview is pending; afterwards the page it writes must exist."""

    def test_the_states(self):
        self.assertEqual([c for _, c, _ in tier0.first_run_findings(True, False)], ["first-run-pending"])
        self.assertEqual([c for _, c, _ in tier0.first_run_findings(True, True)], ["first-run-pending"])
        self.assertEqual([c for _, c, _ in tier0.first_run_findings(False, False)], ["sources-of-truth-missing"])
        self.assertEqual(tier0.first_run_findings(False, True), [])

    def test_both_are_warnings_never_blocking(self):
        for pending, page in ((True, False), (False, False)):
            self.assertEqual({b for b, _, _ in tier0.first_run_findings(pending, page)}, {"warning"})

    def test_the_sweep_reads_the_two_files(self):
        with FixtureRepo() as fx:
            r = blank()
            tier0.sweep_first_run(r)
            self.assertEqual(checks(r, "warning"), ["sources-of-truth-missing"])
            write(fx.root / "FIRST-RUN.md", "# first run\n")
            r = blank()
            tier0.sweep_first_run(r)
            self.assertEqual(checks(r, "warning"), ["first-run-pending"])
            (fx.root / "FIRST-RUN.md").unlink()
            fx.page("reference/sources-of-truth.md", "# sources\n")
            r = blank()
            tier0.sweep_first_run(r)
            self.assertEqual(checks(r, "warning"), [])


class SanityTests(unittest.TestCase):
    def test_a_missing_pyyaml_is_a_clear_message_and_not_a_traceback(self):
        code = "import sys; sys.modules['yaml'] = None; sys.path.insert(0, sys.argv[1]); import common"
        done = subprocess.run([sys.executable, "-I", "-c", code, str(Path(__file__).parent)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("PyYAML is required: pip install -r requirements.txt", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_entropy_sweep_flags_a_long_hex_literal(self):
        with FixtureRepo() as fx:
            fx.page("reference/a.md", 'value = "' + "a1" * 20 + '"\n')
            r = blank()
            tier0.sweep_entropy(r)
            self.assertEqual(checks(r), ["entropy"])

    def test_secret_pattern_skips_a_bare_boolean_but_not_a_value_that_begins_like_one(self):
        from common import SECRET_PATTERN
        self.assertIsNone(SECRET_PATTERN.search("automountServiceAccount" + "Token: false"))
        self.assertIsNone(SECRET_PATTERN.search("allow_" + "token = TRUE,"))
        self.assertIsNotNone(SECRET_PATTERN.search("pass" + "word = truebluepassphrase"))
        self.assertIsNotNone(SECRET_PATTERN.search("to" + 'ken: "true"'))
        self.assertIsNotNone(SECRET_PATTERN.search("Never paste a tok" + "en:"))

    def test_secret_pattern_matches_an_assignment_and_allows_a_placeholder(self):
        from common import SECRET_ALLOW, SECRET_PATTERN
        # Built from parts so this fixture does not trip the secret sweep it tests.
        hit = "api" + "_key = abc"
        ok = "API" + '_KEY="REDACTED"'
        self.assertTrue(SECRET_PATTERN.search(hit) and not SECRET_ALLOW.search(hit))
        self.assertTrue(SECRET_PATTERN.search(ok) and SECRET_ALLOW.search(ok))


if __name__ == "__main__":
    unittest.main()
