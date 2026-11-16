#!/usr/bin/env python3
"""Tests for scripts/stalest.py, in the style of test_page_outline.py: the script is run as a program on a throwaway handbook.

Run with: python3 scripts/test_stalest.py
"""
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import stalest  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "stalest.py"
TODAY = "2030-01-15"  # far from the real day, so that a script that read the clock instead of --today fails the tests


def age(day: str) -> int:
    return (date.fromisoformat(TODAY) - date.fromisoformat(day)).days


def page(root: Path, relpath: str, status: str = "unverified", last_verified: str = "2026-10-06", verify_with: str = "n/a"):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nstatus: {status}\nlast_verified: {last_verified}\nverify_with: {verify_with}\nsources_count: 0\n---\n\n# page\n", encoding="utf-8")


def run(root: Path, *args: str):
    done = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--today", TODAY, *args], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def paths(out: str):
    return [line.split()[-1] for line in out.splitlines() if not line.startswith(" ")]


class StalestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_oldest_first_then_unverified_before_verified_then_path(self):
        page(self.root, "operations/b.md", "verified", "2026-10-10")
        page(self.root, "operations/a.md", "verified", "2026-10-10")
        page(self.root, "operations/c.md", "unverified", "2026-10-10")
        page(self.root, "operations/old.md", "verified", "2026-10-01")
        page(self.root, "reference/new.md", "unverified", "2026-10-29")
        rc, out, _ = run(self.root, "-n", "0")
        self.assertEqual(rc, 0)
        self.assertEqual(paths(out), ["operations/old.md", "operations/c.md", "operations/a.md", "operations/b.md", "reference/new.md"])

    def test_a_stale_page_is_not_moved_up(self):
        page(self.root, "operations/gone.md", "stale", "2026-10-29")
        page(self.root, "operations/plain.md", "unverified", "2026-10-06")
        self.assertEqual(paths(run(self.root, "-n", "0")[1]), ["operations/plain.md", "operations/gone.md"])

    def test_a_date_that_cannot_be_read_comes_first_and_shows_a_question_mark(self):
        page(self.root, "operations/ok.md", "unverified", "2026-10-01")
        page(self.root, "operations/odd.md", "verified", "soon")
        _, out, _ = run(self.root, "-n", "0")
        self.assertEqual(paths(out), ["operations/odd.md", "operations/ok.md"])
        self.assertEqual(out.splitlines()[0].split(), ["soon", "?", "verified", "operations/odd.md"])

    def test_the_age_status_and_command_are_printed(self):
        page(self.root, "operations/a.md", "verified", "2026-10-20", "gh run list --limit 1")
        _, out, _ = run(self.root)
        self.assertEqual(out.splitlines(), [f"2026-10-20  {str(age('2026-10-20')) + 'd':>5}  verified    operations/a.md", "    verify_with: gh run list --limit 1"])

    def test_the_records_and_the_pages_outside_the_four_folders_are_left_out(self):
        page(self.root, "operations/releases/r.md", "unverified", "2026-10-01")
        page(self.root, "architecture/retrospectives/r.md", "unverified", "2026-10-01")
        page(self.root, "scripts/tools/results/r.md", "verified", "2026-10-01")
        page(self.root, "operations/p.md", "unverified", "2026-10-20")
        (self.root / "README.md").write_text("# no header\n", encoding="utf-8")
        self.assertEqual(paths(run(self.root, "-n", "0")[1]), ["operations/p.md"])

    def test_the_folders_and_the_records_of_the_config_replace_the_default_ones(self):
        (self.root / "handbook.cfg").write_text("[handbook]\nindex_folders = docs, runbooks\nrecord_folders = runbooks/postmortems\n", encoding="utf-8")
        page(self.root, "docs/a.md", "unverified", "2026-10-02")
        page(self.root, "runbooks/b.md", "unverified", "2026-10-03")
        page(self.root, "runbooks/postmortems/p.md", "unverified", "2026-10-01")
        page(self.root, "operations/c.md", "unverified", "2026-10-01")
        page(self.root, "operations/releases/r.md", "unverified", "2026-10-01")
        self.assertEqual(paths(run(self.root, "-n", "0")[1]), ["docs/a.md", "runbooks/b.md"])
        self.assertEqual(paths(run(self.root, "-n", "0", "runbooks")[1]), ["runbooks/b.md"])
        self.assertEqual(paths(run(self.root, "runbooks/postmortems")[1]), ["runbooks/postmortems/p.md"])
        self.assertEqual(paths(run(self.root, "-n", "0", "operations")[1]), ["operations/c.md", "operations/releases/r.md"])

    def test_a_mistake_in_the_config_is_said_on_stderr_and_the_defaults_are_used(self):
        (self.root / "handbook.cfg").write_text("[handbook]\nindex_folders = ../up\n", encoding="utf-8")
        page(self.root, "operations/p.md", "unverified", "2026-10-20")
        code, out, err = run(self.root, "-n", "0")
        self.assertEqual((code, paths(out)), (0, ["operations/p.md"]))
        self.assertIn("handbook.cfg: index_folders has '../up'", err)

    def test_a_parent_folder_does_not_bring_the_records_back_but_their_own_folder_does(self):
        page(self.root, "operations/releases/r.md", "unverified", "2026-10-01")
        page(self.root, "architecture/retrospectives/r.md", "unverified", "2026-10-01")
        page(self.root, "operations/p.md", "unverified", "2026-10-20")
        page(self.root, "architecture/a.md", "unverified", "2026-10-20")
        self.assertEqual(paths(run(self.root, "-n", "0", "operations")[1]), ["operations/p.md"])
        self.assertEqual(paths(run(self.root, "-n", "0", "operations", "architecture")[1]), ["architecture/a.md", "operations/p.md"])
        self.assertEqual(paths(run(self.root, "operations/releases")[1]), ["operations/releases/r.md"])
        self.assertEqual(paths(run(self.root, "-n", "0", "operations/releases", "architecture/retrospectives")[1]), ["architecture/retrospectives/r.md", "operations/releases/r.md"])

    def test_count_limits_the_list_and_zero_prints_all(self):
        for i in range(7):
            page(self.root, f"operations/p{i}.md", "unverified", f"2026-10-0{i + 1}")
        self.assertEqual(len(paths(run(self.root)[1])), 5)
        self.assertEqual(len(paths(run(self.root, "-n", "2")[1])), 2)
        self.assertEqual(len(paths(run(self.root, "-n", "0")[1])), 7)

    def test_a_folder_limits_the_list_and_is_written_with_or_without_a_slash_or_a_dot(self):
        page(self.root, "operations/a.md")
        page(self.root, "reference/b.md")
        for spelling in ("reference", "reference/", "./reference", "./reference/"):
            self.assertEqual(paths(run(self.root, spelling)[1]), ["reference/b.md"], spelling)

    def test_a_folder_that_holds_no_page_is_an_error_even_next_to_a_good_one(self):
        page(self.root, "operations/a.md")
        for args in (["nothing"], ["oper"], ["operations", "nothing"], ["."]):
            rc, out, err = run(self.root, *args)
            self.assertEqual((rc, out), (2, ""), args)
            self.assertIn("no page under " + [a for a in args if a != "operations"][0], err)

    def test_an_empty_handbook_is_an_error(self):
        rc, out, err = run(self.root)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("no page under", err)

    def test_a_negative_count_is_refused(self):
        page(self.root, "operations/a.md")
        rc, out, err = run(self.root, "-n", "-1")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("must be 0 or more", err)

    def test_rank_orders_unsorted_input_by_date_then_status_then_path(self):
        def entry(path, status, day):
            return {"path": path, "status": status, "last_verified": day, "verify_with": "n/a"}

        got = stalest.rank([entry("z.md", "verified", "2026-10-02"), entry("b.md", "verified", "2026-10-02"), entry("c.md", "unverified", "2026-10-02"), entry("y.md", "verified", None), entry("a.md", "stale", "2026-10-03")])
        self.assertEqual([p["path"] for p in got], ["y.md", "c.md", "b.md", "z.md", "a.md"])

    def test_naming_a_parent_and_its_records_folder_together_lists_the_records_too(self):
        page(self.root, "operations/releases/r.md", "unverified", "2026-10-01")
        page(self.root, "operations/p.md", "unverified", "2026-10-20")
        self.assertEqual(paths(run(self.root, "-n", "0", "operations", "operations/releases")[1]), ["operations/releases/r.md", "operations/p.md"])

    def test_a_folder_is_a_whole_path_segment_and_an_absolute_path_is_not_a_relative_one(self):
        page(self.root, "operations/a.md")
        self.assertEqual(stalest.read_pages(self.root, ("oper",)), [])
        rc, out, err = run(self.root, "/operations")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("no page under /operations", err)

    def test_a_date_over_several_lines_or_missing_still_prints_two_lines_for_the_page(self):
        (self.root / "operations").mkdir()
        (self.root / "operations/block.md").write_text("---\nstatus: unverified\nlast_verified: |\n  2026-10-06\n  and more\nverify_with: n/a\n---\n# x\n", encoding="utf-8")
        (self.root / "operations/missing.md").write_text("---\nstatus: unverified\nverify_with: n/a\n---\n# x\n", encoding="utf-8")
        _, out, _ = run(self.root, "-n", "0")
        self.assertEqual(len(out.splitlines()), 4)
        self.assertEqual(sorted(line.split()[0] for line in out.splitlines() if not line.startswith(" ")), ["2026-10-06", "?"])

    def test_a_page_with_a_broken_header_is_skipped_and_a_wrapped_command_is_one_line(self):
        (self.root / "operations").mkdir()
        (self.root / "operations/broken.md").write_text("---\nstatus: [unverified\n---\n# x\n", encoding="utf-8")
        (self.root / "operations/wrapped.md").write_text("---\nstatus: unverified\nlast_verified: 2026-10-06\nverify_with: |\n  gh run list\n  --limit 1\n---\n# x\n", encoding="utf-8")
        _, out, _ = run(self.root, "-n", "0")
        self.assertEqual(out.splitlines(), [f"2026-10-06  {str(age('2026-10-06')) + 'd':>5}  unverified  operations/wrapped.md", "    verify_with: gh run list --limit 1"])


if __name__ == "__main__":
    unittest.main()
