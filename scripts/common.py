#!/usr/bin/env python3
"""Shared helpers and patterns for scripts/tier0.py.

Every pattern that names something this repo must not contain is assembled at runtime from
parts, never typed literally, so this file cannot match its own sweep. CLAUDE.md gives the
reason: a check that names its own pattern reports itself on every run, and a sweep with one
permanent expected hit trains you to skim its output.
"""
import configparser
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:  # a clean message beats a traceback in a pre-commit hook
    sys.exit("PyYAML is required: pip install -r requirements.txt (or: pip install pyyaml)")


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


def split_frontmatter(content: str):
    """Return (raw_frontmatter_text, body) or (None, content) if absent.

    The header runs from the line `---` that opens the file to the next line that is `---` alone. A `---` inside a value is not a
    closing line (the old split at the first `---` anywhere cut the header there, silently).
    """
    if not re.match(r"---[ \t]*\n", content):
        return None, content
    m = re.search(r"^---[ \t]*$", content[3:], re.M)
    if not m:
        return None, content
    return content[3:3 + m.start()], content[3 + m.end():]


# The sources of a page are a final section of the page, "## Sources", with one list item per entry (process/frontmatter.md); the
# header holds only their number, `sources_count`. The old form, a `sources:` list in the header, is forbidden (Tier 0).
SOURCES_HEADING = "## Sources"
HEADING_LINE = re.compile(r"^#{1,6}[ \t]+\S")
FENCE_LINE = re.compile(r"(`{3,}|~{3,})")


def body_without_sources(content: str) -> str:
    """The text of a page after its header and before its '## Sources' section, for the checks that ask what the page itself says."""
    raw, body = split_frontmatter(content)
    if raw is None:
        return content
    out = []
    for line in body.split("\n"):
        if line.rstrip() == SOURCES_HEADING:
            break
        out.append(line)
    return "\n".join(out)


def source_entries(content: str):
    """(entries, problems) of one page. `entries` are the texts of the sources, in order, without the list marker. `problems` is a
    list of (check, detail) for a page whose section is wrong: no section (`missing-sources-section`), a heading after it
    (`sources-section-not-last`), a line in it that is not one list item (`sources-entry-malformed`).

    Lines inside a fenced block are not headings. An entry is one line: a continuation line is malformed, as the old rule said
    ("never wrap a list item").
    """
    raw, body = split_frontmatter(content)
    if raw is None:
        return [], []
    lines = body.split("\n")
    fence = None  # (character, length) of the open fence; a closing fence is the same character, at least as long, with nothing after it
    heading_at = None
    problems = []
    entries = []
    for number, line in enumerate(lines):
        marker = FENCE_LINE.match(line.lstrip())
        if fence is None:
            if marker:
                fence = (marker.group(1)[0], len(marker.group(1)))
                continue
        else:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= fence[1] and not line.lstrip()[len(marker.group(1)):].strip():
                fence = None
            continue
        if heading_at is None:
            if line.rstrip() == SOURCES_HEADING:
                heading_at = number
            continue
        if HEADING_LINE.match(line):
            problems.append(("sources-section-not-last", f"the heading {line.strip()[:60]!r} follows the section {SOURCES_HEADING!r}, which must be the last"))
            break
        if not line.strip():
            continue
        if line.startswith("- ") and line[2:].strip():
            entries.append(line[2:])
        else:
            problems.append(("sources-entry-malformed", f"the line {line.strip()[:60]!r} in {SOURCES_HEADING!r} is not a list item of its own"))
    if heading_at is None:
        problems.append(("missing-sources-section", f"no {SOURCES_HEADING!r} section at the end of the page"))
    return entries, problems


def parse_frontmatter(content: str):
    """Return (dict_or_None, error_or_None).

    error is None only when a frontmatter block exists and parses to a mapping. A file with
    no frontmatter at all returns (None, None); whether that is allowed depends on the file
    (README.md, CLAUDE.md and the other root files of a project carry none), which is the caller's call.
    """
    raw, _ = split_frontmatter(content)
    if raw is None:
        return None, None
    try:
        data = yaml.safe_load(raw)
    except (yaml.YAMLError, ValueError) as e:  # ValueError: an unquoted date that does not exist, such as 2026-13-45
        return None, (str(e).splitlines() or [type(e).__name__])[0]
    if not isinstance(data, dict):
        return None, "frontmatter did not parse to a mapping"
    return data, None


