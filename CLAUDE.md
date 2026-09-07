# linguexx — notes for Claude

Standalone and modern reimplementation of `linguex` (numbered linguistic examples, interlinear glosses, PDF/UA tagging). expl3. A4.

## Environment
- TeX Live 2026 (LuaHBTeX). All three engines must pass: pdflatex, xelatex, lualatex.
- Taging preamble: `\DocumentMetadata{...}` with `testphase={phase-III}` (portable), NOT the old `{tagpdf,text,sec,block}` list.
- veraPDF installed (`verapdf`): this is the ONLY oracle that is authoritative for PDF/UA.

## Harness — `.claude/tools/lxx`
Local agent tooling (in `.claude/`, untracked; ignore this section if it is
not there). It wraps the tools below so that a debugging loop costs one
command and a few lines instead of a 40 kB log. It never restates an
assertion: it imports `tests/runtests.py` for `PASSES`, the parsers and the
geometry helpers, so nothing here can drift away from the suite.

- `lxx test [-k F] [-e E]` — the suite with the 248 green lines folded away;
  failures grouped by CASE, engines named, so a defect that fails all three
  prints once. Every failure is re-run SERIALLY before it is reported: a
  concurrent xdvipdfmx temp-file race makes a xelatex case die about once in
  600 runs with no TeX error at all (see `DEFAULT_JOBS`, now 6), and a red
  that cannot be trusted is a gate that gets overridden. A confirmed
  failure is still red; a refuted one prints as FLAKY with the command that
  refuted it. On a full green run it writes the stamp the hooks read — so does
  a raw `python3 tests/runtests.py` that prints "All green."
- `lxx verify [--quick]` — the whole gate of the section below in one go.
- `lxx build CASE [-e E]` / `lxx snippet -c '\ex. ...' [--preamble _preamble-tagged]`
  — compile a case or an ad-hoc repro into a build dir that STAYS
  (`.claude/.state/build/`), with the suite's own preambles and pass count.
- `lxx log [CASE|FILE]` — a TeX log as its errors, each with the `l.NNN`
  line, plus warnings and a box count. Reading a big `.log` whole is
  refused by a hook that names this command; grep still works.
- `lxx words PDF [-g RE] [--line RE]` — word boxes in points, and every word
  on the rendered line of a match: the geometry oracle, interactively.
- `lxx png PDF [-p N] [--crop|--box x0 y0 x1 y1]` — a rendering, cropped to
  the ink, for LOOKING at, which the section below requires.
- `lxx struct PDF` — the tag tree folded (494 lines → ~130), plus the
  label-depth and no-Formula invariants. `lxx ua PDF` — veraPDF's 190 kB
  report as one line per failed rule with a location.
- `lxx diff A.pdf B.pdf` — which pages differ and the box the change sits in.
- Three hooks enforce the section below rather than trusting memory: a commit
  is held back when `linguexx.sty` or a case has changed since the last green
  run (`LXX_SKIP_GATE=1` overrides), a turn that CLAIMS completion on such a
  tree is stopped once, and a `.log` over 6 kB is not read whole. They compare
  hashes, so "I ran the suite" cannot be believed, only checked.
- The `log-triage` subagent (haiku) is for FAN-OUT only: many logs, many
  builds, one question. For a single log, run `lxx log` — a subagent that
  re-derives the context is the expensive way to read four lines.

## Verification — non-negotiable
- NEVER conclude that a rendering is correct based on an exit code. Render the PDF (`pdftoppm`) and INSPECT it.
- For any geometric shape (braces, alignments), verify the POSITION *and the shape* — not just the coordinates. The mirrored brace bug came from measuring the position without looking at the curvature.
- Test assertions prove the actual geometry and tagging, not just successful compilation. Mutation-tested suite: every rule has a mutation that kills it.
- Run `python3 tests/runtests.py` (all 3 engines) before delivering
  (`lxx test`, or `lxx verify` for this whole list at once). It now runs `verapdf` itself, on the `ua` case, so PDF/UA compliance is checked on every run and veraPDF is a hard requirement of the suite.
- Still run `verapdf` on examples/ua-demo.pdf before delivering (`lxx verify`
  does it, on a build of its own): it is the full accessible document (and covers footnote examples, which the `ua` case deliberately omits — see its header comment).
