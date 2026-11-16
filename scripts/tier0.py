#!/usr/bin/env python3
"""Run every Tier 0 sweep CLAUDE.md requires before a commit, in one command.

Usage:
    python3 scripts/tier0.py [--json]

Scoping matches CLAUDE.md: the secret and em-dash sweeps are diff-scoped to staged changes
(`git diff --cached`), because a repo-wide grep buries the one line you just wrote; every
other sweep is repo-wide, because Tier 0 runs before every commit to catch pre-existing rot
too, not just what this change introduces.

The record-style sweeps (`em-dash`, `non-english-text`, blocking, and `quoted-message`, a warning) can be switched off with
`record_style = off` in handbook.cfg. The language sweeps read the working tree of every tracked text file, not a diff, because the
rule (CLAUDE.md, "Records are formulations, not conversations") covers what is already there as much as what is added. They report
the file, the line and the reason, never the text.

Exit code is 0 if there are no blocking findings, 1 otherwise. `info` and `warning` findings
never fail the run; they are signals to look at.
"""
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import secret_sweep  # noqa: E402
from common import (  # noqa: E402
    EM_DASH,
    ENTROPY_PATTERN,
    INDEX_FIELD_LIMITS,
    NOT_ORPHANS,
    ROOT_PROJECT_FILES,
    SETTINGS_FILE,
    TEMPORARY_FILES,
    body_without_sources,
    NO_FRONTMATTER_FILES,
    PAGE_BUDGET_BYTES,
    QUOTED_MESSAGE_PATTERNS,
    RECORD_FOLDERS,
    REQUIRED_FRONTMATTER_KEYS,
    SECRET_ALLOW,
    SECRET_PATTERN,
    SIZE_BUDGET_FILE,
    SIZE_BUDGET_SLACK_BYTES,
    SPECIAL_BUDGET_BYTES,
    VERIFIED_MAX_AGE_DAYS,
    folder_prefixes,
    foreign_scripts,
    iter_markdown_files,
    iter_text_files,
    log,
    parse_frontmatter,
    source_entries,
    split_frontmatter,
    text_lines,
    load_settings,
    under_folders,
    verified_date,
)

HANDBOOK_ROOT = Path(__file__).resolve().parent.parent
# Sibling clones of the repositories that pages cite as sources (a cited `repo/path` is looked for here). Overridable for
# anyone whose clones do not live one directory up.
SIBLING_REPOS_ROOT = Path(os.environ.get("SIBLING_REPOS_ROOT", str(HANDBOOK_ROOT.parent))).resolve()

HUNK_HEADER_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def run(args, cwd=None, timeout=30, env=None):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


# The variables with which git names the repository it works on. A git hook runs with them set to the repository being
# committed, and they beat `git -C OTHER_REPO`: every question about a sibling clone would then be answered by this
# repository ("not found at HEAD", "no block"). The sweeps that read a sibling clone run git without them.
GIT_REPOSITORY_VARIABLES = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_NAMESPACE", "GIT_QUARANTINE_PATH",
)


