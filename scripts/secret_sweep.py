#!/usr/bin/env python3
"""Hard rule: no secret in this repository, in any file, ever.

If you keep this file in several repositories, keep one of them as the copy to edit and the others identical. It uses the
standard library only, so it runs in a pre-commit hook and in CI without installing anything.

    python3 scripts/secret_sweep.py             # the staged changes (what the pre-commit hook runs)
    python3 scripts/secret_sweep.py --tree      # every tracked file as it is now
    python3 scripts/secret_sweep.py --history   # every line ever added on any branch

Exit code 1 when something is found. It prints where (file and line) and why, and never the matching text:
a finding is a secret until proven otherwise, and the output of a check must not become a second copy of it.
A hit means: do not commit, and if it was committed, rotate the value first and only then remove it. Removing it
from git does not undo a disclosure.

History cannot be rewritten, so a false positive that is already in a commit would be reported for ever. A person
who has looked at it records `COMMIT8 path:line` in scripts/secret_sweep_reviewed.txt (eight characters of the
commit, no content), and only `--history` honours that file. In the tree and in staged changes a false positive is
fixed by rewording the line, never by listing it.

Patterns that would match this file are assembled at run time, so that the sweep does not report itself.
"""
import re
import subprocess
import sys
from pathlib import Path

# Words that, followed by an assignment, look like a credential. A value that is a bare true or false is skipped: a switch is not a credential, and
# some Kubernetes and Terraform settings have credential-sounding names with boolean values (for example the one that stops a pod mounting its
# service account token). A quoted "true", or a word that only begins with true or false, is still a finding.
ASSIGNED_SECRET = re.compile(
    r"(api[_-]?key|password|passwd|secret|token|bearer|private[_-]?key)[^a-z]*[=:]\s*(?!(?:true|false)\b)\S", re.IGNORECASE
)
# Lines that are a placeholder or a reference, not a value.
ALLOWED = re.compile(
    r"REDACTED|<[a-z_ -]+>|\$\{?[A-Z_]+\}?|CAPS|secretKeyRef|secretName|name:|-secret|_secret|SECRET_VALUE|secret_id|"
    r"\bsecret\s*:\s*(\{\}|$)",
    re.IGNORECASE,
)
# Shapes that are a secret whatever they are called. No allowance for these.
KNOWN_SHAPES = {
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "private key block, base64 encoded": re.compile("LS0tLS1C" + "RUdJTi"),
    "service account key file": re.compile(r'"private_key_id"\s*:'),
    "GitHub credential": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack credential": re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}"),
}
# A long hexadecimal literal in quotes or after an equals sign.
LONG_HEX = re.compile(r"""["'=][0-9a-f]{32,}["']?""")
# Lines where a long hexadecimal value is a digest, not a secret.
NOT_A_SECRET_HEX = re.compile(r"sha256|sha512|digest|checksum|\bzh:|\bh1:", re.IGNORECASE)
# A file kept out of the repository by its name, whatever it holds.
FORBIDDEN_NAME = re.compile(
    r"(\.pem|\.key|\.p12|\.pfx|\.jks|\.keystore|\.tfstate(\.backup)?|\.tfvars(\.json)?|\.tfplan|\.kubeconfig)$"
    r"|(^|/)(tfplan|kubeconfig|credentials\.json|id_rsa|id_ed25519|\.env(\..+)?)$"
    r"|-credentials\.json$|(^|/)gha-creds-.*\.json$",
    re.IGNORECASE,
)
# Files whose long hexadecimal lines are hashes of providers, not secrets.
HEX_EXEMPT_FILES = {".terraform.lock.hcl"}


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd, errors="replace")
    return r.stdout


def scan_line(path, line):
    """Return the reasons this line is a finding, as short labels."""
    reasons = []
    name = Path(path).name
    for label, pattern in KNOWN_SHAPES.items():
        if pattern.search(line):
            reasons.append(label)
    if ASSIGNED_SECRET.search(line) and not ALLOWED.search(line):
        reasons.append("a credential assigned a value")
    if name not in HEX_EXEMPT_FILES and LONG_HEX.search(line) and not NOT_A_SECRET_HEX.search(line):
        reasons.append("a long hexadecimal literal")
    return reasons


def added_lines(diff_text):
    """Yield (path, line number, text) for every added line of a -U0 diff."""
    path, lineno = None, None
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            p = raw[4:]
            path = None if p == "/dev/null" else (p[2:] if p.startswith("b/") else p)
            lineno = None
        elif raw.startswith("@@"):
            m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            lineno = int(m.group(1)) if m else None
        elif raw.startswith("+") and not raw.startswith("+++") and path and lineno is not None:
            yield path, lineno, raw[1:]
            lineno += 1


def findings_in_diff(diff_text, prefix=""):
    out = []
    for path, lineno, text in added_lines(diff_text):
        for reason in scan_line(path, text):
            out.append((f"{prefix}{path}:{lineno}", reason))
    return out


def forbidden_names(paths, prefix=""):
    return [(f"{prefix}{p}", "a file type that must never be committed") for p in paths if FORBIDDEN_NAME.search(p)]


def scan_staged():
    diff = git("diff", "--cached", "-U0", "--no-color")
    names = git("diff", "--cached", "--name-only", "--diff-filter=AM").split("\n")
    return findings_in_diff(diff) + forbidden_names([n for n in names if n])


def scan_tree():
    out = []
    root = Path(git("rev-parse", "--show-toplevel").strip())
    tracked = [p for p in git("ls-files").split("\n") if p]
    out += forbidden_names(tracked)
    for p in tracked:
        f = root / p
        if not f.is_file():
            continue
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for reason in scan_line(p, line):
                out.append((f"{p}:{i}", reason))
    return out


def reviewed_history_findings():
    """The `COMMIT8 path:line` entries a person has reviewed and cleared, from scripts/secret_sweep_reviewed.txt."""
    f = Path(git("rev-parse", "--show-toplevel").strip()) / "scripts" / "secret_sweep_reviewed.txt"
    if not f.is_file():
        return set()
    return {ln.split("#")[0].strip() for ln in f.read_text().splitlines() if ln.split("#")[0].strip()}


def scan_history():
    out = []
    commits = [c for c in git("rev-list", "--all").split("\n") if c]
    for c in commits:
        diff = git("show", "--no-color", "-U0", "--format=", c)
        out += findings_in_diff(diff, prefix=f"{c[:8]} ")
        names = git("show", "--name-only", "--format=", "--diff-filter=AM", c).split("\n")
        out += forbidden_names([n for n in names if n], prefix=f"{c[:8]} ")
    reviewed = reviewed_history_findings()
    return [(where, why) for where, why in out if where not in reviewed]


def main(argv):
    mode = "--staged"
    for a in argv[1:]:
        if a in ("--staged", "--tree", "--history"):
            mode = a
    found = {"--staged": scan_staged, "--tree": scan_tree, "--history": scan_history}[mode]()
    for where, why in found:
        print(f"SECRET? {where}: {why} (the value is not printed)")
    print(f"secret sweep {mode[2:]}: {len(found)} finding(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
