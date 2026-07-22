# linguexx — notes for Claude

Standalone and modern reimplementation of `linguex` (numbered linguistic examples, interlinear glosses, PDF/UA tagging). expl3. A4.

## Environment
- TeX Live 2026 (LuaHBTeX). All three engines must pass: pdflatex, xelatex, lualatex.
- Taging preamble: `\DocumentMetadata{...}` with `testphase={phase-III}` (portable), NOT the old `{tagpdf,text,sec,block}` list.
- veraPDF installed (`verapdf`): this is the ONLY oracle that is authoritative for PDF/UA.

## Verification — non-negotiable
- NEVER conclude that a rendering is correct based on an exit code. Render the PDF (`pdftoppm`) and INSPECT it.
- For any geometric shape (braces, alignments), verify the POSITION *and the shape* — not just the coordinates. The mirrored brace bug came from measuring the position without looking at the curvature.
- Test assertions prove the actual geometry and tagging, not just successful compilation. Mutation-tested suite: every rule has a mutation that kills it.
- Run `python3 tests/runtests.py` (all 3 engines) before delivering.
- Run `verapdf` on the examples/ua-demo.pdf before delivering and make sure that result is compliant.
- Check with `pdfinfo -struct-text ua-demo.pdf` whether the tagging structure makes sense.


## Package Invariants
- `\altn` / `\altg`: TEXT mode only. No math, no italics, no amsmath. No `Formula` element in the tree (this is what broke PDF/UA-2 before v0.12; avoiding it is the goal).
- Braces drawn in TikZ on both sides. The `brace` decoration bulges according to the path direction: ascending = opening `{`, descending = closing `}`.
- `\altg` is written twice in a gloss (objects, then glosses); same number of alternatives in both calls; no spaces between groups.
- Tagging idiom: `\tag_mc_end_push:` … `\tag_mc_begin_pop:n{}`.
- `[legacy]` mode = geometric fidelity to linguex; orthogonal to `[lazy]`/`[gb4e]`.

## Do Not
- Ship a tagging fix without validating it with veraPDF on TL2026 (lesson from v0.10: Span > Part/P broke compliance).
- Introduce a new user syntax "by default" without prior explicit validation.
