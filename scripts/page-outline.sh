#!/usr/bin/env bash
# The outline of a page: its headings with the line each starts on, the number of lines and the size in KB of each
# section, and the size of the page. A page over 40 KB is never read whole (CLAUDE.md): take this outline first, then
# read the section you need with Read (offset = the LINE column, limit = the LINES column).
#
# Usage: scripts/page-outline.sh PAGE [MIN_KB]
#   PAGE    a Markdown file
#   MIN_KB  optional; leave out the sections smaller than this (their count and size are still shown; default 0)
#
# A section runs from its heading to the line before the next heading of any level, so a heading with sub-headings shows
# only its own text; the sub-sections have their own rows. The front matter is the first row. A line that starts like a
# heading inside a fenced code block, or inside the front matter, is not a heading. KB is 1000 bytes. A page without
# headings is said to have none. Works with bash 3.2 (macOS) and with Linux: the work is done by one awk program, in the
# C locale so that every awk counts bytes.
set -euo pipefail

usage() {
  echo "usage: $0 PAGE [MIN_KB]" >&2
  echo "  the headings of PAGE with line numbers and the size of each section in KB; MIN_KB hides smaller sections" >&2
}

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  usage
  exit 2
fi

page=$1
min_kb=${2:-0}

case $min_kb in
  '' | *[!0-9.]* | *.*.* | .)
    echo "$0: MIN_KB must be a non-negative number, got '$min_kb'" >&2
    usage
    exit 2
    ;;
esac

if [ -d "$page" ]; then
  echo "$0: $page is a directory, not a page" >&2
  exit 1
fi
if [ ! -r "$page" ]; then
  echo "$0: cannot read $page" >&2
  exit 1
fi

LC_ALL=C awk -v min_kb="$min_kb" -v name="$page" '
function kb(n) { return sprintf("%.1f", n / 1000) }
function emit(    shown) {
  # Close the section that ends at the previous line.
  if (cur_line == 0) return
  shown = (cur_bytes / 1000 >= min_kb + 0)
  if (shown) {
    rows[nrows++] = sprintf("%6d %6d %8s  %s", cur_line, cur_end - cur_line + 1, kb(cur_bytes), cur_text)
  } else {
    hidden++
    hidden_bytes += cur_bytes
  }
}
function start(line_no, text) {
  emit()
  cur_line = line_no
  cur_text = text
  cur_bytes = 0
}
BEGIN { fence = ""; in_fm = 0; heads = 0; hidden = 0; hidden_bytes = 0; cur_line = 0; total = 0; nrows = 0 }
{
  n = length($0) + 1
  total += n
  line = $0
  sub(/\r$/, "", line)
  body = line
  sub(/^ ? ? ?/, "", body)          # up to three spaces of indentation are allowed before a fence

  if (NR == 1 && line == "---") {
    in_fm = 1
    start(1, "(front matter)")
  } else if (in_fm) {
    if (line == "---") in_fm = 0
  } else if (fence != "") {
    # Inside a fenced block only its closing fence matters.
    c = substr(fence, 1, 1)
    k = 0
    while (substr(body, k + 1, 1) == c) k++
    if (k >= length(fence) && substr(body, k + 1) ~ /^[ \t]*$/) fence = ""
  } else if (substr(body, 1, 3) == "```" || substr(body, 1, 3) == "~~~") {
    c = substr(body, 1, 1)
    k = 0
    while (substr(body, k + 1, 1) == c) k++
    fence = substr(body, 1, k)
    if (cur_line == 0) start(NR, "(text before the first heading)")
  } else if (line ~ /^#+ +[^ \t]/) {
    hashes = line
    sub(/[^#].*$/, "", hashes)
    if (length(hashes) <= 6) {
      text = line
      sub(/^#+[ \t]+/, "", text)
      sub(/[ \t]+#*[ \t]*$/, "", text)
      if (length(text) > 90) text = substr(text, 1, 87) "..."
      pad = ""
      for (i = 2; i <= length(hashes); i++) pad = pad "  "
      heads++
      start(NR, pad hashes " " text)
    }
  } else if (cur_line == 0) {
    start(NR, "(text before the first heading)")
  }
  cur_bytes += n
  cur_end = NR
}
END {
  if (NR == 0) {
    printf "%s: empty file, 0 KB, 0 lines, no headings\n", name
    exit 0
  }
  emit()
  printf "%s: %s KB, %d lines, %d headings\n", name, kb(total), NR, heads
  if (nrows > 0) {
    printf "  LINE  LINES       KB  HEADING\n"
    for (i = 0; i < nrows; i++) print rows[i]
  }
  if (heads == 0) {
    printf "no headings: the page is one block, so read it with offset and limit in parts of about 300 lines\n"
  }
  if (hidden > 0) {
    printf "%d sections smaller than %s KB are not shown (%s KB together)\n", hidden, min_kb, kb(hidden_bytes)
  }
  if (total > 40000) {
    printf "over 40 KB: do not read the page whole; Read a section with offset = LINE and limit = LINES\n"
  }
}
' "$page"
