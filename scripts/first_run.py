#!/usr/bin/env python3
"""The first-run interview for a person without an agent: where does the truth of each kind of fact live?

Usage:
    python3 scripts/first_run.py [--root DIR] [--today YYYY-MM-DD] [--force]

The questions are read from FIRST-RUN.md, the one place that holds them (the lines `- **A1** question` under a heading
`### A. Group`, each with an optional `*Why:*` line). For each one the script takes a few lines: an empty line ends an answer, and
`?` or an empty answer means "unknown". It writes the answers to reference/sources-of-truth.md as a first version of the page, which
an agent or a person can restructure later into the layout FIRST-RUN.md describes. It never overwrites the page without --force, and
it asks before it deletes FIRST-RUN.md.

Do not type a secret, a token, a password or personal data: the page is committed, and Tier 0 refuses what looks like a secret.
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

FIRST_RUN_FILE = "FIRST-RUN.md"
PAGE = "reference/sources-of-truth.md"
GROUP = re.compile(r"^### ([A-Z])\. (.+?)\s*$")
QUESTION = re.compile(r"^- \*\*([A-Z]\d+)\*\* (.+?)\s*$")
WHY = re.compile(r"^\s+\*Why:\* (.+?)\s*$")
UNKNOWN = "unknown"


def parse_questions(text: str) -> list:
    """The questions of FIRST-RUN.md, in order: dicts with id, group (letter), group_title, text and why. Pure."""
    questions, group, title, in_section = [], None, None, False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.strip() == "## Questions"
            continue
        if not in_section:
            continue
        match = GROUP.match(line)
        if match:
            group, title = match.group(1), match.group(2)
            continue
        match = QUESTION.match(line)
        if match and group:
            questions.append({"id": match.group(1), "group": group, "group_title": title, "text": match.group(2), "why": ""})
            continue
        match = WHY.match(line)
        if match and questions and not questions[-1]["why"]:
            questions[-1]["why"] = match.group(1)
    return questions


def interview(questions: list, ask, say) -> dict:
    """Ask each question and return {id: answer}. `ask()` returns one line, or None at the end of the input. Pure apart from them.

    An answer is the lines up to an empty line. A first line `?` ends the answer at once; it, an empty answer, or the end of the input
    gives UNKNOWN.
    """
    answers, group = {}, None
    for number, question in enumerate(questions):
        if question["group"] != group:
            group = question["group"]
            say(f"\n== {group}. {question['group_title']} ==")
        say(f"\n{question['id']}. {question['text']}")
        if question["why"]:
            say(f"   (why: {question['why']})")
        lines = []
        while True:
            line = ask()
            if line is None:
                answers[question["id"]] = "\n".join(lines).strip() or UNKNOWN
                for rest in questions[number + 1:]:
                    answers[rest["id"]] = UNKNOWN
                return answers
            if line.strip() == "":
                break
            if not lines and line.strip() == "?":
                break
            lines.append(line.rstrip())
        answer = "\n".join(lines).strip()
        answers[question["id"]] = UNKNOWN if answer in ("", "?") else answer
    return answers


def clean(answer: str) -> str:
    """The answer as page text: a line that starts with # would become a heading and could break the sections, so it is escaped."""
    return "\n".join("\\" + line if line.lstrip().startswith("#") else line for line in answer.splitlines())


def render_page(questions: list, answers: dict, today: date) -> str:
    """The text of reference/sources-of-truth.md. Pure."""
    out = [
        "---",
        "status: unverified",
        f"last_verified: {today.isoformat()}",
        "verify_with: n/a",
        "summary: Where the truth of each kind of fact lives, how to read it with a command, who owns it and which source wins",
        "keywords: sources of truth, first run",
        "sources_count: 1",
        "---",
        "",
        "# Sources of truth: where each kind of fact lives",
        "",
        "These are the sources of truth of this handbook, written at the first run from the answers of the interview. They are what people",
        "said, not what was checked: each command in them stays unverified until it has been run and the result recorded under `## Sources`.",
        "Restructure this page into the layout of `FIRST-RUN.md` (one section per kind of fact: source, command, owner, what it wins over).",
        "",
    ]
    group = None
    for question in questions:
        if question["group"] != group:
            group = question["group"]
            out += [f"## {group}. {question['group_title']}", ""]
        out += [f"**{question['id']}** {question['text']}", "", clean(answers.get(question["id"], UNKNOWN)), ""]
    out += [
        "## Sources",
        "",
        f"- team knowledge ({today.isoformat()}), unverified: the answers of the first-run interview, written by scripts/first_run.py",
        "",
    ]
    return "\n".join(out)


def main(argv=None, ask=None, say=print) -> int:
    parser = argparse.ArgumentParser(description="Ask where the truth of each kind of fact lives and write the first sources-of-truth page.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent, help="the handbook to write to")
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="the date to write into the page (default today)")
    parser.add_argument("--force", action="store_true", help=f"overwrite {PAGE} if it exists")
    args = parser.parse_args(argv)
    if ask is None:
        def ask():
            try:
                return input("> ")
            except EOFError:
                return None
    first_run, page = args.root / FIRST_RUN_FILE, args.root / PAGE
    if not first_run.is_file():
        print(f"{FIRST_RUN_FILE} not found under {args.root}: the first run is done, or this is not a copy of the template", file=sys.stderr)
        return 2
    if page.exists() and not args.force:
        print(f"{PAGE} exists already: run again with --force to overwrite it", file=sys.stderr)
        return 2
    questions = parse_questions(first_run.read_text(encoding="utf-8"))
    if not questions:
        print(f"no question found in {FIRST_RUN_FILE}: the lines must look like `- **A1** question` under `### A. Group`", file=sys.stderr)
        return 2
    say("First run: where does the truth live? Answer in a few lines, an empty line ends an answer, '?' means unknown.")
    say("Do not type a secret, a token, a password or personal data.")
    answers = interview(questions, ask, say)
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(render_page(questions, answers, args.today or date.today()), encoding="utf-8")
    unknown = sum(1 for value in answers.values() if value == UNKNOWN)
    say(f"\nWritten {PAGE} ({len(questions)} questions, {unknown} unknown).")
    say("Next: set record_style (E2) and verified_max_age_days (E3) in handbook.cfg, list the names of D3 in scripts/foreign-identifiers.txt,")
    say(f"then run scripts/tier0.sh. Delete {FIRST_RUN_FILE} when the page has been read back with the owner.")
    say(f"Delete {FIRST_RUN_FILE} now? [y/N]")
    reply = ask()
    if reply is not None and reply.strip().lower() in ("y", "yes"):
        first_run.unlink()
        say(f"{FIRST_RUN_FILE} deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
