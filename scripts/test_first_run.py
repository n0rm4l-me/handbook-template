#!/usr/bin/env python3
"""Tests for scripts/first_run.py and for the questions of FIRST-RUN.md that it reads.

Run with: python3 scripts/test_first_run.py
"""
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import first_run  # noqa: E402
import tier0  # noqa: E402
from test_tier0 import FixtureRepo, blank, checks  # noqa: E402

REAL_FIRST_RUN = Path(__file__).resolve().parent.parent / "FIRST-RUN.md"
TODAY = date(2030, 1, 15)

SAMPLE = """# First run

## How to run it

- **Z9** this line is outside the section of questions and is not one

## Questions

### A. One

- **A1** First question?
  *Why:* because.
- **A2** Second question?

### B. Two

- **B1** Third question?
  *Why:* so.
"""


def scripted(lines):
    """An ask() that returns the lines in turn and then None, the end of the input."""
    it = iter(lines)
    return lambda: next(it, None)


class ParseTests(unittest.TestCase):
    def test_questions_groups_and_why_are_read_and_the_text_outside_the_section_is_not(self):
        got = first_run.parse_questions(SAMPLE)
        self.assertEqual([(q["id"], q["group"], q["group_title"], q["text"], q["why"]) for q in got], [
            ("A1", "A", "One", "First question?", "because."),
            ("A2", "A", "One", "Second question?", ""),
            ("B1", "B", "Two", "Third question?", "so."),
        ])

    def test_a_file_without_a_section_of_questions_gives_none(self):
        self.assertEqual(first_run.parse_questions("# x\n\n- **A1** a question\n"), [])

    def test_the_real_file_has_questions_in_every_group_each_with_a_why_and_no_repeated_id(self):
        got = first_run.parse_questions(REAL_FIRST_RUN.read_text(encoding="utf-8"))
        self.assertEqual("".join(sorted({q["group"] for q in got})), "ABCDE")
        ids = [q["id"] for q in got]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([q["id"] for q in got if not q["why"]], [])
        self.assertTrue(all(q["text"].endswith(("?", ".")) for q in got), "a question that does not end in a mark")


class InterviewTests(unittest.TestCase):
    QUESTIONS = first_run.parse_questions(SAMPLE)

    def run_interview(self, lines):
        said = []
        return first_run.interview(self.QUESTIONS, scripted(lines), said.append), said

    def test_an_answer_runs_to_an_empty_line_and_may_have_several_lines(self):
        answers, _ = self.run_interview(["line one", "line two", "", "short", "", "x", ""])
        self.assertEqual(answers, {"A1": "line one\nline two", "A2": "short", "B1": "x"})

    def test_a_question_mark_an_empty_answer_and_the_end_of_input_mean_unknown(self):
        answers, _ = self.run_interview(["?", "", "partial"])
        self.assertEqual(answers, {"A1": "unknown", "A2": "unknown", "B1": "partial"})
        # a question mark ends the answer at once, with no empty line after it; one inside an answer is text
        answers, _ = self.run_interview(["?", "?", "a", "?", "", ])
        self.assertEqual(answers, {"A1": "unknown", "A2": "unknown", "B1": "a\n?"})
        answers, _ = self.run_interview(["only the first", ""])
        self.assertEqual(answers, {"A1": "only the first", "A2": "unknown", "B1": "unknown"})
        answers, _ = self.run_interview([])
        self.assertEqual(set(answers.values()), {"unknown"})

    def test_the_group_heading_and_the_why_are_shown(self):
        _, said = self.run_interview(["a", "", "b", "", "c", ""])
        text = "\n".join(said)
        self.assertEqual(text.count("== A. One =="), 1)
        self.assertEqual(text.count("== B. Two =="), 1)
        self.assertIn("(why: because.)", text)
        self.assertIn("A2. Second question?", text)


class RenderTests(unittest.TestCase):
    def test_the_page_passes_the_sweeps_that_read_a_page(self):
        questions = first_run.parse_questions(REAL_FIRST_RUN.read_text(encoding="utf-8"))
        answers = {q["id"]: "an answer\n# looks like a heading\n## Sources\n- not a source" for q in questions}
        with FixtureRepo() as fx:
            (fx.root / "reference").mkdir()
            (fx.root / "reference/sources-of-truth.md").write_text(first_run.render_page(questions, answers, TODAY), encoding="utf-8")
            r = blank()
            for sweep in (tier0.sweep_yaml_frontmatter, tier0.sweep_sources_section, tier0.sweep_index_fields):
                sweep(r)
            tier0.sweep_verification_age(r, today=TODAY)
            self.assertEqual([(b, c) for b in r for c in checks(r, b)], [])

    def test_a_line_that_would_become_a_heading_is_escaped(self):
        self.assertEqual(first_run.clean("a\n# b\n   ## c\nd"), "a\n\\# b\n\\   ## c\nd")

    def test_a_missing_answer_is_unknown_and_the_date_is_written(self):
        questions = first_run.parse_questions(SAMPLE)
        text = first_run.render_page(questions, {"A1": "yes"}, TODAY)
        self.assertIn("last_verified: 2030-01-15", text)
        self.assertIn("**A2** Second question?\n\nunknown", text)
        self.assertIn("team knowledge (2030-01-15), unverified", text)


class MainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        shutil.copy(REAL_FIRST_RUN, self.root / "FIRST-RUN.md")
        self.count = len(first_run.parse_questions(REAL_FIRST_RUN.read_text(encoding="utf-8")))

    def tearDown(self):
        self._tmp.cleanup()

    def run_main(self, replies, *extra):
        said = []
        code = first_run.main(["--root", str(self.root), "--today", "2030-01-15", *extra], ask=scripted(replies), say=said.append)
        return code, "\n".join(said)

    def answers(self, tail):
        return ["an answer", ""] * self.count + tail

    def test_it_writes_the_page_and_keeps_the_file_unless_told_to_delete_it(self):
        code, said = self.run_main(self.answers(["n"]))
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "reference/sources-of-truth.md").is_file())
        self.assertTrue((self.root / "FIRST-RUN.md").is_file())
        self.assertIn(f"{self.count} questions, 0 unknown", said)

    def test_it_deletes_the_file_on_a_yes(self):
        self.assertEqual(self.run_main(self.answers(["y"]))[0], 0)
        self.assertFalse((self.root / "FIRST-RUN.md").exists())

    def test_an_end_of_input_at_the_last_prompt_deletes_nothing(self):
        self.assertEqual(self.run_main(self.answers([]))[0], 0)
        self.assertTrue((self.root / "FIRST-RUN.md").is_file())

    def test_it_refuses_to_overwrite_the_page_without_force(self):
        self.run_main(self.answers(["n"]))
        page = self.root / "reference/sources-of-truth.md"
        page.write_text("kept\n", encoding="utf-8")
        self.assertEqual(self.run_main(self.answers(["n"]))[0], 2)
        self.assertEqual(page.read_text(encoding="utf-8"), "kept\n")
        self.assertEqual(self.run_main(self.answers(["n"]), "--force")[0], 0)
        self.assertNotEqual(page.read_text(encoding="utf-8"), "kept\n")

    def test_it_stops_when_the_first_run_is_already_done_or_the_file_has_no_questions(self):
        (self.root / "FIRST-RUN.md").write_text("# no questions here\n", encoding="utf-8")
        self.assertEqual(self.run_main([])[0], 2)
        (self.root / "FIRST-RUN.md").unlink()
        self.assertEqual(self.run_main([])[0], 2)


if __name__ == "__main__":
    unittest.main()