def run_in_sibling(args, timeout=30):
    """run() for a git command on a sibling clone: the environment without the variables that name the repository."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_REPOSITORY_VARIABLES}
    return run(args, timeout=timeout, env=env)


def add(report: dict, bucket: str, check: str, detail: str):
    report[bucket].append({"check": check, "detail": detail})


def rel(path: Path) -> str:
    return str(path.relative_to(HANDBOOK_ROOT))


def sh_diff_cached(pathspec: str) -> str:
    _, out, _ = run(["git", "diff", "--cached", "-U0", "--", pathspec], cwd=HANDBOOK_ROOT)
    return out


def iter_added_lines_with_location(diff_text: str):
    """Yield (relpath, lineno, line_text) per added line in a -U0 diff.

    Findings report file and line, never the matched text of a secret sweep: CLAUDE.md is
    explicit that a secret finding must not reproduce the value.
    """
    current_file = None
    next_lineno = None
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:]
            current_file = path[2:] if path.startswith("b/") else path
            next_lineno = None
            continue
        if raw.startswith("@@"):
            m = HUNK_HEADER_PATTERN.match(raw)
            next_lineno = int(m.group(1)) if m else None
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            if current_file is not None and next_lineno is not None:
                yield current_file, next_lineno, raw[1:]
                next_lineno += 1


# --- The two diff-scoped sweeps ---

def sweep_secrets(report: dict):
    # Not scoped to *.md: the rule is "no secret value in any file, ever".
    for relpath, lineno, line in iter_added_lines_with_location(sh_diff_cached(".")):
        if SECRET_PATTERN.search(line) and not SECRET_ALLOW.search(line):
            add(report, "blocking", "secret", f"{relpath}:{lineno} (value redacted, do not print or commit it)")


def sweep_em_dash(report: dict):
    # *.md on purpose: the no-em-dash rule is a documentation convention, not a rule about code.
    for relpath, lineno, line in iter_added_lines_with_location(sh_diff_cached("*.md")):
        if EM_DASH in line:
            add(report, "warning", "em-dash", f"{relpath}:{lineno}: {line.strip()[:200]}")


# --- Repo-wide sweeps ---

def sweep_secret_rule(report: dict):
    """The hard rule: no secret in any tracked file.

    Runs the same scan as the pre-commit hook and CI (scripts/secret_sweep.py, tree mode).
    """
    os.chdir(HANDBOOK_ROOT)
    for where, why in secret_sweep.scan_tree():
        add(report, "blocking", "secret-rule", f"{where}: {why} (the value is not printed)")


MERMAID_TYPES = re.compile(
    r"^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline|"
    r"gitGraph|quadrantChart|requirementDiagram|block-beta|architecture-beta|C4\w+)\b"
)
MERMAID_AS_OF = re.compile(r"\bas of 20\d\d-\d\d-\d\d", re.IGNORECASE)


def sweep_mermaid(report: dict):
    """Every mermaid diagram must be a closed block that starts with a diagram type, and carry an "As of DATE" caption.

    A diagram that does not render shows as a red box on GitHub and tells the reader nothing, and a diagram without a date
    cannot be told from a stale one. Only the structure is checked: whether the picture is still true is for the person who
    changes the system (process/keep-documentation-current.md lists the diagrams among the places that state a fact).
    """
    for path in iter_markdown_files(HANDBOOK_ROOT):
        lines = path.read_text(errors="replace").splitlines()
        i, n = 0, len(lines)
        while i < n:
            stripped = lines[i].strip()
            if not (stripped.startswith("`" * 3) and stripped[3:].strip().lower().startswith("mermaid")):
                i += 1
                continue
            start = i + 1
            body, j = [], i + 1
            while j < n and not lines[j].strip().startswith("`" * 3):
                body.append(lines[j])
                j += 1
            if j >= n:
                add(report, "blocking", "mermaid-unclosed", f"{rel(path)}:{start}: the block is never closed")
                break
            first = next((ln.strip() for ln in body if ln.strip() and not ln.strip().startswith("%%")), "")
            if not first:
                add(report, "blocking", "mermaid-empty", f"{rel(path)}:{start}: the block is empty")
            elif not first.startswith("---") and not MERMAID_TYPES.match(first):
                add(report, "blocking", "mermaid-unknown-type", f"{rel(path)}:{start}: starts with {first[:40]!r}, not a diagram type")
            before = [ln for ln in lines[max(0, i - 4):i] if ln.strip()]
            if not any(MERMAID_AS_OF.search(ln) for ln in before):
                add(report, "warning", "mermaid-no-date", f"{rel(path)}:{start}: no 'As of YYYY-MM-DD' line just above the diagram")
            i = j + 1


# --- The language rule: records are in English and are formulations, not conversations ---

NOT_TEXT_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".woff", ".woff2"}


def tracked_text_files(root: Path) -> list:
    """Every tracked file of the repository that is text (git ls-files), or every text file in the tree when `root` is not a git
    repository (the fixtures of the tests). A file that is not valid UTF-8 is not text and is skipped by the caller."""
    rc, out, _ = run(["git", "-C", str(root), "ls-files", "-z"], timeout=30)
    if rc != 0:
        return [p for p in iter_text_files(root) if p.suffix not in NOT_TEXT_SUFFIXES]
    return [root / name for name in out.split("\0") if name and Path(name).suffix not in NOT_TEXT_SUFFIXES]


def sweep_non_english_text(report: dict):
    """A line with a letter outside the Latin alphabet is a blocking finding, in any tracked text file.

    The rule (CLAUDE.md, "Records are formulations, not conversations"): everything recorded here is in
    English. Symbols, arrows, box drawing, emoji, accents on Latin letters and the zero-width characters are not letters and
    pass. The finding names the file, the line and the scripts found, never the text: a sweep that printed the line would
    repeat what it is there to keep out. The name of a file is read too (and is printed, because the path is the finding).

    A tracked file that is not valid UTF-8 is a finding as well, because text in another encoding (Shift-JIS, GBK, Latin-1,
    UTF-16) cannot be read here and would pass unseen. A file that holds a NUL byte and no UTF-16 mark is binary and is skipped.
    """
    for path in tracked_text_files(HANDBOOK_ROOT):
        name_scripts = foreign_scripts(rel(path))
        if name_scripts:
            add(report, "blocking", "non-english-text", f"{rel(path)}: the file name has letters outside the Latin alphabet ({', '.join(name_scripts)}); records are in English only")
        try:
            data = path.read_bytes()
        except OSError:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            if b"\0" in data and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            add(report, "blocking", "non-english-text", f"{rel(path)}: not valid UTF-8, so it cannot be read as English text; save it as UTF-8")
            continue
        for lineno, line in enumerate(text_lines(text), 1):
            scripts = foreign_scripts(line)
            if scripts:
                add(report, "blocking", "non-english-text", f"{rel(path)}:{lineno}: letters outside the Latin alphabet ({', '.join(scripts)}); records are in English only")


def sweep_quoted_message(report: dict):
    """A phrase that introduces the quotation of a person is a warning, in every Markdown page.

    The rule is the same as above: a record states the decision or the fact, not the message that carried it. A warning and
    not a blocker, because a quotation of code, an error message, a title or the name of a rule is legitimate, and the sweep
    cannot tell them apart. Lines inside a fenced block and text in backticks are not looked at. Like the sweep above it names
    the file, the line and the phrase, not the text.
    """
    for path in iter_markdown_files(HANDBOOK_ROOT):
        fence = False
        for lineno, line in enumerate(text_lines(path.read_text(errors="replace")), 1):
            if line.strip().startswith("`" * 3):
                fence = not fence
                continue
            if fence:
                continue
            prose = re.sub(r"`[^`]*`", "", line)
            for why, pattern in QUOTED_MESSAGE_PATTERNS:
                if pattern.search(prose):
                    add(report, "warning", "quoted-message", f"{rel(path)}:{lineno}: {why}")
                    break


def sweep_entropy(report: dict):
    for path in iter_markdown_files(HANDBOOK_ROOT):
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if ENTROPY_PATTERN.search(line):
                add(report, "blocking", "entropy", f"{rel(path)}:{i}")


def sweep_yaml_frontmatter(report: dict):
    for path in iter_markdown_files(HANDBOOK_ROOT):
        content = path.read_text(errors="replace")
        if not content.startswith("---"):
            if path.name not in NO_FRONTMATTER_FILES or path.parent != HANDBOOK_ROOT:
                add(report, "blocking", "missing-frontmatter", f"{rel(path)}: no frontmatter block")
            continue
        data, err = parse_frontmatter(content)
        if err:
            add(report, "blocking", "broken-frontmatter-yaml", f"{rel(path)}: {err}")
            continue
        missing = REQUIRED_FRONTMATTER_KEYS - (data or {}).keys()
        if missing:
            add(report, "blocking", "missing-frontmatter-key", f"{rel(path)}: missing {', '.join(sorted(missing))}")


# The sources of a page: the final section "## Sources" and the header key `sources_count` (process/frontmatter.md).
def sources_findings(data: dict, content: str) -> list:
    """(check, detail) for the sources of one page that has a front matter. Pure, so that it is tested without a repository."""
    findings = []
    if "sources" in data:
        findings.append(("sources-in-front-matter", "the entries are in the header as `sources:`; move them to the final section '## Sources' and write `sources_count:` in their place (process/frontmatter.md)"))
        return findings
    entries, problems = source_entries(content)
    findings.extend(problems)
    if any(check == "missing-sources-section" for check, _ in problems):
        return findings
    count = data.get("sources_count")
    if count is None:
        return findings  # sweep_yaml_frontmatter reports the missing key
    if isinstance(count, bool) or not isinstance(count, int) or count != len(entries):
        findings.append(("sources-count-mismatch", f"`sources_count:` says {count!r} and the section '## Sources' has {len(entries)} entries"))
    return findings


def sweep_sources_section(report: dict):
    for path in iter_markdown_files(HANDBOOK_ROOT):
        content = path.read_text(errors="replace")
        data, err = parse_frontmatter(content)
        if err or data is None:
            continue
        for check, detail in sources_findings(data, content):
            add(report, "blocking", check, f"{rel(path)}: {detail}")


def indexed_pages() -> set:
    """The paths that the rows of INDEX.md name. A page the index lists is found from the entry point, so it is not an orphan; the
    index is generated and Tier 0 fails when it is out of date, so a page that is missing from it is reported by that check."""
    index = HANDBOOK_ROOT / "INDEX.md"
    if not index.is_file():
        return set()
    return {m.group(1) for m in re.finditer(r"^\| ([^ |]+\.md) \|", index.read_text(errors="replace"), re.M)}


def sweep_link_integrity(report: dict):
    link_re = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    files = list(iter_markdown_files(HANDBOOK_ROOT))
    rel_files = [rel(f) for f in files]
    graph = {f: set() for f in rel_files}
    broken = []
    for path, relpath in zip(files, rel_files):
        content = path.read_text(errors="replace")
        for m in link_re.finditer(content):
            target = m.group(2).strip()
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part = target.split("#")[0]
            if not path_part:
                continue
            resolved = os.path.normpath(str(path.parent / path_part))
            if resolved.endswith(".md"):
                resolved_rel = os.path.relpath(resolved, HANDBOOK_ROOT)
                if os.path.isfile(HANDBOOK_ROOT / resolved_rel):
                    graph[relpath].add(resolved_rel)
                else:
                    broken.append((relpath, target))
    incoming = {f: set() for f in rel_files}
    for f, targets in graph.items():
        for t in targets:
            incoming.setdefault(t, set()).add(f)
    for relpath, target in broken:
        add(report, "blocking", "broken-link", f"{relpath} -> {target}")
    listed = indexed_pages()
    for f in rel_files:
        if not incoming.get(f) and f not in NOT_ORPHANS and f not in listed and f not in TEMPORARY_FILES:
            add(report, "warning", "orphaned-page", f)


def sources_text(content: str) -> str:
    """The sources of a page as list lines ("- entry"), wherever the page keeps them, for the sweeps that read the entries."""
    entries, _ = source_entries(content)
    return "\n".join("- " + e for e in entries)


# A bare-path source citation looks like "repo-name/some/path", optionally followed by a
# parenthetical note. It deliberately excludes a tag pin (" @ "), a `live:` or `team knowledge`
# citation (checked by nothing, by design).
BARE_PATH_SOURCE_PATTERN = re.compile(r"^-\s+([a-zA-Z0-9_-]+/[^\s@]+?)(?:\s*\(.*\))?\s*$")

# A cited path starting with one of these is a cross-reference to another page in *this* repo,
# not to a sibling repo. Checking it against the sibling root instead is exactly backwards.
HANDBOOK_ROOT_FILES = ROOT_PROJECT_FILES


def handbook_top_level_dirs() -> set:
    """The first part of the path of every folder of this handbook (the index folders and the record folders of handbook.cfg), and scripts."""
    settings, _ = load_settings(HANDBOOK_ROOT)
    return {folder.split("/", 1)[0] for folder in settings["index_folders"] + settings["record_folders"]} | {"scripts"}


def resolve_source_target(cited: str) -> Path:
    top = cited.split("/", 1)[0]
    if top in handbook_top_level_dirs() or cited in HANDBOOK_ROOT_FILES:
        return HANDBOOK_ROOT / cited
    return SIBLING_REPOS_ROOT / cited


def sweep_sources_path_exists(report: dict):
    for path in iter_markdown_files(HANDBOOK_ROOT):
        raw = sources_text(path.read_text(errors="replace"))
        if not raw:
            continue
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            if any(tag in stripped for tag in (" @ ", "live:", "team knowledge")):
                continue
            m = BARE_PATH_SOURCE_PATTERN.match(stripped)
            if not m:
                continue
            cited = m.group(1)
            if "*" in cited:
                base = HANDBOOK_ROOT if cited.split("/", 1)[0] in handbook_top_level_dirs() else SIBLING_REPOS_ROOT
                if not list(base.glob(cited)):
                    add(report, "warning", "source-path-gone", f"{rel(path)}: sources cites {cited} (glob), no match under {base}")
                continue
            target = resolve_source_target(cited)
            if not target.exists():
                add(report, "warning", "source-path-gone", f"{rel(path)}: sources cites {cited}, not found at {target}")


# --- INDEX.md: generated from the front matter of the pages (scripts/make-index.sh) ---

MAKE_INDEX = Path(__file__).resolve().parent / "make-index.sh"


def index_field_findings(raw: str, data: dict, content: str = "") -> list:
    """(check, detail) for the `summary:` and `keywords:` of one page that has a front matter.

    The index script reads the two keys as plain one-line values, so the YAML parser and the script must see the same text: a
    value that is quoted, folded, followed by a comment, holds a "|" or is not text is `frontmatter-not-plain`, and a value over the
    limit is `summary-too-long` or `keywords-too-long`. A page without `summary:` is `missing-summary`, which the caller reports as
    a warning, and a keyword that the page itself never mentions (in its text, not in the header and not in the section of sources) is
    `keyword-not-in-page`, also a warning: the index may only say what the page says. Pure, so that it is tested without a repository.
    """
    findings = []
    if not data.get("summary"):
        findings.append(("missing-summary", "no `summary:` in the front matter, so INDEX.md shows the first paragraph (one line of at most 160 characters that says which question the page answers)"))
    for key, limit in INDEX_FIELD_LIMITS.items():
        if key not in data or data[key] is None:
            continue
        value = data[key]
        m = re.search(rf"^{key}:[ \t]*(.*?)[ \t]*$", raw, re.M)
        if not isinstance(value, str) or not m or m.group(1) != value or "|" in value:
            findings.append(("frontmatter-not-plain", f"`{key}:` must be one plain line of text (no quotes, no folded block, no ` #` comment, no `|`)"))
        elif len(value) > limit:
            findings.append((f"{key}-too-long", f"`{key}:` has {len(value)} characters, the limit is {limit}"))
    keywords = data.get("keywords")
    if isinstance(keywords, str) and content:
        text = body_without_sources(content).lower()
        for word in (w.strip() for w in keywords.split(",")):
            if word and word.lower() not in text:
                findings.append(("keyword-not-in-page", f"the keyword {word!r} does not occur in the page"))
    return findings


def sweep_index_fields(report: dict):
    """Every page listed in INDEX.md: a `summary:` (a warning when missing) of at most 160 characters, plain `summary:` and `keywords:`."""
    settings, _ = load_settings(HANDBOOK_ROOT)
    for path in iter_markdown_files(HANDBOOK_ROOT):
        if not under_folders(rel(path), settings["index_folders"]):
            continue
        content = path.read_text(errors="replace")
        data, err = parse_frontmatter(content)
        if err or data is None:
            continue  # sweep_yaml_frontmatter reports it
        raw, _ = split_frontmatter(content)
        for check, detail in index_field_findings(raw, data, content):
            add(report, "warning" if check in ("missing-summary", "keyword-not-in-page") else "blocking", check, f"{rel(path)}: {detail}")


def sweep_index_current(report: dict):
    """INDEX.md must be what scripts/make-index.sh prints for the pages as they are now."""
    if not (HANDBOOK_ROOT / "INDEX.md").is_file():
        add(report, "blocking", "index-missing", "INDEX.md does not exist: run scripts/make-index.sh and commit the result")
        return
    rc, out, err = run(["bash", str(MAKE_INDEX), "--check", "--root", str(HANDBOOK_ROOT)], timeout=60)
    if rc == 1:
        changed = sum(1 for ln in err.splitlines() if ln[:1] in "+-" and ln[:3] not in ("+++", "---"))
        add(report, "blocking", "index-out-of-date", f"INDEX.md differs from what scripts/make-index.sh prints ({changed} lines): run scripts/make-index.sh and commit INDEX.md")
    elif rc != 0:
        add(report, "blocking", "index-script-failed", f"scripts/make-index.sh --check exited {rc}: {err.strip()[:200]}")


# --- The size budget: a page over 60 KB, CLAUDE.md and INDEX.md over 40 KB, and the ratchet list of the pages that are over today ---

# The git revision whose list is the baseline of the ratchet: what is merged. A list that is new on a branch has none, and nothing
# is compared; once it is merged, a commit that raises a line or adds a page to it is reported against the merged list.
RATCHET_BASE_REF = "origin/main"


def read_size_budget(text: str):
    """(limits, bad_lines) of scripts/size-budget.txt: one `PATH BYTES` per line, `#` starts a comment. Pure."""
    limits, bad = {}, []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdigit() or parts[0] in limits:
            bad.append(number)
            continue
        limits[parts[0]] = int(parts[1])
    return limits, bad


def size_limit(path: str) -> int:
    return SPECIAL_BUDGET_BYTES.get(path, PAGE_BUDGET_BYTES)


def size_findings(sizes: dict, ratchet: dict) -> list:
    """(bucket, check, detail) for the sizes of the Markdown files (path to bytes) against the budget and the ratchet list. Pure.

    A file over its budget (60 KB for a page, 40 KB for CLAUDE.md and INDEX.md) that is not on the list is `size-over-budget`. A
    file on the list is held to the size on its line: more is `size-over-ratchet`. A line that has become unnecessary or loose is
    an `info` that says to remove or lower it, so that the list only shrinks.
    """
    findings = []
    for path in sorted(sizes):
        size, budget = sizes[path], size_limit(path)
        if path in ratchet:
            line = ratchet[path]
            if size > line:
                findings.append(("warning", "size-over-ratchet", f"{path} is {size} bytes, {size - line} over the {line} on its line of {SIZE_BUDGET_FILE}: it may not grow; split it or cut it"))
            elif size <= budget:
                findings.append(("info", "size-ratchet-obsolete", f"{path} is {size} bytes, within its budget of {budget}: remove its line from {SIZE_BUDGET_FILE}"))
            elif size < line - SIZE_BUDGET_SLACK_BYTES:
                findings.append(("info", "size-ratchet-slack", f"{path} is {size} bytes and its line says {line}: lower the line to {size}, so that it cannot grow back"))
        elif size > budget and path == "INDEX.md":
            findings.append(("warning", "size-over-budget", f"{path} is {size} bytes, {size - budget} over its budget of {budget}: it is generated, so shorten the summaries and keywords of the pages, or split it into INDEX.md and INDEX-records.md (decisions, retrospectives, releases) in scripts/make-index.sh"))
        elif size > budget:
            findings.append(("warning", "size-over-budget", f"{path} is {size} bytes, {size - budget} over its budget of {budget}: split it (a record per release under operations/releases/ is the pattern) or move what is read rarely out of it"))
    for path in sorted(set(ratchet) - set(sizes)):
        findings.append(("warning", "size-ratchet-file-gone", f"{SIZE_BUDGET_FILE} lists {path}, which does not exist: remove the line"))
    return findings


def ratchet_increases(base: dict, now: dict) -> list:
    """Details for every line of the list that is new or higher than in the baseline: the list only shrinks. Pure."""
    found = []
    for path in sorted(now):
        if path not in base:
            found.append(f"{path} is a new line ({now[path]} bytes)")
        elif now[path] > base[path]:
            found.append(f"{path} was {base[path]} bytes and its line now says {now[path]}")
    return found


def sweep_size_budget(report: dict):
    list_path = HANDBOOK_ROOT / SIZE_BUDGET_FILE
    ratchet = {}
    if list_path.is_file():
        ratchet, bad = read_size_budget(list_path.read_text(errors="replace"))
        for number in bad:
            add(report, "warning", "size-budget-bad-line", f"{SIZE_BUDGET_FILE}:{number} is not `PATH BYTES` or repeats a path")
    sizes = {rel(path): path.stat().st_size for path in iter_markdown_files(HANDBOOK_ROOT)}
    for bucket, check, detail in size_findings(sizes, ratchet):
        add(report, bucket, check, detail)
    rc, out, _ = run_in_sibling(["git", "-C", str(HANDBOOK_ROOT), "show", f"{RATCHET_BASE_REF}:{SIZE_BUDGET_FILE}"], timeout=15)
    if rc == 0:
        base, _ = read_size_budget(out)
        for detail in ratchet_increases(base, ratchet):
            add(report, "warning", "size-ratchet-raised", f"{detail} (against {RATCHET_BASE_REF}): the list only shrinks")


# --- The age of a verification: a `verified` page whose date is old, and a date that nothing can age ---

def age_findings(pages: dict, today: date, max_days: int = VERIFIED_MAX_AGE_DAYS, record_folders: tuple = RECORD_FOLDERS) -> list:
    """(bucket, check, detail) for the `last_verified` of the pages (path to (status, value)). Pure.

    A value that is not a YYYY-MM-DD date, or that lies after today, is reported for every page: nothing else reads it, and a page
    with such a value never ages. A `verified` page whose date is more than `max_days` before today is `verification-aged`, except a
    page of a record folder (`record_folders` of handbook.cfg, as prefixes with a slash), which does not become false with time.
    """
    findings = []
    for path in sorted(pages):
        status, value = pages[path]
        day = verified_date(value)
        if day is None:
            findings.append(("warning", "last-verified-unreadable", f"{path}: last_verified {value!r} is not a YYYY-MM-DD date, so the page never ages"))
        elif day > today:
            findings.append(("warning", "last-verified-in-the-future", f"{path}: last_verified {day} is after today ({today}), so the page does not age until then"))
        elif status == "verified" and (today - day).days > max_days and not path.startswith(record_folders):
            findings.append(("warning", "verification-aged", f"{path}: verified on {day}, {(today - day).days} days ago (limit {max_days}): run its verify_with and set last_verified, or set status to unverified"))
    return findings


def sweep_verification_age(report: dict, today: date | None = None):
    today = today or date.today()
    pages = {}
    for path in iter_markdown_files(HANDBOOK_ROOT):
        data, err = parse_frontmatter(path.read_text(errors="replace"))
        if err or not data or "last_verified" not in data:
            continue  # sweep_yaml_frontmatter reports it
        pages[rel(path)] = (data.get("status"), data["last_verified"])
    settings, _ = load_settings(HANDBOOK_ROOT)
    for bucket, check, detail in age_findings(pages, today, settings["verified_max_age_days"], folder_prefixes(settings["record_folders"])):
        add(report, bucket, check, detail)


# --- The settings of this handbook (handbook.cfg) ---

def sweep_settings(report: dict):
    _, problems = load_settings(HANDBOOK_ROOT)
    for problem in problems:
        add(report, "blocking", "settings-problem", f"{SETTINGS_FILE}: {problem}")


# --- Identifiers of another project or handbook: none may appear in this repository ---

FOREIGN_IDENTIFIERS_FILE = "scripts/foreign-identifiers.txt"
# The only file that may name them is the list itself.
FOREIGN_IDENTIFIERS_EXEMPT = (FOREIGN_IDENTIFIERS_FILE,)


def read_foreign_identifiers(text: str):
    """(patterns, bad_lines) of scripts/foreign-identifiers.txt. Pure.

    One regular expression per line, matched without regard to case. A blank line and a line that starts with `#` are skipped. A line
    that is not a regular expression, or that matches the empty string and so would match everything, is bad.
    """
    patterns, bad = [], []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            pattern = re.compile(line, re.IGNORECASE)
        except re.error:
            bad.append(number)
            continue
        if pattern.search(""):
            bad.append(number)
        else:
            patterns.append(pattern)
    return patterns, bad


def foreign_identifier_findings(patterns: list, files: dict) -> list:
    """(path, line number) of every line of `files` (path to text) that matches one of the `patterns`. Pure."""
    found = []
    for path in sorted(files):
        for number, line in enumerate(text_lines(files[path]), 1):
            if any(pattern.search(line) for pattern in patterns):
                found.append((path, number))
    return found


def sweep_foreign_identifiers(report: dict):
    """A handbook copies the conventions of another one, never its content: the list names what must not appear here."""
    list_path = HANDBOOK_ROOT / FOREIGN_IDENTIFIERS_FILE
    if not list_path.is_file():
        return
    patterns, bad = read_foreign_identifiers(list_path.read_text(errors="replace"))
    for number in bad:
        add(report, "blocking", "foreign-identifiers-bad-line", f"{FOREIGN_IDENTIFIERS_FILE}:{number} is not a regular expression, or matches the empty string")
    files = {rel(path): path.read_text(errors="replace") for path in iter_text_files(HANDBOOK_ROOT) if rel(path) not in FOREIGN_IDENTIFIERS_EXEMPT}
    for path, number in foreign_identifier_findings(patterns, files):
        add(report, "blocking", "foreign-identifier", f"{path}:{number}")


# --- The first run: the interview that says where the truth lives (FIRST-RUN.md, scripts/first_run.py) ---

FIRST_RUN_FILE = "FIRST-RUN.md"
SOURCES_OF_TRUTH_PAGE = "reference/sources-of-truth.md"


def first_run_findings(first_run_exists: bool, page_exists: bool) -> list:
    """(bucket, check, detail) for the state of the first run. Pure.

    While FIRST-RUN.md exists the interview is not finished. Once it is deleted, the page it produces must exist: a handbook
    that does not say where the truth of each kind of fact lives has no way to tell a verified page from a guess.
    """
    if first_run_exists:
        return [("warning", "first-run-pending", f"{FIRST_RUN_FILE} exists: the first-run interview is not finished (python3 scripts/first_run.py, or let the agent ask the questions); delete the file when {SOURCES_OF_TRUTH_PAGE} is written")]
    if not page_exists:
        return [("warning", "sources-of-truth-missing", f"{SOURCES_OF_TRUTH_PAGE} does not exist: it says where the truth of each kind of fact lives, and every `verify_with` and `Sources` entry depends on it")]
    return []


def sweep_first_run(report: dict):
    for bucket, check, detail in first_run_findings((HANDBOOK_ROOT / FIRST_RUN_FILE).is_file(), (HANDBOOK_ROOT / SOURCES_OF_TRUTH_PAGE).is_file()):
        add(report, bucket, check, detail)


RECORD_STYLE_SWEEPS = ("sweep_em_dash", "sweep_non_english_text", "sweep_quoted_message")


def selected_sweeps(settings: dict) -> list:
    """The sweeps to run, in order. `record_style = off` in handbook.cfg leaves out the three that check how records are written."""
    sweeps = [
        sweep_settings, sweep_secrets, sweep_secret_rule, sweep_em_dash, sweep_non_english_text, sweep_quoted_message, sweep_entropy, sweep_mermaid,
        sweep_foreign_identifiers, sweep_yaml_frontmatter, sweep_sources_section, sweep_link_integrity, sweep_sources_path_exists,
        sweep_index_fields, sweep_index_current, sweep_size_budget, sweep_verification_age, sweep_first_run,
    ]
    if settings["record_style"] == "off":
        sweeps = [sweep for sweep in sweeps if sweep.__name__ not in RECORD_STYLE_SWEEPS]
    return sweeps


def main():
    report = {"blocking": [], "warning": [], "info": []}

    settings, _ = load_settings(HANDBOOK_ROOT)
    for sweep in selected_sweeps(settings):
        try:
            sweep(report)
        except Exception as e:  # noqa: BLE001
            log(f"  CRASHED in {sweep.__name__}: {e}")
            add(report, "blocking", "sweep-crashed", f"{sweep.__name__}: {e}")

    total = sum(len(report[k]) for k in ("blocking", "warning", "info"))
    print(f"Tier 0: {len(report['blocking'])} blocking, {len(report['warning'])} warning, "
          f"{len(report['info'])} info ({total} total)")
    for bucket, label in (("blocking", "BLOCKING"), ("warning", "warning"), ("info", "info")):
        for f in report[bucket]:
            print(f"  {label:9s} [{f['check']}] {f['detail']}")

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    sys.exit(1 if report["blocking"] else 0)


if __name__ == "__main__":
    main()