def iter_markdown_files(root: Path) -> Iterable[Path]:
    """The Markdown files of the handbook. A folder whose name starts with a dot (.git, .github, .venv) holds tooling, not pages."""
    for path in sorted(root.glob("**/*.md")):
        if ".git" in path.parts:
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts[:-1]):
            continue
        yield path


def iter_text_files(root: Path) -> Iterable[Path]:
    """Every readable text file in the tree, for sweeps that are not Markdown-only."""
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".gif", ".ico", ".pdf", ".zip"}:
            continue
        yield path


# --- Patterns encoding CLAUDE.md's Tier 0 sweeps ---

# A bare true or false after the colon is a switch and not a credential (the same refinement as in secret_sweep.py, CLAUDE.md, "Never write a secret value").
SECRET_PATTERN = re.compile(
    r"(api[_-]?key|password|passwd|secret|token|bearer|private[_-]?key|BEGIN [A-Z ]*PRIVATE KEY)[^a-z]*[=:](?!\s*(?:true|false)\b)",
    re.IGNORECASE,
)
SECRET_ALLOW = re.compile(
    r"REDACTED|<[a-z-]+>|\$\{?[A-Z_]+\}?|CAPS|secretKeyRef|name:|-secret|_secret",
    re.IGNORECASE,
)
ENTROPY_PATTERN = re.compile(r"""["'=][0-9a-f]{32,}["']?""")
EM_DASH = "\u2014"  # escape, not the literal glyph, so this file cannot match a repo-wide em-dash grep

# Files that legitimately carry no frontmatter. Everything else must. The root files of a project are read by people and by the
# hosting site (README.md, CONTRIBUTING.md, SECURITY.md and so on), not found through the links of the handbook, so they are not orphans
# either. INDEX.md is generated by scripts/make-index.sh; FIRST-RUN.md and TEMPLATE.md are temporary, and are deleted when the first run
# is finished (TEMPLATE.md says so).
TEMPORARY_FILES = {"FIRST-RUN.md", "TEMPLATE.md"}
COMMUNITY_FILES = {"CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md"}
ROOT_PROJECT_FILES = {"README.md", "CLAUDE.md", "AGENTS.md", "INDEX.md"} | COMMUNITY_FILES
NOT_ORPHANS = {"README.md"} | COMMUNITY_FILES  # CLAUDE.md and INDEX.md are reached by a link, and are reported when nothing links to them
NO_FRONTMATTER_FILES = ROOT_PROJECT_FILES | TEMPORARY_FILES
REQUIRED_FRONTMATTER_KEYS = {"status", "last_verified", "verify_with", "sources_count"}

# The default folders whose pages are listed in INDEX.md (the key `index_folders` of handbook.cfg replaces them; scripts/make-index.sh
# reads the same key), the optional front matter keys the index reads, and the longest value each may have (process/frontmatter.md,
# "The required keys").
INDEX_FOLDERS = ("architecture", "operations", "process", "reference")
INDEX_FIELD_LIMITS = {"summary": 160, "keywords": 100}

# The size budget of a Markdown file in bytes (1 KB is 1000 bytes), checked by scripts/tier0.py as warnings. Above these a page is
# paid for by every call that holds it. A page that is over today is listed in scripts/size-budget.txt with its size, which is then
# its own limit: it may not grow, and the list only shrinks.
PAGE_BUDGET_BYTES = 60_000
SPECIAL_BUDGET_BYTES = {"CLAUDE.md": 40_000, "INDEX.md": 40_000}  # loaded in every call, and the entry point that is searched
SIZE_BUDGET_FILE = "scripts/size-budget.txt"
SIZE_BUDGET_SLACK_BYTES = 1_000  # a listed page this much under its line is told to lower the line

