#!/usr/bin/env bash
# INDEX.md, the entry point of the handbook: one row per page of the folders of `index_folders` in handbook.cfg (by default
# architecture/, operations/, process/ and reference/, with the folders inside them) with its path, title, status, size, the
# question it answers and its keywords. An agent greps it
# (grep -i WORD INDEX.md) before it opens a page. The file is generated: the pages hold the text, this script collects it,
# and Tier 0 (scripts/tier0.py) fails when INDEX.md differs from what this script prints.
#
# Usage: scripts/make-index.sh [--write | --check | --stdout] [--root DIR]
#   --write   (default) write INDEX.md in the root, only when its content changes
#   --check   write nothing; exit 0 when INDEX.md is what the pages say, exit 1 and show a diff when it is out of date
#   --stdout  print the index
#   --root    the handbook to read (default: the folder above scripts/); the tests use a throwaway tree
#
# Where each field comes from, all of it from the page itself:
#   title     the first "# " heading outside a fenced block, cut at a word at 64 bytes
#   status    `status:` of the front matter
#   KB        the size of the file in bytes over 1000, rounded to a whole number, at least 1 (scripts/page-outline.sh gives the
#             exact figure and the sections of a page)
#   answers   `summary:` of the front matter (one line, at most 160 characters, no ": " inside); a page without it gets its
#             first paragraph cut at a word at 160 bytes, and Tier 0 warns for it
#   keywords  `keywords:` of the front matter (a comma-separated line); empty when the page has none
# The output depends on the pages only: no date, no host, the rows sorted by folder and then by name in the C locale. A "|"
# inside a title or a field is written as "/" so that the row stays a row. Works with bash 3.2 (macOS) and with Linux: the
# work is done by one awk program, in the C locale so that every awk counts bytes.
set -euo pipefail

usage() {
  echo "usage: $0 [--write | --check | --stdout] [--root DIR]" >&2
}

mode=write
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

while [ "$#" -gt 0 ]; do
  case $1 in
    --write) mode=write ;;
    --check) mode=check ;;
    --stdout) mode=stdout ;;
    --root)
      if [ "$#" -lt 2 ]; then
        usage
        exit 2
      fi
      root=$2
      shift
      ;;
    *)
      echo "$0: unknown argument '$1'" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

if [ ! -d "$root" ]; then
  echo "$0: $root is not a folder" >&2
  exit 1
fi
cd "$root"

