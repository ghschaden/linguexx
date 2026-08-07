#!/bin/bash
# Record what the example documents currently RENDER to.
#
#   tests/nominal-capture.sh [baseline-dir]
#
# Companion to nominal-verify.sh, which rebuilds and compares.  Together
# they answer one question that the test suite cannot: did a change that
# was supposed to alter nothing actually alter nothing?
#
# The suite asserts on the properties someone thought to write an
# assertion for.  A refactor claims something much stronger -- that every
# property is unchanged, including the ones nobody has named -- and the
# cheap way to check that claim is to compare the rendered pages
# themselves.  This pair was written for the front-end API work, where
# every commit was meant to be purely nominal, and it caught nothing
# precisely because it was run after each one; that is the point of it.
#
# What is recorded, per example document:
#   <name>.struct   pdfinfo -struct-text, i.e. the tagged structure tree
#   <name>-N.png    every page at 150dpi
#   pixels.sha256   their checksums, which is what is actually compared
# plus a veraPDF report on ua-demo, the full accessible document.
#
# PDF bytes themselves are NOT comparable: they carry a timestamp and a
# file ID, so two builds of identical source differ.  Rendered pixels and
# the structure tree are the two views that do not.
set -e

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${1:-$REPO/tests/.nominal-baseline}
DOCS="ua-demo accessible-demo altg-demo"

# veraPDF is a hard requirement of the suite; accept it from PATH, and
# fall back to the location the installer uses, rather than failing with
# "verapdf: command not found" three minutes into a build.
VERAPDF=$(command -v verapdf || true)
[ -z "$VERAPDF" ] && [ -x "$HOME/verapdf/verapdf" ] && VERAPDF=$HOME/verapdf/verapdf
if [ -z "$VERAPDF" ]; then
  echo "veraPDF not found on PATH or in ~/verapdf." >&2
  echo "It is the only authoritative oracle for PDF/UA; install it." >&2
  exit 2
fi

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
mkdir -p "$OUT"
rm -f "$OUT"/*.png "$OUT"/*.struct "$OUT"/pixels.sha256 2>/dev/null || true

# Build out of tree, with TEXINPUTS pointing back: the examples must be
# built against the working copy of the .sty, not an installed linguexx,
# and the repo must not collect .aux files as a side effect.
export TEXINPUTS="$REPO:"
cd "$BUILD"
for f in $DOCS; do
  cp "$REPO/examples/$f.tex" .
  # lualatex converges in two passes; the third is insurance, and cheap
  # next to diagnosing an unconverged file that fails veraPDF exactly
  # like a real regression.
  for i in 1 2 3; do
    if ! lualatex -interaction=nonstopmode -halt-on-error "$f.tex" >"$f.$i.log" 2>&1; then
      echo "BUILD FAILED: $f, pass $i" >&2
      grep -E "^!" "$f.$i.log" | head -5 >&2
      exit 1
    fi
  done
  pdfinfo -struct-text "$f.pdf" > "$OUT/$f.struct"
  pdftoppm -r 150 -png "$f.pdf" "$OUT/$f"
done

cd "$OUT"
sha256sum *.png > pixels.sha256
"$VERAPDF" --format text "$BUILD/ua-demo.pdf" > "$OUT/ua-demo.verapdf.txt" 2>&1 || true
sed -i "s|$BUILD/||" "$OUT/ua-demo.verapdf.txt" 2>/dev/null || true

echo "captured $(ls *.png | wc -l) page(s) from $(echo $DOCS | wc -w) document(s) to $OUT"
grep -E "^(PASS|FAIL)" "$OUT/ua-demo.verapdf.txt" | sed 's/^/  verapdf /'
