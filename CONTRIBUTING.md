# Contributing

Thank you for looking at this template. It is early, and the most useful thing you can send is what you learned by adopting it in a
real team: a question of the first run that nobody could answer, a check that fired on correct text, a convention that did not fit
your kind of team (development, QA, SRE, data, security). An issue with that is a contribution.

## Before you change anything

The template follows its own rule: write only what cannot be derived from a repository or a live command. The scripts follow a second
one: a check does not depend on a stack. A check for Kubernetes, one cloud or one tracker belongs in the handbook of the team that
needs it (see "Adapting it" in `TEMPLATE.md`), not here.

Set up once per clone:

```bash
pip install -r requirements.txt
git config core.hooksPath .githooks
```

The hook runs the secret sweep and Tier 0 on every commit, and refuses a commit whose `INDEX.md` is out of date (run
`scripts/make-index.sh` and add the file).

## What a change needs

- **A test.** Every script has a `scripts/test_*.py`. Add a passing case and a failing case for the rule you change, in the style of
  the file. A fixture that looks like a secret or a forbidden word is assembled from parts at run time, so that the test does not trip
  the sweep it tests.
- **All the tests, and Tier 0.** Run each file, then Tier 0. A fresh copy gives exactly one warning, `first-run-pending`.

  ```bash
  for t in scripts/test_*.py; do python3 "$t" || break; done
  scripts/tier0.sh
  ```

- **The text rules of the repository.** Files are in English with plain punctuation: no em dash, no quoted conversations. Tier 0 checks
  it, because this repository uses its own handbook settings.
- **No secret, no real identifier.** Not in an example, not in a test fixture, not in a commit message. Use a capitalised placeholder.
- **The documentation says what the code does.** A change is finished when every page that states the old behaviour says the new one
  (`process/keep-documentation-current.md`). Fix a `summary:` that a change made untrue, and regenerate `INDEX.md`.

## Pull requests

One branch, one pull request. Read your own diff before you push. Describe what was wrong and the cause, what changes, what you tested
and what you did not. End the description with the line that `process/pull-requests.md` describes: which model or tool helped, or
`none`, and who owns the change. Review findings are claims to check: a finding is closed when it is fixed or answered with evidence.

## License

By contributing you agree that your contribution is licensed under the MIT license of the repository (`LICENSE`).
