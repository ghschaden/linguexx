#!/bin/sh
# Compile the recon doc on the CI's TeX Live and print all diagnostics.
set -e
cd "$(dirname "$0")"
echo "########## TeX Live version ##########"
lualatex --version | head -1
echo "########## which math-tagging files exist ##########"
for f in latex-lab-math.sty luamml.sty luamml-tagpdf.sty luamml-amsmath.sty \
         latex-lab-testphase-math.sty; do
  printf "%-32s " "$f"; kpsewhich "$f" 2>/dev/null || echo "(absent)"
done
echo "########## compile recon.tex (twice) ##########"
lualatex -interaction=nonstopmode recon.tex > recon.log 2>&1 || true
lualatex -interaction=nonstopmode recon.tex > recon.log 2>&1 || true
echo "--- command probes (from the log) ---"
grep -aE "PROBE|luamml|latex-lab-math" recon.log | grep -iE "PROBE|luamml|math" | sort -u | head -40
echo "--- loaded .sty files mentioning math/mathml (from the log) ---"
grep -oE "[a-z0-9-]*math[a-z0-9-]*\.(sty|ltx|lua)" recon.log | sort -u | head
echo "########## structure probe ##########"
python3 probe.py
