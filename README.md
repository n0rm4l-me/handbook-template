# Handbook template

A starting point for the knowledge base of one team or product, kept in git: an index and a memory that AI agents read first and
people second, with checks that keep it true.

It is for any team that has to hand knowledge over to a newcomer, to the person on call or to an agent: development, QA, SRE and
operations, data, security. It holds no content of its own. It holds the conventions, the scripts that enforce them, a short generic
version of each procedure, and an interview that finds out where the truth of your project lives.

## The idea

One rule: **write only what cannot be derived from a repository or a live command.**

- What belongs in the handbook: how the pieces fit together and why a design was chosen, procedures that took trial and error to get
  right, failure modes with the signature by which to recognise them, decisions and the constraints behind them.
- What does not: lists of endpoints, configuration keys, versions, counts and statuses, anything a command prints. A page links to the
  source instead, because a copied value rots silently and is trusted anyway.

Everything else follows from it. A page says where each fact comes from and how to check it again. Its `status` says what evidence was
seen, not how confident the author felt. A check refuses a secret, a broken link, a missing source and an index that is out of date.

## What you get

- [CLAUDE.md](CLAUDE.md): the rules for the agent that writes in the repository. It is the file Claude Code reads. For a tool that
  reads `AGENTS.md`, add a root `AGENTS.md` that says to read `CLAUDE.md`.
- `process/`: five short procedures, each read when its trigger fires: front matter, verification, keeping the documentation current,
  pull requests, decision records.
- `scripts/`: the checks and generators. `tier0.py` runs every static check before a commit (secrets, front matter, sources, links,
  index, size, age of a verification, language). `make-index.sh` generates `INDEX.md`, the one file an agent greps to find a page.
  `page-outline.sh` outlines a large page, `stalest.py` lists the pages verified longest ago, `secret_sweep.py` is the secret check.
- `FIRST-RUN.md` and `scripts/first_run.py`: the interview that finds out where the truth of each kind of fact lives, for a team of
  any kind, with or without an agent.
- `.githooks/pre-commit` and two GitHub workflows: the secret sweep and Tier 0 on every commit, the tests of the scripts on Linux and macOS.

## Quick start

1. Create your repository from this template (on GitHub, "Use this template") or copy the files.
2. `pip install -r requirements.txt`, then `git config core.hooksPath .githooks` (once per clone).
3. Run the first-run interview: ask an agent to start the handbook, or run `python3 scripts/first_run.py`. It writes
   `reference/sources-of-truth.md`.
4. Read `TEMPLATE.md` for what is in the box and what to adapt. Then write the README of your own handbook (`TEMPLATE.md` has a
   skeleton) and delete `TEMPLATE.md` and `FIRST-RUN.md`.
5. Write the first pages from the questions people ask again and again. Add a page when someone has verified content for it, not to
   fill a structure.

Find a page: `grep -i WORD INDEX.md`, then open the page the line names. Check before a commit: `scripts/tier0.sh`.
Pick what to re-verify next: `python3 scripts/stalest.py -n 5`.

## Layout

- `architecture/`: how the system fits together and why (`architecture/decisions/` holds decision records)
- `operations/`: runbooks and how-to pages (`operations/releases/` holds dated records)
- `process/`: the procedures for working on the handbook
- `reference/`: pointers, inventories and the page of sources of truth
- `scripts/`: the checks and generators
- `handbook.cfg`: the settings: the language rule, the age limit of a verification, the folder names

The four folder names are a default. A QA team, an SRE team and a product team name them differently: set `index_folders` and
`record_folders` in `handbook.cfg`.

## Requirements

Python 3.10 or later, PyYAML (`requirements.txt`), bash and git. The scripts are written for macOS (bash 3.2) and Linux, and the CI
workflow runs the tests on both.

## Status

Early. The tests pass and a fresh copy passes Tier 0 with one warning (`first-run-pending`), but no real team has used the template
yet, and the 22 questions of the first run are a draft. Reports from a first real adoption are the most useful contribution: see
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT, see `LICENSE`.
