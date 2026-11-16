---
status: unverified
last_verified: 2026-10-30
verify_with: n/a
summary: How to open, update and merge a pull request. The description, the local review before each push, the review findings, and the line that says who wrote it
keywords: pull request, review, description
sources_count: 1
---

# Pull requests: the description, the review and the line that says who wrote it

Read it when you open, update, review or merge a pull request in this repository, before the first push.

1. **One branch, one pull request.** Do not split a change into a stack of pull requests that wait for each other when nobody reviews
   the stack: the merges cascade. Split only when a reviewer asks for it.
2. **Review your own diff locally before every push.** Read `git diff origin/main...HEAD` file by file as a reviewer would, run
   `scripts/tier0.sh` and the tests of the scripts you touched, and run the code review of your tool on the diff, or ask a second agent
   that has not seen your reasoning. A pull request pushed early turns into rounds of waiting. If it needs more than three rounds,
   read the whole diff again from the top before the fourth push.
3. **Write the description for a reviewer who was not in the conversation, and make it true.** What was wrong and the cause, what
   changes, a table of what was tested with the result (and what was not), what has to change outside the repository and in what
   order, and what is left out. The numbers match the diff: read `git diff --stat` before writing "a couple of files". Look at the list
   of files before the first push for tool output, caches and local files.
4. **Treat every review finding as a claim to verify, not as a fact.** A reviewer, human or automatic, can cite a function, a line or a
   behaviour that does not exist, or describe a real line wrongly. Reproduce the finding first (read the cited line at the cited
   commit, run a short script, check the cited behaviour). Then either fix it, with a test where one fits, and reply with the commit;
   or answer with the evidence that it is wrong, and do not change the code to please the review. In both cases the reply says what
   was checked.
5. **Do not merge, and do not say a pull request is ready, while a finding is open.** A finding is closed when it was fixed or answered
   with evidence. Merging is a decision of the owners of the repository; an agent merges only when told to, for that pull request.
6. **A review that arrives after a merge is still owed.** Treat its findings as open work and fix the real ones in a follow-up.
7. **When a review finds one instance of a class, audit the whole class** before the next push, and write the class down where the
   next agent reads it (a page of this handbook), as a check with a command and not as advice.
8. **End the description with the line that says who wrote it:** `AI: ` and the real model id of the session and of each reviewer or
   agent it used, or `none`, then `Owner: ` and the login of the person. It is the only way a later reader can tell which parts were
   checked by a person.

## Sources

- team knowledge (2026-10-30), unverified: the conventions of this template, a starting point to adapt to the project
