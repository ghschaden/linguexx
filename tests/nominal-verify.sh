#!/bin/bash
# Prove that a change altered nothing that reaches the page.
#
#   tests/nominal-capture.sh          # before the change
#   ...edit...
#   tests/nominal-verify.sh           # after: must report all OK
#
# Rebuilds the example documents and compares them against the baseline
# recorded by nominal-capture.sh: the tagged structure tree must be
# identical, every rendered page must be byte-identical, and veraPDF must
# still pass ua-demo.  See that script's header for why these three and
# not the PDF bytes.
#
# Use it for a refactor that is supposed to be invisible.  It is the
# wrong tool for a deliberate change -- there it will simply report the
# difference, and the baseline needs recapturing.
#
# A difference here is not automatically a defect, but it IS automatically
# something to explain: render both and look, rather than assuming the
# suite would have caught anything that mattered.
set -e

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BASE=${1:-$REPO/tests/.nominal-baseline}
DOCS="ua-demo accessible-demo altg-demo"

if [ ! -f "$BASE/pixels.sha256" ]; then
  echo "No baseline in $BASE -- run tests/nominal-capture.sh first." >&2
  exit 2
fi

NEW=$(mktemp -d)
trap 'rm -rf "$NEW"' EXIT
"$REPO/tests/nominal-capture.sh" "$NEW" > "$NEW/capture.log" 2>&1 || {
  echo "REBUILD FAILED"; tail -20 "$NEW/capture.log"; exit 1; }

rc=0
for f in $DOCS; do
  if diff -q "$BASE/$f.struct" "$NEW/$f.struct" >/dev/null; then
    echo "  struct OK    $f"
  else
    echo "  STRUCT DIFF  $f"
    diff "$BASE/$f.struct" "$NEW/$f.struct" | head -20
    rc=1
  fi
done

# Compare checksums by basename: the two runs live in different
# directories, so the paths sha256sum records differ by construction.
if diff <(awk '{print $1}' "$BASE/pixels.sha256") \
        <(awk '{print $1}' "$NEW/pixels.sha256") >/dev/null; then
  echo "  pixels OK    every page byte-identical"
else
  echo "  PIXEL DIFF"
  diff "$BASE/pixels.sha256" "$NEW/pixels.sha256" | head -20
  echo "  (render both and LOOK -- coordinates alone have hidden a"
  echo "   mirrored brace before now)"
  rc=1
fi

grep -E "^(PASS|FAIL)" "$NEW/ua-demo.verapdf.txt" | sed 's/^/  verapdf      /'
grep -qE "^FAIL" "$NEW/ua-demo.verapdf.txt" && rc=1

[ $rc -eq 0 ] && echo "  => the change is nominal" || echo "  => the change is NOT nominal"
exit $rc
