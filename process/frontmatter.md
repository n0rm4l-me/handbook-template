---
status: unverified
last_verified: 2026-10-30
verify_with: python3 scripts/tier0.py
summary: What the front matter of a page holds. Required keys, summary and keywords, the section Sources, what verified, unverified and stale mean, the meaning of n/a
keywords: front matter, sources, n/a
sources_count: 1
---

# Front matter: the required keys, the meaning of status and the forms of a Sources entry

Read it whenever you write, change or interpret the front matter of a page.

## The required keys

Required on every page except the root files of the project (`README.md`, `CLAUDE.md`, `AGENTS.md`, `INDEX.md` which is generated,
`CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`), the Markdown files inside a folder whose name starts with a dot
(`.github`), and the two temporary files `FIRST-RUN.md` and `TEMPLATE.md`:

```yaml
---
status: verified | unverified | stale
last_verified: YYYY-MM-DD
verify_with: <one command that re-checks the core claim, or n/a>
summary: <the question the page answers, one line>    # optional, at most 160 characters
keywords: <extra terms to grep for>                    # optional, at most 100 characters, each one must appear in the page
sources_count: <the number of entries in the section "## Sources">
---
```

The last section of the page is `## Sources`, one list item for each entry, each on one line (a continuation line is refused by
Tier 0 as `sources-entry-malformed`).

## What status means

`status` is a claim about evidence, not about confidence:

- `verified`: you ran the commands and saw the output. Nothing else earns this.
- `unverified`: you read the code and inferred, or a person told you. Correct until proven otherwise, but unproven.
- `stale`: you know it drifted. Say so in the body and keep the file.

Never mark a page `verified` because it looks right. If you did not execute it, it is `unverified`. Downgrading a page you could not
check is the useful action. A `verified` page ages: Tier 0 warns when its `last_verified` is older than `verified_max_age_days`
in `handbook.cfg` ([verification.md](verification.md)).

`verify_with` must be runnable as written, with a capitalised placeholder where a value depends on the environment. Never put a
plausible-looking real value in a placeholder slot.

## The meaning of n/a

`verify_with: n/a` is right for a page that states no present state, so that no command can re-check it: a dated record (a release,
a retrospective, the result of a measurement run), a proposal that is not live, a page of questions, a page of history. It is a gap on
a page that states the present state of the system, even when the page is also a procedure or a checklist: a status column, a line
such as "applied since DATE", a count of what runs. That page needs a command, or a line in its body that says why it has none.
Tier 0 cannot tell the two kinds apart; `python3 scripts/stalest.py` prints the `verify_with` of each page it lists, so a gap is seen
when the page comes up for re-verification.

## The forms of a Sources entry

A `Sources` entry without a version is not a source, it is a gesture. Use one of four forms:

- `<repo> @ <tag-or-commit>` for anything read out of source. Use the version that is deployed, not the one your clone sits on.
- `<repo/path>, commit <hash>` for a file whose content is the claim. Pin the commit of that file (`git log -1 --format=%h -- PATH`),
  not a date: a date says when you looked, a hash lets the next agent diff forward.
- `live: <command> <YYYY-MM-DD> (<result>)` for output from a running system. Record the result, including a negative one.
- `team knowledge (<YYYY-MM-DD>), unverified: <which claims>` when a person told you. Name the claims, so that a later reader knows
  what has no artifact behind it. Everything else on the page must trace to a path.

A bare `repo/path` entry is checked by Tier 0 (`source-path-gone`) against this repository and against sibling clones one directory
up (set `SIBLING_REPOS_ROOT` if yours are elsewhere). `live:` and `team knowledge` entries are checked by nothing, by design.

## Re-verification is incremental

When you re-verify a page, do not re-read every source. Compare each pinned version with what is current and re-read only the ones
that moved. Then update the pin. A page whose pins all still match needs a `last_verified` bump and nothing else; saying so in the
report is a real result.

## A second colon in a header value breaks the parser

A plain `key: value` line of the header must not contain a second `: `: the parser reads it as the start of a nested mapping and
fails. This breaks `summary: Two colons: the second one fails`. Fix it with a comma or parentheses, not with quotes. The entries of
`## Sources` are Markdown, so a colon inside them breaks nothing.

## Sources

- team knowledge (2026-10-30), unverified: the conventions of this template, a starting point to adapt to the project
