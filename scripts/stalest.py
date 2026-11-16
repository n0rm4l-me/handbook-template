#!/usr/bin/env python3
"""List the pages that were verified longest ago, for the Tier 2 pass (process/verification.md).

Usage:
    python3 scripts/stalest.py [-n COUNT] [--root DIR] [--today YYYY-MM-DD] [FOLDER ...]

FOLDER limits the list to the pages under it (`operations`, `operations/releases`); without one, the pages of the folders of INDEX.md
(`index_folders` in handbook.cfg, by default architecture, operations, process and reference). COUNT is how many pages to print
(default 5, the Tier 2 budget of a session; 0 prints all of them).

The order: by `last_verified`, oldest first, a date that cannot be read before every other, and for the same date `unverified`
before every other status. A page marked `stale` is not moved up (it sorts by its date like a `verified` one): its drift is known,
and a page kept as history of a removed component would sit on the list for good. The dated records (`record_folders` in handbook.cfg)
are left out, because a record does not become false with time; a parent folder such as `operations` does not bring them back, name
their own folder (`operations/releases`) to list them. Each page is printed with its status, the age of its date and its
`verify_with`, so that a page that has a command is run first. Blast radius, which Tier 2 puts first, is not known to the script:
name the folder. Reads only; exit code 2 when a FOLDER holds no page, or when there is no page at all.
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import RECORD_FOLDERS, folder_prefixes, iter_markdown_files, load_settings, parse_frontmatter, verified_date  # noqa: E402


def rank(pages: list) -> list:
    """The pages (dicts with path, status, last_verified, verify_with) in the order described above. Pure."""
    def key(page):
        day = verified_date(page["last_verified"])
        return (day or date.min, page["status"] != "unverified", page["path"])
    return sorted(pages, key=key)


def read_pages(root: Path, folders: tuple, record_folders: tuple = RECORD_FOLDERS) -> list:
    """The pages under the folders. A page of a record folder (prefixes with a slash) is read only when a folder named is itself
    a record folder."""
    pages = []
    for path in iter_markdown_files(root):
        rel = path.relative_to(root).as_posix()
        under = [folder for folder in folders if rel.startswith(folder + "/")]
        if not under or (rel.startswith(record_folders) and not any((folder + "/").startswith(record_folders) for folder in under)):
            continue
        data, err = parse_frontmatter(path.read_text(errors="replace"))
        if err or not data:
            continue  # Tier 0 reports a broken or missing header
        pages.append({"path": rel, "status": data.get("status"), "last_verified": data.get("last_verified"), "verify_with": data.get("verify_with")})
    return pages


def count(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="List the pages verified longest ago.")
    parser.add_argument("folders", nargs="*", help="limit the list to the pages under these folders")
    parser.add_argument("-n", type=count, default=5, help="how many pages to print, 0 for all (default 5)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent, help="the handbook to read")
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="the date to count the age from (default today)")
    args = parser.parse_args(argv)
    today = args.today or date.today()
    settings, problems = load_settings(args.root)
    for problem in problems:
        print(f"handbook.cfg: {problem} (the default is used; scripts/tier0.py reports it)", file=sys.stderr)
    folders = tuple(os.path.normpath(folder) for folder in args.folders) or settings["index_folders"]
    pages = read_pages(args.root, folders, folder_prefixes(settings["record_folders"]))
    named = folders if args.folders else ()
    empty = [folder for folder in named if not any(page["path"].startswith(folder + "/") for page in pages)]
    if empty or not pages:
        for folder in empty or [str(args.root)]:
            print(f"no page under {folder}", file=sys.stderr)
        return 2
    ranked = rank(pages)
    for page in ranked[: args.n or None]:
        day = verified_date(page["last_verified"])
        age = f"{(today - day).days}d" if day else "?"
        shown = str(day) if day else ("?" if page["last_verified"] is None else " ".join(str(page["last_verified"]).split()))
        print(f"{shown:<10}  {age:>5}  {page['status']!s:<10}  {page['path']}")
        print(f"    verify_with: {' '.join(str(page['verify_with']).split())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