- Check with `pdfinfo -struct-text ua-demo.pdf` (or `lxx struct`) whether the
  tagging structure makes sense.
- The manual (`linguexx-doc.tex`) builds with **lualatex only** and errors out under pdflatex. It contains the dot-below transliteration examples of its §9.3, which pdflatex gives a broken text layer (`kṛṣṇaḥ` extracts as `kr.s.n.ah.`), so building it with pdflatex made the manual exhibit the defect it documents. Do not add `fontspec`/`\setmainfont` to it: the kernel's own Latin Modern under LuaLaTeX has the small-caps and bold-mono shapes the manual needs, and naming the families explicitly loses them.
- veraPDF and the structure checks are COMPLEMENTARY, and neither alone is sufficient. An element opened at the wrong moment (marked content straddling its parent) fails veraPDF but passes every structure assertion; an element never closed is spec-valid, so veraPDF passes it while the rest of the document silently becomes its child — that one is caught only by `struct_label_depths`, which asserts that top-level example numbers all sit at one depth.
- PDF/UA validity needs a THIRD LaTeX pass under pdflatex and xelatex (lualatex converges in two). An unconverged file fails veraPDF exactly like a real regression; see `PASSES` in runtests.py before concluding a tagging change broke something.


## Package Invariants
- `\altn` / `\altg`: TEXT mode only. No math, no italics, no amsmath. No `Formula` element in the tree (this is what broke PDF/UA-2 before v0.12; avoiding it is the goal).
- Braces drawn in TikZ on both sides. The `brace` decoration bulges according to the path direction: ascending = opening `{`, descending = closing `}`.
- `\altg` is written twice in a gloss (objects, then glosses); same number of alternatives in both calls; no spaces between groups.
- Judgment marks in a stack hang into a gutter ONLY under `[phantomalign]`
  (`\GlossPhantomAlign`), and in `\altg` only on the call that sets the
  OBJECT tier plus a solo stack -- a gloss is a translation, not something
  that is grammatical or not. Both commands build their stack through
  `\__lxp_alt_build:NNnnN`; keep it that way rather than inlining the
  decision, which drifted twice when it was written out per caller.
- Relative references (`\Next` & co.) link only to an anchor the PREVIOUS
  run recorded in the `.aux`, and never to one two examples claimed. A
  constructed `\hyperlink` that skips that check is a silent wrong jump:
  a missing destination is not an error, the backend substitutes a
  whole-page one, and xelatex does not even warn. See the block above
  `\Last` in the .sty, and `doc/DEFERRED-DECISIONS.md` on the shared
  anchors themselves.
- Under `beamer` those anchors are linguexx's own (beamer sets hyperref's
  `implicit=false`), and a frame is typeset once per overlay slide with
  the counters restored -- so one example comes past several times with
  one number. `\lx_relref_if_unseen_here:` tells that from a reset
  counter, and it asks about the FRAME (`\c@framenumber`), never about
  the pass. Both mistakes are live: a by-name check swallows a reset
  (the name is exactly what the two cases have in common), and a
  by-pass check strands an example inside `\only<2->{...}`, whose first
  appearance IS a later pass. It also refuses a pass on which the example
  is covered (`\beamer@coveringdepth`), because `\pause`/`\uncover` RUN
  their material on every slide and only drop its ink -- so the pass an
  example is first run on is not the slide a reader can see it on. Both
  mistakes shipped and were reported from a lecture deck; neither leaves a
  trace on the page, which is why the tests assert on `.aux` records and on
  the page a destination resolves to.
- Tagging idiom: `\tag_mc_end_push:` … `\tag_mc_begin_pop:n{}`.
- `[legacy]` mode = geometric fidelity to linguex; orthogonal to `[lazy]`/`[gb4e]`.

## Do Not
- Ship a tagging fix without validating it with veraPDF on TL2026 (lesson from v0.10: Span > Part/P broke compliance).
- Introduce a new user syntax "by default" without prior explicit validation.
- Settle anything listed in `doc/DEFERRED-DECISIONS.md` in passing. Those behaviours are undecided on purpose; each entry says what evidence would decide it. Patching one silently picks a semantics, and the accident becomes the promise.
