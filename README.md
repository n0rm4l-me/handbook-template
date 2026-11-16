# Handbook template

**A team knowledge base in git that stays true.** It keeps what only people know, points at the source for everything else, says
what evidence stands behind each page, and checks all of that before every commit. It is written to be read by AI agents first and by
people second.

It is for any team that has to hand knowledge over to a newcomer, to the person on call or to an agent: development, QA, SRE and
operations, data, security. It holds no content of its own. It holds the conventions, the scripts that enforce them, a short generic
version of each procedure, and an interview that finds out where the truth of your project lives.

## The idea

One rule: **write only what cannot be derived from a repository or a live command.**

- What belongs in the handbook: how the pieces fit together and why a design was chosen, procedures that took trial and error to get
  right, failure modes with the signature by which to recognise them, decisions and the constraints behind them.
- What does not: lists of endpoints, configuration keys, versions, counts and statuses, anything a command prints. A page links to the
  source instead, because a copied value rots silently and is trusted anyway.

The rest of the template exists to make that rule hold.

## What makes it different

Most documentation templates give you folders to fill. This one gives you rules about truth, and the machinery that enforces them.

- **It is built on a rule, not on a structure.** A page links to the source instead of repeating a value, so there is nothing to rot
  silently. The agent that writes the pages gets the rule first, and the procedures behind it (keep the documentation current, verify
  before you claim) exist to make it hold.
- **Every page says what was seen, not how sure the author felt.** `verified` means the commands were run and the output was seen;
  anything else is `unverified`. A page carries the command that re-checks it and a `Sources` section: a commit that is pinned, a live
  result with its date, or a person's word recorded as `team knowledge` and unverified. A `verified` page that nobody re-checks is
  flagged as it ages.
- **It starts from where the truth lives.** Before the first page is written, the first-run interview asks for each kind of fact which
  system is the source of truth, how to read it with a command, who owns it, and which source wins when two disagree.
- **It is built for the agent that reads it.** A generated `INDEX.md` has one line for each page. An agent greps it and opens one page,
  reads a large page by section, and reads a procedure only when its trigger fires, so it pays for the page it needs and not for the
  whole handbook.
- **The checks run offline, in seconds, before every commit.** Secrets (in the hook, and in CI on the tree and on every commit ever
  made), front matter, sources, links, an index that is out of date, page size, the age of a verification, names copied from another
  project, text outside the language rule. No network and no credentials.
- **Records state facts, not conversations, and never a guess.** A fact is written with its source. A name, an id or a count goes in
  only when it was read in the session; otherwise the page holds a capitalised placeholder, not a plausible value that the next reader
  copies into a command.
- **It fits any team.** The questions and the rules do not depend on a role, and the folder names are a setting.
- **It is tested like software.** Every script has tests, one end-to-end test walks a fresh copy through the first run to a first
  commit through the hook, and CI runs them on Linux and macOS.

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

1. Create your repository from this template (on GitHub, "Use this template"), clone it and open it in your AI agent.
2. Give the agent one sentence:

   ```text
   Start the handbook: read FIRST-RUN.md and follow it from the first step to the last, and ask me the questions.
   ```

3. Answer the questions. The agent installs the requirements, switches on the pre-commit hook, writes
   `reference/sources-of-truth.md` and a README for your handbook, asks before it deletes `FIRST-RUN.md` and `TEMPLATE.md`, and
   proposes the first pages.

Without an agent: `pip install -r requirements.txt`, `git config core.hooksPath .githooks`, then `python3 scripts/first_run.py`. Read
`TEMPLATE.md`, write your README from its skeleton, and delete `TEMPLATE.md` and `FIRST-RUN.md`.

From then on, add a page when someone has verified content for it, not to fill a structure. Find a page: `grep -i WORD INDEX.md`, then
open the page the line names. Check before a commit: `scripts/tier0.sh`. Pick what to re-verify next:
`python3 scripts/stalest.py -n 5`.

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

As of 2026-11-16, by the account of its author: the template has been used on two projects, and this version holds the fixes found
there. The tests pass and a fresh copy passes Tier 0 with one warning (`first-run-pending`). The 22 questions of the first run are the
part most worth adapting: change them for your team and keep the format. Reports from other teams are the most useful contribution:
see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT, see `LICENSE`.
