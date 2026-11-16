# About this template

This file is for the person who adopts the template. Delete it, together with `FIRST-RUN.md`, when the first run is finished. Tier 0
does not check that you did.

## What it is

A starting point for a handbook that accumulates the knowledge of a team: an index and a memory that is written to be read by AI
agents first and by people second, with the checks that keep it true. It holds conventions, the scripts that enforce them, a short
generic version of each procedure, and an interview that finds out where the truth of your project lives. It holds no page of content.
It is not tied to one role: the same conventions serve a development team, a QA team and an SRE or operations team (see "Adapting it").

## What is in the box

- `FIRST-RUN.md` and `scripts/first_run.py`: the interview that finds out where the truth lives (22 questions in five groups).
- `CLAUDE.md`: the rules for agents. `README.md`: what the repository is, written for the people who find the template. Yours is
  written from the skeleton below. `process/`: five short procedures.
- `scripts/tier0.py` and `scripts/common.py`: the checks run before every commit. `scripts/make-index.sh` generates `INDEX.md`.
  `scripts/page-outline.sh` outlines a large page. `scripts/stalest.py` lists the pages verified longest ago.
  `scripts/secret_sweep.py` is the secret check used by the hook, the CI job and Tier 0.
- `handbook.cfg`: four settings. `scripts/foreign-identifiers.txt`: the names that must not appear. `scripts/size-budget.txt`: the ratchet list.
- `.githooks/pre-commit`, `.github/workflows/secret-sweep.yml` and `.github/workflows/ci.yml` (the tests of the scripts, and Tier 0 on
  the tree).
- Tests for all of it: `python3 scripts/test_tier0.py` and the other `scripts/test_*.py`; `scripts/test_template.py` walks the whole path
  from a fresh copy to a finished first run and a first commit through the hook.
- `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE.md` belong to the open
  source project that this template is. Keep what suits your repository and delete the rest. The license is the one of the template: your
  own handbook needs its own decision.

## What the checks do

A blocking finding fails the commit: a secret, a broken header or link, a missing `Sources` section, an out-of-date `INDEX.md`, a
foreign identifier, text in another alphabet (while `record_style = strict`), a bad setting. A warning is a prompt: an old `verified`
date, a page over its size budget, an orphaned page, an em dash, `first-run-pending`. The full list is in
`process/verification.md`.

## Adapting it

- **Folder names.** The four folders (`architecture`, `operations`, `process`, `reference`) are the default of `index_folders` in
  `handbook.cfg`: a comma-separated list of folders relative to the root, nested folders included automatically. Change the line, move
  the folders, and change the links that name them in `README.md`, `CLAUDE.md` and the pages (Tier 0 reports a broken link).
  `INDEX.md` gives the folders it knows (the four defaults and the folders inside `architecture` and `operations`) a one-line
  description; any other folder is listed without one.
- **Records that do not age.** `record_folders` in `handbook.cfg`. A folder of dated records (releases, postmortems, sign-offs,
  measurement results) belongs there; it may be empty.
- **Your team.** The questions of the first run and the rules do not depend on a role; what goes into the folders does. As a start:
  - a development team: `architecture/` the design of the system and its decision records; `operations/` how to build, release, debug
    and run it, with the dated records of releases; `reference/` pointers to repositories, owners and inventories.
  - a QA team: `architecture/` the test strategy and the shape of the environments; `operations/` the runbooks of test runs, with the
    sign-off records of releases; `reference/` where test data and accounts live, as locations and never as values.
  - an SRE or operations team: `architecture/` the topology of the services and their failure modes, with postmortems under
    `architecture/retrospectives/`; `operations/` runbooks and on-call procedures; `reference/` inventories and escalation paths, as pointers.
- **A language other than English.** Set `record_style = off` in `handbook.cfg`. Then rewrite the section "Records are formulations,
  not conversations" in `CLAUDE.md` to say what you want instead.
- **Another agent.** `CLAUDE.md` is the file that Claude Code reads. A tool that reads `AGENTS.md` can be given a root `AGENTS.md`
  that says to read `CLAUDE.md` (a file or a symlink; Tier 0 treats it as a root file, with no front matter).
- **Checks for your own tooling.** The template has no check for the commands that your pages hold, because they depend on your stack.
  If a command in a page can hit the wrong system when it does not name its target (a cluster, a project, an account), add a sweep that
  requires the target to be named, add a test to `scripts/test_tier0.py`, and register the sweep in `selected_sweeps`.
- **Several repositories.** If you keep the secret check in more than one repository, keep one copy as the source and add a Tier 0
  check that the others are identical.
- **Requirements.** Python 3.10 or later, PyYAML for Tier 0 and the generators (`requirements.txt`), bash and git. `secret_sweep.py` uses
  only the standard library.

## The skeleton of your README

Replace `README.md` with something like this, once the first run has told you whose handbook it is:

```markdown
# Handbook

An index and a memory for TEAM OR PRODUCT, written to be read by AI agents first and by people second.

## What this repository is

An index and a memory, not a mirror of the code. It holds what you cannot get by reading a repository or running a command:

- how the pieces fit together, and why
- verified, copy-pasteable procedures
- decisions and the constraints behind them
- traps that already cost someone a day, with the signature by which to recognise them

It deliberately does not hold anything that a command prints (statuses, versions, counts, lists of keys or endpoints): it links to the
source instead. Copies rot silently.

## How it is used

- Find a page: `grep -i WORD INDEX.md`, then open the page the line names.
- Write a page: read [CLAUDE.md](CLAUDE.md); the procedures it points to are in `process/`.
- Check before a commit: `scripts/tier0.sh`. Check a page's age: `python3 scripts/stalest.py`.
- Pick what to re-verify next: `python3 scripts/stalest.py -n 5 operations`.

## Layout

- `architecture/`: how the system fits together and why
- `operations/`: runbooks and how-to pages
- `process/`: the procedures for working on this handbook
- `reference/`: pointers, inventories and the page of sources of truth
- `scripts/`: the checks and generators; `handbook.cfg` holds their settings
```

## What is not included

Checks that depend on a stack: the target of infrastructure commands, a single allowed cloud project, the drift of pinned chart or
module hashes, a project IAM policy. Procedures that depend on a stack: preflight, production safety, label selectors, application
metrics. Add the ones your project needs when it needs them.

## What has not been verified

The template has not been used by a real team yet. The tests pass and a fresh copy passes Tier 0 with the one warning
`first-run-pending`, but the 22 questions of the first run are a draft: change them after the first real interview, and keep the format
(`- **A1** question`, then an optional `*Why:*` line) so that `scripts/first_run.py` can still read them. The scripts were written and
tested on macOS; the workflow that runs them on Linux has not been seen to pass.
