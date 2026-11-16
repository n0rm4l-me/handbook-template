# First run: say where the truth lives

This file is read once, by the first agent or person who opens an empty copy of this template. Its job is to find out, before any
page is written, **where the truth of each kind of fact lives and how to read it with a command**. Every page of the handbook rests on
that: a `verify_with` is a command that reads a source of truth, and a `## Sources` entry names one.

The result is one page, `reference/sources-of-truth.md`. When it exists and you have read it back with the owner, delete this file
(Tier 0 warns `first-run-pending` while the file exists, and `sources-of-truth-missing` if the page is absent after it is gone).

## How to run it

**An agent** (Claude Code or another) does this when it is asked to start the handbook, or when it finds this file and the page
`reference/sources-of-truth.md` does not exist:

1. Prepare the clone, once: `pip install -r requirements.txt` and `git config core.hooksPath .githooks`. Both change the machine or
   the clone, so say what you are about to run and run it only when the person agrees.
2. Ask the questions below one group at a time (A, then B, and so on), in the person's words. Do not read the answers out of the
   repository: the point is what people know that the repository does not say.
3. Do not guess. An answer you cannot get is written `unknown`, with the name of the person who can give it.
4. For every source named in group B, ask for the command that reads it. If the command only reads, and the person agrees, run it
   and note the result as a `live:` entry in `## Sources` (see `process/frontmatter.md`). A source whose command was not run stays
   `unverified`.
5. Never ask for, accept or write a secret, a token, a password or personal data. If one is offered, say it is not needed and ask
   for the place where it is kept.
6. Write `reference/sources-of-truth.md` in the layout below, then set `handbook.cfg` from E2 and E3 and
   `scripts/foreign-identifiers.txt` from D3.
7. Read the page back with the person. Then write the `README.md` of this handbook from the skeleton in `TEMPLATE.md`, ask before
   you delete `FIRST-RUN.md` and `TEMPLATE.md`, and run `scripts/tier0.sh`: it should end with no warning.
8. Propose the first three pages from A3 and C1 to C3, and open the first pull request (`process/pull-requests.md`).

**A person without an agent** runs `python3 scripts/first_run.py`: it asks the same questions from this file, takes a few lines for
each answer (an empty line ends an answer, `?` or an empty answer means unknown) and writes a first version of the page. An agent can
restructure it later into the layout below.

## The layout of `reference/sources-of-truth.md`

One section per kind of fact from group B, in this form, plus the answers of the other groups as short sections:

```markdown
## Results of automated checks

- Source: the CI of the repository, and the monitoring system for what runs in production
- Read it with: `gh run list --limit 5` (a command), or "no command: a person opens the tool"
- Owner: the name or the role who can change it
- Wins over: the sources it overrides when they disagree
```

The sources differ by team, the questions do not. A few examples of what an answer to the same question looks like:

| Kind of fact | A development team | A QA team | An SRE or operations team |
|---|---|---|---|
| Results of automated checks (B2) | the CI of the repository | the CI, and the test management tool for manual runs | the monitoring and alerting system, the CI of the infrastructure code |
| Work items and defects (B3) | the issue tracker of the repository | the defect tracker | the incident tracker and the on-call tool |
| What runs where (B4) | the deploy pipeline, the manifests of each environment | the list of test environments, the build under test | the cluster, the cloud console, the repository of configuration |
| Data and accounts for non-production work (B5) | fixtures and seed scripts | test accounts and the test data service | the sandbox accounts, the rule for copying production data |
| Decision to ship or change production (B6) | the reviewers of the merge, the release owner | the sign-off record of the release | the change record, the person on call with the right to roll back |

## Questions

### A. What the handbook is for

- **A1** Which team or product is this handbook for, and which systems, repositories and environments does it cover?
  *Why:* a page outside the scope is not written, and the scope tells which sources can be cited.
- **A2** Who reads it first: agents, new joiners, people on call, managers?
  *Why:* it sets the level of detail and what an example looks like.
- **A3** What do people ask again and again, or lose a day on? Name the five most recent.
  *Why:* the first pages should answer real recurring questions; the handbook grows with the work, not to fill a structure.

### B. Where the truth lives

- **B1** Code and tests: which repositories hold them, which branch is the truth, and how do you read them (a clone path, a command)?
  *Why:* a page about behaviour links to the code and pins a commit instead of copying values.
- **B2** Results of automated checks and runs (builds, tests, deployments, jobs, alerts): where do they live, and how do you get the latest result of one of them with a command or a query?
  *Why:* a statement such as "this check is stable" is only as good as the place its result is read from.
- **B3** Work items and defects (requirements, tasks, bugs, incidents): which tracker holds them, and how do you list the open ones for this scope with a command or a query?
  *Why:* the handbook should link to a work item, never keep a copy of its status.
- **B4** Environments: which exist, and how do you tell what runs in each (a command, a dashboard, a repository of configuration)?
  *Why:* "what is deployed where" rots fastest when it is copied, so it must be read from here.
- **B5** Data and accounts for work outside production (test data, fixtures, seed data, sandbox accounts): where do they come from, who may change them, and what is never to be used?
  *Why:* the traps of non-production data cost days, and the rule against real customer data must be written once.
- **B6** Decisions to ship, roll back or change production: who decides that a change is good enough, on what evidence, and where is the decision recorded?
  *Why:* it is among the most asked questions of any team and the one most often answered from memory.
- **B7** Ownership: where is the list of who owns what kept?
  *Why:* a page needs an owner to be re-verified, and a name copied into a page goes out of date.
- **B8** Is there another place that is the truth for this team (a dashboard, a spreadsheet, a wiki) and is not named above?
  *Why:* a source missing from this page is a source the handbook will contradict.
- **B9** When two sources disagree, which one wins, and who settles it?
  *Why:* a handbook that records a conflict without a rule to settle it only moves the argument.

### C. What lives only in people's heads

- **C1** Which decisions were made whose reasons only a few people remember?
  *Why:* each becomes a decision record (`process/adr.md`) while the people are still here.
- **C2** Which failures have a recognisable signature and a known cause (a flaky test, an alert that fires for no reason, an environment quirk, a data trap)?
  *Why:* a failure mode with its signature is the page that saves the most time, and it cannot be derived from code.
- **C3** Which procedures took trial and error to get right?
  *Why:* a verified procedure is the other kind of page that cannot be derived, and it is worth more than any overview.

### D. Safety and boundaries

- **D1** What must never be written into the handbook (secrets, personal data, customer data, internal addresses)?
  *Why:* the repository may be read by more people than the team, and a published value stays in history.
- **D2** Which systems or environments are dangerous to touch, and what needs a human to confirm first?
  *Why:* a runbook that does not say so gets run under time pressure by someone who cannot pause to check.
- **D3** Which other projects, teams or handbooks does this one relate to, and whose names, identifiers or content must not be copied here?
  *Why:* it fills `scripts/foreign-identifiers.txt`, so that a page copied from another handbook is stopped before it is committed.

### E. Working agreement

- **E1** Who owns the handbook, and who reviews a change?
  *Why:* a page nobody owns is not re-verified, and a change nobody reviews is not checked.
- **E2** In which language are the pages written?
  *Why:* the default checks assume English with plain punctuation; another language needs `record_style = off` in `handbook.cfg`.
- **E3** How many days may a page marked verified stay unchecked? The default is 30.
  *Why:* it is `verified_max_age_days` in `handbook.cfg`, and the age warning of Tier 0 uses it.
- **E4** Where does the repository live (organisation, who may read it)?
  *Why:* it decides how careful the rule against secrets and personal data has to be.
