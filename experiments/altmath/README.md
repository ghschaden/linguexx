> **Status: superseded (v0.13).** `\alt` was rebuilt in text mode (a
> tabular stack with a TikZ brace, no math), which removes the `Formula`
> entirely and lets the alternatives be tagged as text with a spoken
> `/Alt`. The math-tagging reconnaissance below is kept only as a record
> of how that conclusion was reached; it is no longer needed.

# `\alt` math-tagging reconnaissance

`\alt` typesets its stacked alternatives as a math formula. In a tagged PDF
that formula is conformant (it passes PDF/UA-2), but a screen reader reads the
braces and the concatenated alternatives literally. Giving it a clean spoken
form means attaching alternate/expansion text to the *formula*, and the
interface for that lives in the math-tagging code of a current TeX Live — which
cannot be developed against an older local TeX Live. This folder develops it
against the CI's TeX Live instead.

## What is here

- `recon.tex` — probes which math-tagging commands exist and typesets one
  `\alt`-style formula under full PDF/UA-2 tagging.
- `probe.py` — dumps the accessibility structure of `recon.pdf`: how the
  formula is tagged, and whether any `/Alt`, `/ActualText`, `/E`, MathML, or
  associated file is attached (the last two matter because `luamml` may be
  supplying the actual reading).
- `run.sh` — compiles and runs the probe, printing a labelled report.

## How to run it

The reconnaissance is wired as a **manual** CI job so it never runs on ordinary
pushes:

- GitLab: open the pipeline, find the `alt-recon` job, press play. Read its log
  and/or download the `recon.pdf` / `recon.log` artifact.
- GitHub: Actions tab → `alt-recon` → "Run workflow". Same outputs.

## What to look for in the output

1. The `PROBE ... : YES/no` lines — which of `\UseMathForPositioningText`,
   `\MathCollectFalse`, `\mathalt`, `\tag_math_alt:n`, `\luamml_annotate:nn`
   the toolchain actually provides.
2. The Formula struct element's dictionary — is there an `/Alt`, `/ActualText`,
   or `/AF` already?
3. Whether MathML is present (`<math`, `AFRelationship`) — if `luamml` attaches
   MathML, that, not the glyph text, is what a screen reader reads.

Those three answers determine the correct way to give `\alt` a spoken form, and
the fix will then be written and validated here before it touches `linguexx.sty`.
