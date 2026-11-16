---
status: unverified
last_verified: 2026-10-30
verify_with: n/a
summary: When to write a decision record, how to number and structure it, and the states of its status line
keywords: decision record, ADR
sources_count: 1
---

# Decision records (ADR): when to write one and how

Read it when you add or change a decision record in `architecture/decisions/`.

Write one when a change has real trade-offs that someone will need to reconstruct later, not for every change. A schedule tweak or a
renamed setting does not need one; replacing a tool, or choosing between two designs with different failure modes, does. A fact that
is only a fact belongs in a page of `architecture/` or `reference/`.

1. **Number it sequentially**, `0001-kebab-case-title.md`. Check the highest existing number first; do not guess or reuse one.
2. **Use the standard front matter.** The `Sources` of a decision record carry more weight than those of a page: its whole point is
   that its claims can be traced back, so pin every version, commit, live check and document that fed the decision.
3. **Put one line right after the title: `**Status:** <state>.`** The states are `proposed` (nothing is implemented), `proposed,
   actively being tested` (an experiment runs and the record is edited in place as it produces results), `accepted`, and
   `superseded by ADR NNNN`. Say plainly what has and has not happened; never write `accepted` for an idea.
4. **Keep the shape:**
   - `## Context`: why the decision has to be made now.
   - `## Options`, plural, even when one is clearly favoured. Record what was rejected and why, so that the next reader who thinks of
     the same option finds out why it does not work. Mark a mechanism nobody has run as an open question, not as a fact.
   - `## Decision`: what was chosen, or `Not made yet` and what would settle it.
   - `## Consequences`: the blast radius, and what this record does not decide.
5. **A record in `proposed, actively being tested` is edited in place**, with a dated section for what was done and found, until the
   experiment ends. Do not replace it with a new file while it runs.
6. **Link both ways.** If a record formalises or supersedes an item of a plan or another record, say so in it and make the other
   point back.

## Sources

- team knowledge (2026-10-30), unverified: the conventions of this template, a starting point to adapt to the project
