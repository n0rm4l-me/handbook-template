#!/usr/bin/env python3
"""End to end: a fresh copy of this template, then a finished first run, both through the real scripts and the real Tier 0.

It guards the failures that only show when the whole path is walked: a page that links to a file the first run deletes, a check that
fires on the temporary files, an index that is out of date after the interview.

Run with: python3 scripts/test_template.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import first_run  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GIT = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=tester"]


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, **kw)


def tier0(cwd):
    done = sh([sys.executable, "-I", "scripts/tier0.py"], cwd)
    found = re.search(r"Tier 0: (\d+) blocking, (\d+) warning", done.stdout)
    checks = re.findall(r"^\s+(?:BLOCKING|warning)\s+\[([a-z0-9-]+)\]", done.stdout, re.M)
    return done.returncode, (int(found.group(1)), int(found.group(2))), checks, done.stdout


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.copy = Path(self._tmp.name) / "copy"
        shutil.copytree(ROOT, self.copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        sh(["git", "init", "-q", "-b", "main"], self.copy)
        self.refresh()

    def tearDown(self):
        self._tmp.cleanup()

    def refresh(self):
        sh(["git", "add", "-A"], self.copy)
        sh(["bash", "scripts/make-index.sh", "--write"], self.copy)
        sh(["git", "add", "-A"], self.copy)

    def test_a_fresh_copy_has_only_the_first_run_warning(self):
        code, counts, checks, out = tier0(self.copy)
        self.assertEqual((code, counts, checks), (0, (0, 1), ["first-run-pending"]), out)

    def test_a_finished_first_run_leaves_a_clean_handbook_and_the_first_commit_passes_the_hook(self):
        questions = first_run.parse_questions((self.copy / "FIRST-RUN.md").read_text(encoding="utf-8"))
        replies = [line for i in range(len(questions)) for line in ([f"answer {i}", ""] if i % 5 else ["?"])] + ["y"]
        it = iter(replies)
        code = first_run.main(["--root", str(self.copy), "--today", date.today().isoformat()], ask=lambda: next(it, None), say=lambda *_: None)
        self.assertEqual(code, 0)
        self.assertFalse((self.copy / "FIRST-RUN.md").exists())
        (self.copy / "TEMPLATE.md").unlink()
        self.refresh()
        code, counts, checks, out = tier0(self.copy)
        self.assertEqual((code, counts, checks), (0, (0, 0), []), out)
        sh(["git", "config", "core.hooksPath", ".githooks"], self.copy)
        done = sh([*GIT, "commit", "-q", "-m", "first run"], self.copy)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_the_page_of_the_first_run_is_refused_when_an_answer_holds_a_secret(self):
        questions = first_run.parse_questions((self.copy / "FIRST-RUN.md").read_text(encoding="utf-8"))
        replies = [line for i in range(len(questions)) for line in (["api" + "_key = abc123def456ghi789xyz", ""] if i == 3 else ["fine", ""])] + ["n"]
        it = iter(replies)
        first_run.main(["--root", str(self.copy), "--today", date.today().isoformat()], ask=lambda: next(it, None), say=lambda *_: None)
        self.refresh()
        sh(["git", "config", "core.hooksPath", ".githooks"], self.copy)
        done = sh([*GIT, "commit", "-q", "-m", "first run"], self.copy)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("SECRET?", done.stdout + done.stderr)

    def test_a_name_on_the_foreign_list_stops_a_copied_page(self):
        (self.copy / "scripts/foreign-identifiers.txt").write_text("neighbour-[a-z]+\n", encoding="utf-8")
        (self.copy / "operations").mkdir(exist_ok=True)
        (self.copy / "operations/copied.md").write_text(
            "---\nstatus: unverified\nlast_verified: 2030-01-01\nverify_with: n/a\nsources_count: 1\n---\n\n# Copied\n\nruns on neighbour-prod\n\n## Sources\n\n- team knowledge (2030-01-01), unverified: x\n",
            encoding="utf-8")
        self.refresh()
        code, counts, checks, out = tier0(self.copy)
        self.assertEqual(code, 1)
        self.assertIn("foreign-identifier", checks, out)


if __name__ == "__main__":
    unittest.main()
