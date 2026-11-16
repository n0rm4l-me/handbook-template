#!/usr/bin/env python3
"""Tests for scripts/make-index.sh, in the style of test_page_outline.py: a passing case and a failing case for each rule.

The script is run as a program (a shell script with one awk program inside) on a throwaway handbook, so that the sizes and
the order are known. It is also run under /bin/bash, which is bash 3.2 on macOS.

Run with: python3 scripts/test_make_index.py
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import INDEX_FOLDERS, load_settings, under_folders  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "make-index.sh"
FENCE = "`" * 3


def front(status="unverified", extra="") -> str:
    return ("---\nstatus: " + status + "\nlast_verified: 2026-10-27\nverify_with: n/a\n" + extra +
            "sources:\n  - team knowledge (2026-10-27), unverified: a claim\n---\n")


def run(root: Path, *args, shell="bash"):
    return subprocess.run([shell, str(SCRIPT), "--root", str(root), *args], capture_output=True, text=True, timeout=30)


def rows(stdout: str):
    """The table rows as lists of the six cells."""
    found = []
    for line in stdout.splitlines():
        if line.startswith("| ") and not line.startswith("| Page ") and not line.startswith("|---"):
            found.append([c.strip() for c in line.strip().strip("|").split(" | ")])
    return found


class IndexTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def page(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def index(self, *args) -> str:
        r = run(self.root, "--stdout", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    # --- the passing cases ---

    def test_a_row_has_the_path_title_status_size_summary_and_keywords(self):
        self.page("operations/a.md", front("verified", "summary: How the thing runs now and what to do when it stops\nkeywords: thing, restart, probe\n") + "\n# The thing\n\nBody.\n")
        got = rows(self.index())
        self.assertEqual(got, [["operations/a.md", "The thing", "verified", "1", "How the thing runs now and what to do when it stops", "thing, restart, probe"]])

    def test_the_size_is_rounded_to_whole_kb_and_is_at_least_one(self):
        def sized(rel, size):
            head = front("verified", "summary: s\n") + "\n# T\n\n"
            self.page(rel, head + "x" * (size - len(head.encode()) - 1) + "\n")
        sized("reference/small.md", 300)
        sized("reference/round_down.md", 2499)
        sized("reference/round_up.md", 2500)
        sized("reference/big.md", 61234)
        kb = {r[0]: r[3] for r in rows(self.index())}
        self.assertEqual(kb, {"reference/small.md": "1", "reference/round_down.md": "2", "reference/round_up.md": "3", "reference/big.md": "61"})

    def test_a_summary_from_the_front_matter_wins_over_the_first_paragraph(self):
        self.page("process/a.md", front(extra="summary: From the front matter\n") + "\n# T\n\nThe first paragraph says something else.\n")
        self.assertEqual(rows(self.index())[0][4], "From the front matter")

    def test_a_page_without_summary_gets_its_first_paragraph_and_no_keywords(self):
        body = ("\n# The title\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- a list item\n\n" + FENCE + "\n# not a title\n" + FENCE +
                "\n\n**Bold start** of the real paragraph,\nwrapped on a second line.\n\nA second paragraph that is not used.\n")
        self.page("operations/a.md", front() + body)
        got = rows(self.index())[0]
        self.assertEqual(got[1], "The title")
        self.assertEqual(got[4], "Bold start of the real paragraph, wrapped on a second line.")
        self.assertEqual(got[5], "")

    def test_a_long_first_paragraph_is_cut_at_a_word_and_stays_valid_utf8(self):
        words = " ".join(["wordy"] * 20 + ["→"] * 10 + ["end"] * 30)
        self.page("operations/a.md", front() + "\n# T\n\n" + words + "\n")
        summary = rows(self.index())[0][4]
        self.assertTrue(summary.endswith("..."))
        self.assertLessEqual(len(summary.encode()), 160)
        self.assertNotIn("  ", summary)
        raw = run(self.root, "--stdout").stdout.encode()
        raw.decode("utf-8")  # raises when a multi-byte character was split

    def test_the_title_is_the_first_heading_outside_a_fenced_block_and_is_cut(self):
        self.page("operations/a.md", front() + "\n" + FENCE + "bash\n# a comment of a script\n" + FENCE + "\n\n# " + "long " * 30 + "\n\n# A second heading\n")
        title = rows(self.index())[0][1]
        self.assertTrue(title.startswith("long long"))
        self.assertTrue(title.endswith("..."))
        self.assertLessEqual(len(title), 64)

    def test_a_page_without_a_heading_is_listed_under_its_path(self):
        self.page("operations/a.md", front(extra="summary: s\n") + "\nJust text.\n")
        self.assertEqual(rows(self.index())[0][1], "operations/a.md")

    def test_a_pipe_in_a_field_does_not_break_the_row(self):
        self.page("operations/a.md", front(extra="summary: one | two\nkeywords: a|b\n") + "\n# T | U\n")
        got = rows(self.index())
        self.assertEqual(got, [["operations/a.md", "T / U", "unverified", "1", "one / two", "a/b"]])

    def test_a_quoted_summary_is_unquoted_and_a_line_of_sources_is_not_a_field(self):
        text = ("---\nstatus: verified\nlast_verified: 2026-10-27\nverify_with: n/a\nsummary: 'Quoted text'\nsources:\n"
                "  - summary: this line belongs to sources\n  - keywords: so does this one\n---\n\n# T\n")
        self.page("operations/a.md", text)
        got = rows(self.index())[0]
        self.assertEqual((got[4], got[5]), ("Quoted text", ""))

    def test_the_rows_are_sorted_by_folder_and_then_by_name(self):
        for rel in ("reference/z.md", "operations/b.md", "operations/releases/r1.md", "architecture/services/s.md", "architecture/overview.md",
                    "architecture/decisions/0002.md", "architecture/decisions/0001.md", "process/p.md", "operations/a.md"):
            self.page(rel, front(extra="summary: s\n") + "\n# T\n")
        self.assertEqual([r[0] for r in rows(self.index())], [
            "architecture/overview.md", "architecture/decisions/0001.md", "architecture/decisions/0002.md", "architecture/services/s.md",
            "operations/a.md", "operations/b.md", "operations/releases/r1.md", "process/p.md", "reference/z.md"])
        headings = re.findall(r"^## (\S+) \((\d+) pages?", self.index(), re.M)
        self.assertEqual(headings, [("architecture/", "1"), ("architecture/decisions/", "2"), ("architecture/services/", "1"),
                                    ("operations/", "2"), ("operations/releases/", "1"), ("process/", "1"), ("reference/", "1")])

    def test_only_the_index_folders_are_listed(self):
        for folder in INDEX_FOLDERS:
            self.page(f"{folder}/a.md", front(extra="summary: s\n") + "\n# T\n")
        for rel in ("README.md", "CLAUDE.md", "CONTRIBUTING.md", "INDEX.md", ".github/PULL_REQUEST_TEMPLATE.md", "scripts/tools/README.md", "other/a.md", "operations/notes.txt"):
            self.page(rel, front(extra="summary: s\n") + "\n# T\n")
        self.assertEqual(sorted(r[0] for r in rows(self.index())), sorted(f"{f}/a.md" for f in INDEX_FOLDERS))

    def test_the_output_is_the_same_on_every_run_and_does_not_depend_on_the_order_of_creation(self):
        names = ["operations/b.md", "operations/a.md", "reference/c.md", "architecture/x.md"]
        for rel in names:
            self.page(rel, front(extra="summary: s\n") + "\n# T\n")
        first = self.index()
        self.assertEqual(first, self.index())
        other = tempfile.TemporaryDirectory()
        try:
            for rel in reversed(names):
                target = Path(other.name) / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((self.root / rel).read_text())
            self.assertEqual(first, run(Path(other.name), "--stdout").stdout)
        finally:
            other.cleanup()

    @unittest.skipUnless(os.path.exists("/bin/bash"), "no /bin/bash")
    def test_the_same_output_under_bin_bash(self):
        self.page("operations/a.md", front(extra="summary: s\nkeywords: k\n") + "\n# T\n")
        self.assertEqual(run(self.root, "--stdout").stdout, run(self.root, "--stdout", shell="/bin/bash").stdout)

    def test_one_page_is_not_two_pages(self):
        self.page("operations/a.md", front(extra="summary: s\n") + "\n# T\n")
        out = self.index()
        self.assertIn("handbook, 1 page.", out)
        self.assertIn("## operations/ (1 page,", out)
        self.assertNotIn("1 pages", out)

    def test_a_page_with_a_space_in_its_name_fails_loudly_and_names_the_file(self):
        self.page("operations/with space.md", front(extra="summary: s\n") + "\n# T\n")
        r = run(self.root, "--stdout")
        self.assertEqual(r.returncode, 1)
        self.assertIn("space or a tab in its name", r.stderr)
        self.assertIn("with space.md", r.stderr)

    def test_an_empty_handbook_gives_a_header_and_no_rows(self):
        out = self.index()
        self.assertIn("0 pages", out)
        self.assertEqual(rows(out), [])

    # --- the folders of handbook.cfg ---

    def cfg(self, text: str):
        (self.root / "handbook.cfg").write_bytes(text.encode())

    def test_the_folders_of_the_config_replace_the_default_ones(self):
        self.cfg("[handbook]\nindex_folders = docs/handbook, runbooks\n")
        for rel in ("docs/handbook/a.md", "docs/handbook/api/b.md", "runbooks/c.md", "operations/d.md", "docs/other/e.md"):
            self.page(rel, front(extra="summary: s\n") + "\n# T\n")
        self.assertEqual([r[0] for r in rows(self.index())], ["docs/handbook/a.md", "docs/handbook/api/b.md", "runbooks/c.md"])

    def test_the_defaults_hold_when_the_file_has_no_key_an_empty_key_or_the_key_in_another_section(self):
        self.page("operations/a.md", front(extra="summary: s\n") + "\n# T\n")
        self.page("docs/b.md", front(extra="summary: s\n") + "\n# T\n")
        for text in ("", "[handbook]\nrecord_style = strict\n", "[handbook]\nindex_folders =\n", "[other]\nindex_folders = docs\n"):
            self.cfg(text)
            self.assertEqual([r[0] for r in rows(self.index())], ["operations/a.md"], text)

    def test_a_folder_that_is_listed_twice_or_inside_another_one_lists_its_pages_once(self):
        self.cfg("[handbook]\nindex_folders = operations, operations/releases, operations\n")
        for rel in ("operations/a.md", "operations/releases/r.md"):
            self.page(rel, front(extra="summary: s\n") + "\n# T\n")
        self.assertEqual([r[0] for r in rows(self.index())], ["operations/a.md", "operations/releases/r.md"])

    def test_a_folder_name_that_is_not_allowed_fails_loudly(self):
        self.page("operations/a.md", front(extra="summary: s\n") + "\n# T\n")
        for value in ("../x", "/abs", ".git", "a//b", "docs/.cache", "my folder", "a*"):
            self.cfg(f"[handbook]\nindex_folders = operations, {value}\n")
            r = run(self.root, "--stdout")
            self.assertEqual(r.returncode, 1, value)
            self.assertIn("index_folders has a folder that is not allowed", r.stderr, value)

    def test_the_script_and_the_python_settings_read_the_same_folders(self):
        pages = ("a/p.md", "b/p.md", "b/c/p.md", "zzz/p.md", "operations/p.md")
        for rel in pages:
            self.page(rel, front(extra="summary: s\n") + "\n# T\n")
        for text in (
            "[handbook]\nindex_folders = a, b/c\n",
            "[handbook]\nindex_folders: a ,b\n",
            "# note\n[handbook]\n# index_folders = zzz\nindex_folders = a/\n",
            "[other]\nindex_folders = zzz\n[handbook]\nindex_folders = a\n",
            "[handbook]\nINDEX_FOLDERS = b\n",
            "[handbook]\r\nindex_folders = a, zzz\r\n",
            "[handbook]\nrecord_style = strict\nindex_folders =    b/c   \nverified_max_age_days = 30\n",
            "[handbook]\nindex_folders = missing, a\n",
        ):
            self.cfg(text)
            settings, _ = load_settings(self.root)
            expected = [rel for rel in sorted(pages) if under_folders(rel, settings["index_folders"])]
            for shell in ("bash", "/bin/bash"):
                if shell == "/bin/bash" and not os.path.exists(shell):
                    continue
                got = run(self.root, "--stdout", shell=shell)
                self.assertEqual(got.returncode, 0, got.stderr)
                self.assertEqual(sorted(r[0] for r in rows(got.stdout)), expected, f"{shell} {text!r}")

    # --- --write and --check: the passing and the failing case ---

    def test_check_passes_on_a_current_index_and_fails_when_a_page_changed(self):
        page = self.page("operations/a.md", front(extra="summary: First wording\n") + "\n# T\n")
        self.assertEqual(run(self.root).returncode, 0)  # --write
        self.assertTrue((self.root / "INDEX.md").is_file())
        ok = run(self.root, "--check")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        page.write_text(front(extra="summary: Second wording\n") + "\n# T\n")
        stale = run(self.root, "--check")
        self.assertEqual(stale.returncode, 1)
        self.assertIn("out of date", stale.stderr)
        self.assertIn("Second wording", stale.stderr)
        self.assertEqual(run(self.root).returncode, 0)
        self.assertEqual(run(self.root, "--check").returncode, 0)

    def test_check_fails_for_a_new_page_a_removed_page_and_a_missing_index(self):
        self.assertEqual(run(self.root, "--check").returncode, 1)  # no INDEX.md yet
        self.page("operations/a.md", front(extra="summary: s\n") + "\n# T\n")
        run(self.root)
        new = self.page("operations/b.md", front(extra="summary: s\n") + "\n# T\n")
        self.assertEqual(run(self.root, "--check").returncode, 1)
        run(self.root)
        new.unlink()
        self.assertEqual(run(self.root, "--check").returncode, 1)

    def test_check_fails_when_the_index_was_edited_by_hand(self):
        self.page("operations/a.md", front(extra="summary: s\n") + "\n# T\n")
        run(self.root)
        index = self.root / "INDEX.md"
        index.write_text(index.read_text().replace("| s |", "| a hand edit |"))
        self.assertEqual(run(self.root, "--check").returncode, 1)

    def test_write_leaves_a_current_index_alone(self):
        self.page("operations/a.md", front(extra="summary: s\n") + "\n# T\n")
        run(self.root)
        before = (self.root / "INDEX.md").stat().st_mtime_ns
        r = run(self.root)
        self.assertIn("is current", r.stdout)
        self.assertEqual((self.root / "INDEX.md").stat().st_mtime_ns, before)

    # --- the usage ---

    def test_a_bad_argument_and_a_missing_root_fail(self):
        r = subprocess.run(["bash", str(SCRIPT), "--nothing"], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage:", r.stderr)
        r = subprocess.run(["bash", str(SCRIPT), "--root"], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 2)
        r = run(self.root / "no-such-folder")
        self.assertEqual(r.returncode, 1)
        self.assertIn("is not a folder", r.stderr)


if __name__ == "__main__":
    unittest.main()
