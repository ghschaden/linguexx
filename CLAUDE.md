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
- Run `python3 tests/runtests.py` (all 3 engines) before delivering. It now runs `verapdf` itself, on the `ua` case, so PDF/UA compliance is checked on every run and veraPDF is a hard requirement of the suite.
- Still run `verapdf` on examples/ua-demo.pdf before delivering: it is the full accessible document (and covers footnote examples, which the `ua` case deliberately omits — see its header comment).
- Check with `pdfinfo -struct-text ua-demo.pdf` whether the tagging structure makes sense.
- The manual (`linguexx-doc.tex`) builds with **lualatex only** and errors out under pdflatex. It contains the dot-below transliteration examples of its §9.3, which pdflatex gives a broken text layer (`kṛṣṇaḥ` extracts as `kr.s.n.ah.`), so building it with pdflatex made the manual exhibit the defect it documents. Do not add `fontspec`/`\setmainfont` to it: the kernel's own Latin Modern under LuaLaTeX has the small-caps and bold-mono shapes the manual needs, and naming the families explicitly loses them.
- veraPDF and the structure checks are COMPLEMENTARY, and neither alone is sufficient. An element opened at the wrong moment (marked content straddling its parent) fails veraPDF but passes every structure assertion; an element never closed is spec-valid, so veraPDF passes it while the rest of the document silently becomes its child — that one is caught only by `struct_label_depths`, which asserts that top-level example numbers all sit at one depth.
- PDF/UA validity needs a THIRD LaTeX pass under pdflatex and xelatex (lualatex converges in two). An unconverged file fails veraPDF exactly like a real regression; see `PASSES` in runtests.py before concluding a tagging change broke something.


## Package Invariants
- `\altn` / `\altg`: TEXT mode only. No math, no italics, no amsmath. No `Formula` element in the tree (this is what broke PDF/UA-2 before v0.12; avoiding it is the goal).
- Braces drawn in TikZ on both sides. The `brace` decoration bulges according to the path direction: ascending = opening `{`, descending = closing `}`.
- `\altg` is written twice in a gloss (objects, then glosses); same number of alternatives in both calls; no spaces between groups.
- Tagging idiom: `\tag_mc_end_push:` … `\tag_mc_begin_pop:n{}`.
- `[legacy]` mode = geometric fidelity to linguex; orthogonal to `[lazy]`/`[gb4e]`.

## Do Not
- Ship a tagging fix without validating it with veraPDF on TL2026 (lesson from v0.10: Span > Part/P broke compliance).
- Introduce a new user syntax "by default" without prior explicit validation.
