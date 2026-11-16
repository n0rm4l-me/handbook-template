#!/usr/bin/env python3
"""Tests for scripts/page-outline.sh, in the style of test_tier0.py: a passing case and a failing case for each rule.

The script is run as a program (a shell script with one awk program inside), on pages built in a temporary folder, so
that the sizes are known to the byte. It is also run under /bin/bash, which is bash 3.2 on macOS.

Run with: python3 scripts/test_page_outline.py
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "page-outline.sh"
ROOT = SCRIPT.parent.parent
FENCE = "`" * 3
FRONT = "---\nstatus: unverified\nlast_verified: 2026-10-27\nverify_with: n/a\nsources:\n  - team knowledge (2026-10-27), unverified\n---\n"


def block(heading: str, size: int) -> str:
    """A heading line followed by lines of text, exactly `size` bytes in all."""
    head = heading + "\n"
    filler = size - len(head)
    assert filler >= 0
    body = ""
    while filler > 0:
        line = "x" * min(79, filler - 1) + "\n" if filler > 1 else "\n"
        body += line
        filler -= len(line)
    return head + body


def run(*args, shell="bash"):
    return subprocess.run([shell, str(SCRIPT), *args], capture_output=True, text=True, timeout=30)


def rows(output: str):
    """The table rows as (line, lines, kb, heading)."""
    found = []
    for raw in output.splitlines():
        m = re.match(r"^\s*(\d+)\s+(\d+)\s+(\d+\.\d)\s{2}(.*)$", raw)
        if m:
            found.append((int(m.group(1)), int(m.group(2)), float(m.group(3)), m.group(4)))
    return found


class OutlineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def page(self, text: str, name="page.md") -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    # --- the passing cases ---

    def test_headings_lines_and_sizes(self):
        text = FRONT + "\n" + block("# Title", 1000) + block("## Alpha", 2000) + block("### Beta", 3500) + block("## Gamma", 500)
        page = self.page(text)
        r = run(str(page))
        self.assertEqual(r.returncode, 0, r.stderr)
        got = rows(r.stdout)
        self.assertEqual([g[3] for g in got], ["(front matter)", "# Title", "  ## Alpha", "    ### Beta", "  ## Gamma"])
        self.assertEqual([g[2] for g in got], [round((len(FRONT) + 1) / 1000, 1), 1.0, 2.0, 3.5, 0.5])
        self.assertEqual(got[0][:2], (1, 8))  # seven front matter lines and one blank line
        self.assertEqual(got[1][0], 9)
        self.assertIn(f"{page}: {len(text.encode()) / 1000:.1f} KB, {text.count(chr(10))} lines, 4 headings", r.stdout)

    def test_sections_tile_the_page(self):
        page = self.page(FRONT + "\n" + block("# T", 700) + block("## A", 300) + block("## B", 900) + block("### C", 100))
        r = run(str(page))
        got = rows(r.stdout)
        self.assertEqual(sum(g[1] for g in got), page.read_text().count("\n"))
        self.assertEqual(got[0][0], 1)
        for earlier, later in zip(got, got[1:]):
            self.assertEqual(earlier[0] + earlier[1], later[0])

    def test_hashes_in_a_fenced_block_or_in_the_front_matter_are_not_headings(self):
        front = "---\nstatus: unverified\n# a comment line of the front matter\nlast_verified: 2026-10-27\nverify_with: n/a\nsources:\n  - team knowledge (2026-10-27), unverified\n---\n"
        text = (front + "# Real\n\n" + FENCE + "bash\n# a comment in a script\n## not a heading\n" + FENCE + "\n"
                "~~~\n# inside a tilde fence\n~~~\n\n## Second\n\n" + FENCE + FENCE[0] + "\n# inside a four-tick fence\n" + FENCE + "\nstill inside\n" + FENCE + FENCE[0] + "\n\n## Third\n")
        r = run(str(self.page(text)))
        self.assertEqual([g[3] for g in rows(r.stdout)], ["(front matter)", "# Real", "  ## Second", "  ## Third"])

    def test_seven_hashes_and_hashes_without_a_space_are_not_headings(self):
        text = "# Real\n####### seven\n#nospace\n#\n## Next ##\n"
        r = run(str(self.page(text)))
        self.assertEqual([g[3] for g in rows(r.stdout)], ["# Real", "  ## Next"])

    def test_min_kb_hides_small_sections_and_says_how_many(self):
        page = self.page(block("# Big", 5000) + block("## Small one", 400) + block("## Small two", 600) + block("## Medium", 2500))
        r = run(str(page), "2")
        self.assertEqual([g[3] for g in rows(r.stdout)], ["# Big", "  ## Medium"])
        self.assertIn("2 sections smaller than 2 KB are not shown (1.0 KB together)", r.stdout)
        # The page line is the same with or without the filter: the total is the whole page.
        self.assertIn("8.5 KB, ", r.stdout)

    def test_min_kb_may_be_a_decimal(self):
        page = self.page(block("# A", 1500) + block("## B", 1400))
        r = run(str(page), "1.5")
        self.assertEqual([g[3] for g in rows(r.stdout)], ["# A"])

    def test_a_page_without_headings_says_so(self):
        r = run(str(self.page("just text\nmore text\n\nand more\n")))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 headings", r.stdout)
        self.assertIn("no headings: the page is one block", r.stdout)
        self.assertNotIn("over 40 KB", r.stdout)

    def test_an_empty_file_is_reported(self):
        r = run(str(self.page("")))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("empty file", r.stdout)

    def test_over_40_kb_prints_the_rule_and_under_40_kb_does_not(self):
        big = run(str(self.page(block("# Big", 41000) + block("## Tail", 100), "big.md")))
        self.assertIn("over 40 KB: do not read the page whole", big.stdout)
        small = run(str(self.page(block("# Small", 39000), "small.md")))
        self.assertNotIn("over 40 KB", small.stdout)

    def test_crlf_line_endings_still_give_headings(self):
        r = run(str(self.page("# One\r\ntext\r\n## Two\r\ntext\r\n")))
        self.assertEqual([g[3] for g in rows(r.stdout)], ["# One", "  ## Two"])

    def test_a_long_heading_is_cut(self):
        r = run(str(self.page("# " + "word " * 40 + "\n")))
        heading = rows(r.stdout)[0][3]
        self.assertTrue(heading.endswith("..."))
        self.assertLessEqual(len(heading), 95)

    def test_the_total_is_the_size_of_a_real_page(self):
        r = run(str(ROOT / "README.md"))
        self.assertEqual(r.returncode, 0, r.stderr)
        size = os.path.getsize(ROOT / "README.md")
        m = re.search(r"README\.md: ([\d.]+) KB", r.stdout)
        self.assertIsNotNone(m)
        self.assertAlmostEqual(float(m.group(1)), size / 1000, delta=0.1)

    @unittest.skipUnless(os.path.exists("/bin/bash"), "no /bin/bash")
    def test_the_same_output_under_bin_bash(self):
        page = self.page(FRONT + "\n" + block("# T", 1200) + block("## A", 800))
        self.assertEqual(run(str(page)).stdout, run(str(page), shell="/bin/bash").stdout)

    # --- the failing cases ---

    def test_a_missing_file_fails_and_names_it(self):
        r = run(str(self.dir / "nothing.md"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot read", r.stderr)
        self.assertIn("nothing.md", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_a_directory_fails(self):
        r = run(str(self.dir))
        self.assertEqual(r.returncode, 1)
        self.assertIn("is a directory", r.stderr)

    def test_no_argument_prints_the_usage(self):
        r = run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage:", r.stderr)

    def test_a_bad_min_kb_fails(self):
        page = self.page("# A\n")
        for bad in ("abc", "-1", "1.2.3", "."):
            with self.subTest(bad=bad):
                r = run(str(page), bad)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("MIN_KB must be a non-negative number", r.stderr)

    def test_three_arguments_fail(self):
        r = run(str(self.page("# A\n")), "1", "2")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
