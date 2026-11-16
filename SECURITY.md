# Security

This repository holds conventions and scripts, not a service. The part that matters for security is the check that keeps secrets out
of a handbook: `scripts/secret_sweep.py`, the pre-commit hook and the CI job that run it.

## Reporting a problem

Use the private reporting of the hosting site ("Report a vulnerability" in the Security tab of the repository) for:

- a secret or a credential shape that the sweep lets through,
- a script that runs, writes or deletes something it should not when it reads a hostile page or configuration,
- a way to make the checks report a pass while the tree is not clean.

Do not open a public issue that contains a real secret, and do not paste one into a report: describe its shape instead. A missed
pattern is reported by its name and a made-up example.

## If a secret has been committed

Rotate it first, then remove it. Removing it from git does not undo a disclosure.
