---
status: unverified
last_verified: 2026-10-30
verify_with: n/a
summary: What to do when a change or a release is finished. Which pages state the old fact, the two searches, the full read and the report of the session
keywords: git grep, old value
sources_count: 1
---

# Keep the documentation current: the full rule

Read it when you finish a change or a release, and when you find a statement that is no longer true.

**The documentation is part of every change, and a statement that is no longer true is a defect to fix when you find it, not a note
to leave for the next reader.** A wrong page is worse than an empty one, because it is trusted. The usual ways a page goes wrong: a
service described as "not deployed" the day after it was deployed, a pull request "open" a day after it was merged, a count that
moved, a command that fails as written.

1. **A change is finished when every page that states the old fact says the new one.** The usual places are the page of the
   component, its runbook, the inventories (`reference/`, the index of components), the status line of a decision record, the
   diagrams, and `CLAUDE.md`. Anything that carries a state ("not deployed", "planned", "open", "waiting", "blocked", a version, a
   count, an owner) is the most perishable text in the handbook and is looked at first.
2. **Find the pages by searching, not by memory.** Before you call a change done, search the whole tree for the old value and for
   the words that described the old state, and read every hit. A hit that is history (a dated line, the record of a trap) stays,
   with the current state added beside it and dated.

```bash
git grep -n -i -E "OLD_VALUE|OLD_PHRASE" -- '*.md'
```

```bash
git grep -n -i -E "not deployed|not yet|planned|does not exist|waiting for|blocked" -- '*.md'
```

   The second search is broad on purpose; add the name of the thing you changed to narrow it.
3. **A wrong statement found while reading is fixed in that session**, whatever you came for. Fix it with the evidence (the command,
   or the path with its revision) in `Sources`, and mark `status: stale` with a line saying what drifted if you cannot settle it. Do
   not leave a known error in a page, and do not report it instead of fixing it unless the fix is a decision that is not yours.
4. **A dated statement of state is history, not the present.** "State on DATE", "live DATE", "as of DATE" describe that day. When the
   system has moved on, add the current state next to it with its own date; keep the old line when it records how a failure looked.
5. **A full read is done when asked, and by the end of any stretch of work that changed many things at once** (a release of several
   components, a change of plan, a day of findings): one reader per set of pages, each checking the claims that depend on time or
   state against the sources of truth and fixing what is wrong in place.
6. **Say what you did in the report of the session.** Name the pages you updated because of the change and the hits you left on
   purpose.

Tier 0 cannot do this for you: it finds a broken link, a missing front matter key and an old `verified` date, and it cannot tell that
a sentence became false. That check is yours.

## Sources

- team knowledge (2026-10-30), unverified: the conventions of this template, a starting point to adapt to the project
