---
status: unverified
last_verified: 2026-10-30
verify_with: python3 scripts/tier0.py
summary: How to verify pages. Tier 0, 1 and 2 and the budget, the age of a verification, the size budget, the report that closes a session
keywords: re-verify, Tier 0, age, size budget
sources_count: 1
---

# Verification: Tier 0, Tier 1 and Tier 2, the age of a verification and the report of a session

Read it when you verify or re-verify pages, plan the budget of a session, write the report that closes it, or meet a warning of Tier 0.

## Three tiers and a budget

"Re-verify every page, every time" is not followable, so it does not get followed. The requirement is bounded, and being bounded it is
mandatory.

**Tier 0, always.** Every static sweep, run with `scripts/tier0.sh` before every commit. No network, no authentication, a few seconds.
It runs: the secret sweep and the em-dash check on the staged diff; the secret rule, high-entropy, mermaid, front matter, `## Sources`
section, link integrity, source-path, index, size-budget, verification-age, foreign-identifier, settings and first-run sweeps on the
tree; and the record-style sweeps (`non-english-text`, `quoted-message`) unless `record_style = off`. Exit code 1 means a blocking
finding. `info` and `warning` never fail the run, they are prompts to look. The tests of the sweeps are `scripts/test_*.py`.

**Tier 1, always.** Every page your task touches, plus every page it links to. Read them fully: you are about to write next to these
claims, so you own them.

**Tier 2, budgeted.** Five pages per session, chosen by blast radius first and staleness second. Do not spend the budget on a library
page while a runbook that can destroy data goes unchecked. Oldest first within a priority group:

```bash
python3 scripts/stalest.py -n 5 operations
```

It prints each page with its status, the age of its date and its `verify_with`, so that a page with a command is run first. It
leaves out the dated records unless you name their folder (`operations/releases`); `-n 0` prints every page. A page marked `stale`
is not moved up: its drift is known.

For each page in Tier 1 and in your Tier 2 budget: run its `verify_with` and compare the output with the body; fix what drifted;
confirm that the `Sources` paths still own the claim; follow every link; set `status` and `last_verified` to what you actually did.
Checking three pages and dating five is worse than dating none. If a `verify_with` cannot run, say why in the body and set
`status: stale` or leave it `unverified`.

## The age of a verification

`status: verified` claims that the evidence was seen on `last_verified`, and the claim ages. Tier 0 warns `verification-aged` for a
`verified` page whose date is more than `verified_max_age_days` days old (30 unless `handbook.cfg` says otherwise). An `unverified`
or `stale` page makes no such claim and does not age. A dated record does not age either (`record_folders` in `handbook.cfg`, by
default `operations/releases` and `architecture/retrospectives`). A `last_verified` that is not a `YYYY-MM-DD` date
(`last-verified-unreadable`) or lies after today (`last-verified-in-the-future`) is reported for every page, because such a page never
ages. The cure for `verification-aged` is to run `verify_with`, compare the pins, then set `last_verified`, or to set the page to
`unverified`. Moving the date without running anything is the failure this check exists to make visible.

## The size budget

A page is at most 60 000 bytes, and `CLAUDE.md` and `INDEX.md` at most 40 000, because every call that holds a page is paid for by
its size and a page over 40 KB is not read whole. Tier 0 warns (`size-over-budget`). A page that is over when the budget is introduced
to an existing handbook is listed in `scripts/size-budget.txt` with its size, and may not grow (`size-over-ratchet`); the list only
shrinks. A page that is over and not listed: split it.

## Not in Tier 0, on purpose

A warning for the words of a state ("not deployed", "planned", "waiting for") on a line with no date is not included: the same
words appear in rules, in designs and in diagrams as often as in claims of a state, so a warning on them tends to be skimmed. The
search stays a command that is run by hand when a change is finished ([keep-documentation-current.md](keep-documentation-current.md)).
Run it on your own handbook before deciding to automate it.

## The report that closes a session

Say what you checked and what you only read: the pages verified (with the command and the result), the pages read and left
`unverified`, the pages you updated because of the change, the hits of a search that you left on purpose, and the warnings of Tier 0
that were there before. "No page needed a change" is a result only if you ran the searches.

## Sources

- team knowledge (2026-10-30), unverified: the conventions of this template, a starting point to adapt to the project