# The folders that hold pages: `index_folders` of handbook.cfg (a comma-separated list, folders relative to the root), or the four
# defaults when the file or the key is missing or empty. It reads the key the way scripts/common.py does (the first "=" or ":" of
# the line, [handbook] only, a line that starts with # or ; is a comment); scripts/tier0.py checks the value and reports a mistake.
# The rows come out sorted by the path of the folder, not in the order of the list. A folder that does not exist is skipped.
cfg_index_folders() {
  if [ -f handbook.cfg ]; then
    LC_ALL=C awk '
      { sub(/\r$/, "") }
      /^[ \t]*\[/ { in_section = ($0 ~ /^[ \t]*\[handbook\][ \t]*$/); next }
      !in_section || /^[ \t]*[#;]/ { next }
      {
        i = match($0, /[=:]/)
        if (i == 0) next
        k = substr($0, 1, i - 1); gsub(/[ \t]/, "", k)
        if (tolower(k) == "index_folders") {
          v = substr($0, i + 1); gsub(/\r/, "", v); sub(/^[ \t]+/, "", v); sub(/[ \t]+$/, "", v)
          print v
          exit
        }
      }' handbook.cfg
  fi
}

wanted=$(cfg_index_folders)
if [ -z "$wanted" ]; then
  wanted="architecture,operations,process,reference"
fi
folders=""
old_ifs=$IFS
IFS=,
set -f
for d in $wanted; do
  d=$(printf '%s' "$d" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
  d=${d%/}
  case $d in
    '' | /* | .* | */.* | *//* | */ | *[!A-Za-z0-9._/-]*)
      echo "$0: handbook.cfg: index_folders has a folder that is not allowed: '$d'" >&2
      exit 1
      ;;
  esac
  if [ -d "$d" ]; then
    folders="$folders $d"
  fi
done
set +f
IFS=$old_ifs

generate() {
  if [ -z "$folders" ]; then
    list="/dev/null"   # awk with no file would wait on standard input
  else
    # shellcheck disable=SC2086
    list=$(find $folders -type f -name '*.md' | LC_ALL=C awk '{ d = $0; sub(/\/[^\/]*$/, "", d); print d "\t" $0 }' | LC_ALL=C sort -u | cut -f 2-)
    if [ -z "$list" ]; then
      list="/dev/null"
    fi
    # The names are passed to awk as words: a name with a space would be read as two files.
    case $list in
      *" "* | *"	"*)
        echo "$0: a page has a space or a tab in its name; rename it:" >&2
        printf '%s\n' "$list" | grep -E "[ 	]" >&2 || true
        exit 1
        ;;
    esac
  fi
  # shellcheck disable=SC2086
  LC_ALL=C awk '
function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
function norm(s) { gsub(/\r/, "", s); gsub(/[ \t]+/, " ", s); return trim(s) }
function unquote(s,   n, f, l) {
  n = length(s)
  if (n >= 2) {
    f = substr(s, 1, 1); l = substr(s, n, 1)
    if ((f == "\"" || f == "\047") && f == l) s = substr(s, 2, n - 2)
  }
  return s
}
# Cut at a word so that no multi-byte character is split, and mark the cut.
function cut(s, max) {
  if (length(s) <= max) return s
  s = substr(s, 1, max - 3)
  if (s ~ / /) sub(/ [^ ]*$/, "", s)
  return s "..."
}
function cell(s) { gsub(/\|/, "/", s); return s }
function finish(   sm, k) {
  if (path == "") return
  sm = has_summary ? summary : cut(para, 160)
  k = int(bytes / 1000 + 0.5)
  if (k < 1) k = 1
  n++
  p_path[n] = path
  p_dir[n] = path; sub(/\/[^\/]*$/, "", p_dir[n])
  p_title[n] = cell(have_title ? cut(title, 64) : path)
  p_status[n] = cell(status == "" ? "n/a" : status)
  p_kb[n] = k
  p_sum[n] = cell(sm)
  p_kw[n] = cell(keywords)
}
function pages(k) { return k == 1 ? "1 page" : k " pages" }
function blurb(d) {
  if (d == "architecture") return "how does this work, and why"
  if (d == "architecture/decisions") return "ADRs: what was decided, the options and why"
  if (d == "architecture/services") return "how does this service work, one page per deployable component"
  if (d == "operations") return "how do I do this: runbooks and the state of a component"
  if (d == "operations/releases") return "what happened in a past release: records, not the current state"
  if (d == "architecture/retrospectives") return "retrospectives of past efforts"
  if (d == "process") return "how do I do this task of the handbook, read when the trigger in CLAUDE.md fires"
  if (d == "reference") return "what is the value of X: lookup pages"
  return ""
}
BEGIN { n = 0; path = "" }
FNR == 1 {
  finish()
  path = FILENAME; bytes = 0; in_fm = 0; fence = ""
  title = ""; have_title = 0; para = ""; para_done = 0
  status = ""; summary = ""; keywords = ""; has_summary = 0
}
{
  line = $0
  sub(/\r$/, "", line)
  bytes += length($0) + 1
  if (FNR == 1 && line == "---") { in_fm = 1; next }
  if (in_fm) {
    if (line == "---") { in_fm = 0; next }
    if (match(line, /^[A-Za-z_][A-Za-z0-9_]*:/)) {
      key = substr(line, 1, RLENGTH - 1)
      val = unquote(norm(substr(line, RLENGTH + 1)))
      if (key == "status") status = val
      else if (key == "summary" && val != "") { summary = val; has_summary = 1 }
      else if (key == "keywords") keywords = val
    }
    next
  }
  body = line
  sub(/^ ? ? ?/, "", body)
  if (fence != "") {
    c = substr(fence, 1, 1); k = 0
    while (substr(body, k + 1, 1) == c) k++
    if (k >= length(fence) && substr(body, k + 1) ~ /^[ \t]*$/) fence = ""
    next
  }
  if (substr(body, 1, 3) == "```" || substr(body, 1, 3) == "~~~") {
    c = substr(body, 1, 1); k = 0
    while (substr(body, k + 1, 1) == c) k++
    fence = substr(body, 1, k)
    if (have_title && para != "") para_done = 1
    next
  }
  if (!have_title) {
    if (line ~ /^# +[^ \t]/) {
      t = line; sub(/^# +/, "", t); sub(/[ \t]+#*[ \t]*$/, "", t)
      title = norm(t); have_title = 1
    }
    next
  }
  if (para_done) next
  if (line ~ /^[[:space:]]*$/) { if (para != "") para_done = 1; next }
  if (line ~ /^[^[:space:]#|>+<!-]/ && line !~ /^\*[[:space:]]/ && line !~ /^[0-9]+[.)][[:space:]]/ && line !~ /^(\*\*\*+|___+)[[:space:]]*$/) {
    t = line; gsub(/\*\*/, "", t); t = norm(t)
    para = (para == "" ? t : para " " t)
  } else if (para != "") para_done = 1
}
END {
  finish()
  printf "# INDEX\n\n"
  printf "The entry point of the handbook, %s. Generated by `scripts/make-index.sh` from the front matter of the pages: do not edit it, change the `summary:` or `keywords:` of the page and run the script (Tier 0 fails when this file is out of date).\n\n", pages(n)
  printf "Start here: `grep -i WORD INDEX.md` for the service, the symptom, the tool or the name you look for, then open the page; a page over 40 KB is read by section (`scripts/page-outline.sh PAGE`, see CLAUDE.md). Columns: the page, its title, its `status`, its size in KB, the question it answers (`summary:` of the page) and its `keywords:`. Not listed: `CLAUDE.md` (the rules, loaded in every session) and `README.md` (what only it says).\n"
  last = "\001"
  for (i = 1; i <= n; i++) {
    if (p_dir[i] != last) {
      last = p_dir[i]
      cnt = 0
      for (j = i; j <= n && p_dir[j] == last; j++) cnt++
      b = blurb(last)
      printf "\n## %s/ (%s%s)\n\n", last, pages(cnt), (b == "" ? "" : ", " b)
      printf "| Page | Title | Status | KB | Answers | Keywords |\n|---|---|---|---|---|---|\n"
    }
    printf "| %s | %s | %s | %d | %s | %s |\n", p_path[i], p_title[i], p_status[i], p_kb[i], p_sum[i], p_kw[i]
  }
}
' $list
}

case $mode in
  stdout)
    generate
    ;;
  write)
    tmp=$(mktemp "${TMPDIR:-/tmp}/make-index.XXXXXX")
    trap 'rm -f "$tmp"' EXIT
    generate > "$tmp"
    if [ -f INDEX.md ] && cmp -s "$tmp" INDEX.md; then
      echo "INDEX.md is current"
    else
      cp "$tmp" INDEX.md
      echo "INDEX.md written ($(grep -c '^| [a-z]' INDEX.md) rows)"
    fi
    ;;
  check)
    tmp=$(mktemp "${TMPDIR:-/tmp}/make-index.XXXXXX")
    trap 'rm -f "$tmp"' EXIT
    generate > "$tmp"
    if [ ! -f INDEX.md ]; then
      echo "INDEX.md does not exist: run scripts/make-index.sh" >&2
      exit 1
    fi
    if cmp -s "$tmp" INDEX.md; then
      echo "INDEX.md is current"
    else
      echo "INDEX.md is out of date: run scripts/make-index.sh and commit the result" >&2
      diff -u INDEX.md "$tmp" | head -n 30 >&2 || true
      exit 1
    fi
    ;;
esac