# A page marked `verified` claims that its evidence was seen on `last_verified`; the claim ages. Tier 0 warns when the date is older
# than this (process/verification.md, "The age of a verification").
VERIFIED_MAX_AGE_DAYS = 30
# The default folders of dated records of what happened (a release, a postmortem, a retrospective, the result of a measurement run; the
# key `record_folders` of handbook.cfg replaces them). A record does not become false with time, so no age check and no Tier 2 list
# counts it. Written with the trailing slash, as a prefix of a path.
RECORD_FOLDERS = ("operations/releases/", "architecture/retrospectives/")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def verified_date(value):
    """A `last_verified` value as a date, or None when it is not a YYYY-MM-DD calendar date.

    YAML reads an unquoted 2026-10-30 as a date and a quoted one as text; a datetime is cut to its date.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and ISO_DATE.fullmatch(value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


# The settings of this handbook: handbook.cfg in the root, one section [handbook]. A file that is missing means the defaults.
SETTINGS_FILE = "handbook.cfg"
SETTINGS_SECTION = "handbook"
RECORD_STYLES = ("strict", "off")  # strict: the English-only, no-em-dash and no-quoted-conversation checks run; off: none of them


# One part of a folder path: starts with a letter, a digit or an underscore (so never "." or ".." or a hidden folder), no space (scripts/
# make-index.sh passes the names to awk as words).
FOLDER_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")


def parse_folders(key: str, value: str, allow_empty: bool):
    """(folders, problem) for a comma-separated list of folders relative to the root, as `index_folders` and `record_folders` hold it.

    A trailing slash is dropped. A problem (and no folders) is: an empty item, a part that is not a plain name, a folder listed twice, a
    folder inside another one of the list (the index finds nested folders by itself, so the pair would list its pages twice), and, when
    `allow_empty` is false, no folder at all. Pure.
    """
    items = [item.strip().rstrip("/") for item in value.split(",")] if value.strip() else []
    for item in items:
        if not item or not all(FOLDER_PART.fullmatch(part) for part in item.split("/")):
            return None, (f"{key} has {item!r}, expected folders relative to the root, separated by commas "
                          "(letters, digits, '.', '_' and '-', no spaces, no part that starts with a dot)")
    for item in items:
        if items.count(item) > 1:
            return None, f"{key} lists {item!r} twice"
        for other in items:
            if item.startswith(other + "/"):
                return None, f"{key} lists {item!r}, which is inside {other!r} that is listed too"
    if not items and not allow_empty:
        return None, f"{key} needs at least one folder"
    return tuple(items), None


def folder_prefixes(folders) -> tuple:
    """Folders as prefixes of a path ('operations/releases' to 'operations/releases/'), for str.startswith."""
    return tuple(folder + "/" for folder in folders)


def under_folders(relpath: str, folders) -> bool:
    """True when the path (relative, with '/') is inside one of the folders."""
    return relpath.startswith(folder_prefixes(folders))


def load_settings(root: Path):
    """(settings, problems) of handbook.cfg under `root`: the keys with their defaults, and one text per mistake.

    Known keys: `record_style` (strict or off), `verified_max_age_days` (a whole number above 0), `index_folders` (the folders whose
    pages INDEX.md lists, at least one) and `record_folders` (the folders of dated records, may be empty); the last two are tuples
    of folders without a trailing slash. An unknown key or section, a value that is not allowed and a file that does not parse are
    problems, because a setting that is silently ignored is a trap.
    """
    settings = {
        "record_style": "strict",
        "verified_max_age_days": VERIFIED_MAX_AGE_DAYS,
        "index_folders": INDEX_FOLDERS,
        "record_folders": tuple(folder.rstrip("/") for folder in RECORD_FOLDERS),
    }
    path = root / SETTINGS_FILE
    if not path.is_file():
        return settings, []
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(path.read_text(encoding="utf-8"))
    except (configparser.Error, UnicodeDecodeError) as e:
        return settings, [(str(e).splitlines() or [type(e).__name__])[0]]
    problems = [f"unknown section [{name}]" for name in parser.sections() if name != SETTINGS_SECTION]
    if not parser.has_section(SETTINGS_SECTION):
        return settings, problems
    for key, value in parser.items(SETTINGS_SECTION):
        if key == "record_style" and value in RECORD_STYLES:
            settings[key] = value
        elif key == "record_style":
            problems.append(f"record_style is {value!r}, expected one of {', '.join(RECORD_STYLES)}")
        elif key == "verified_max_age_days" and value.isdigit() and int(value) > 0:
            settings[key] = int(value)
        elif key == "verified_max_age_days":
            problems.append(f"verified_max_age_days is {value!r}, expected a whole number above 0")
        elif key in ("index_folders", "record_folders"):
            folders, problem = parse_folders(key, value, allow_empty=key == "record_folders")
            if problem:
                problems.append(problem)
            else:
                settings[key] = folders
        else:
            problems.append(f"unknown key {key}")
    return settings, problems


# --- The language rule (CLAUDE.md, "Records are formulations, not conversations") ---
#
# Everything below is built from code points and names, never from the characters it detects, so this file
# passes its own sweep.

# Code points below this value are Basic Latin, Latin-1 Supplement and Latin Extended A and B: every letter there is
# a Latin letter (or a Latin-derived sign such as the micro sign), so a line made of them needs no further look.
LATIN_BLOCKS_END = 0x250
# Invisible controls that change how text reads: the Arabic letter mark, which belongs to Arabic text, and the embeddings,
# overrides and isolates of bidirectional text. None has a use in an English record. The left-to-right and right-to-left
# marks (U+200E, U+200F) and the zero-width characters are harmless and pass.
DIRECTION_CONTROLS = {0x061C, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}
# Letters by category that are the symbols of units: Greek mu, the ohm, kelvin and angstrom signs.
UNIT_SIGNS = {0x03BC, 0x2126, 0x212A, 0x212B}


def text_lines(text: str) -> list:
    """Lines as an editor numbers them: split at LF, CRLF and CR only (str.splitlines also splits at U+2028 and U+0085)."""
    return re.split(r"\r\n|\r|\n", text)


def foreign_scripts(line: str) -> list:
    """Names of the scripts of the letters in `line` that are outside the Latin alphabet, sorted; empty when there is none.

    Symbols, arrows, box drawing, emoji, digits, punctuation, accents on Latin letters, the signs of units, the modifier
    letters of Latin and the zero-width characters are not letters of another alphabet and never count. Fullwidth and styled
    Latin letters count as Latin. Direction controls (DIRECTION_CONTROLS) are reported as BIDI.
    """
    found = set()
    for ch in line:
        code = ord(ch)
        if code < LATIN_BLOCKS_END or code in UNIT_SIGNS:
            continue
        if code in DIRECTION_CONTROLS:
            found.add("BIDI")
            continue
        name = unicodedata.name(ch, "")
        if not ch.isalpha() or "LATIN" in name or name.startswith("MATHEMATICAL"):
            continue
        if name.startswith("MODIFIER LETTER") and "CYRILLIC" not in name and "GREEK" not in name:
            continue
        found.add(name.split()[0] if name else "UNNAMED")
    return sorted(found)


QUOTE_MARK = "[\"\u201c\u201d\u201e\u00ab\u00bb]"
SPEECH_VERB = r"(?:said|says|wrote|asked|answered|replied|told|quoted)"
# Who can say something: a role or a pronoun, not "the page" or "the log", which quote text legitimately.
# The plural "users" is a separate pattern, because "the Users page says" is a page of the portal and not a person.
SPEAKER = r"(?:user|owners?|sre|developers?|managers?|approvers?|administrators?|reviewers?|authors?|colleagues?|persons?|people|team|he|she|they)"
# Phrases that introduce a quotation of a person. A warning and not a blocker: code quotes, error messages, a title and
# the name of a rule use quotation marks legitimately.
QUOTED_MESSAGE_PATTERNS = (
    ("a person and a speech verb followed by a quotation",
     re.compile(r"\b" + SPEAKER + r"\b[^.\"\u201c\u201d]{0,30}?\b" + SPEECH_VERB + r"\b[^\"\u201c\u201d\n]{0,80}" + QUOTE_MARK, re.IGNORECASE)),
    ("users and a speech verb followed by a quotation",
     re.compile(r"\busers\s+(?:also\s+|then\s+)?" + SPEECH_VERB + r"\b[^\"\u201c\u201d\n]{0,80}" + QUOTE_MARK, re.IGNORECASE)),
    ("'wrote' or 'replied' followed by a quotation", re.compile(r"\b(?:wrote|replied)\b[:,]?\s*(?:that\s+)?" + QUOTE_MARK, re.IGNORECASE)),
    ("'in the words of' a person",
     re.compile(r"\bin (?:(?:his|her|their|(?:the )?(?:user|owner|sre)(?:'s|\u2019s))(?: own)? words?|the words of (?:the )?(?:user|owner|sre|developers?))\b", re.IGNORECASE)),
    ("quoted words, exact words, word for word", re.compile(r"\b(?:quoted words|exact words|word for word)\b", re.IGNORECASE)),
    ("verbatim", re.compile(r"\bverbatim\b", re.IGNORECASE)),
    ("as relayed, or relayed by", re.compile(r"\b(?:as relayed|relayed by)\b", re.IGNORECASE)),
    ("translated from or by", re.compile(r"\btranslated (?:from|by)\b", re.IGNORECASE)),
)
