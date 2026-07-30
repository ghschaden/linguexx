# Work order: fixes from the 2026-07-30 code review

Status: PHASES A AND B EXECUTED (A on branch `review-fixes`, B on branch
`phase-b-coverage`). Phases C and D are NOT EXECUTED — deferred by the
user. The descriptions below are unchanged and remain the work order for
a future run; each deferred item is marked in place.

Executed, one commit each, every one gated on the full three-engine suite:

| Item | Status | Commit |
|------|--------|--------|
| A1 `\z.` inside `exe` | done | `c48a6a1` |
| A2 hyperref anchor collision | done | `47097d8` |
| A3 stray `\a.` leaks a list | done | `eaf1d2f` |
| A4 `\lpzg` empty key | done | `21f7d4b` |
| B1 `[legacy,gb4e]` test case | done | `87bcb92` |
| B2 `\crefrange` assertions | done | `ffcdb1b` |

No item was blocked. Final gate on the Phase A branch tip:
`python3 tests/runtests.py` 912/912 assertions on pdflatex, xelatex and
lualatex; `verapdf examples/ua-demo.pdf` compliant on all three profiles
(PDF/UA-2 + Tagged PDF, WTPDF 1.0 Accessibility, WTPDF 1.0 Reuse). Final
gate on the Phase B branch tip: 963/963 assertions on the three engines
(B added 13 assertions per engine in a new `legacy-gb4e` case and 4 in
`cleveref`). Phase B did not touch tagging and changed no package code:
`linguexx.sty` is byte-identical to its state on `main`, so the veraPDF
gate is inherited from Phase A unchanged.

Two notes for whoever picks up C/D:

- The suite harness now attaches the case's `.aux` to the page object
  (`page.aux`), alongside the existing `page.log`. A2 needed it because a
  hyperref anchor is invisible in the rendering and only two of the three
  engines report a duplicate destination at all.
- A1's DELIBERATE NON-CHANGE (inside `exe`, `\ex` continues at the current
  level) is now implemented and tested but still undocumented — D1 is the
  place for it, and it is the one piece of user-visible behaviour Phase A
  established without a matching line in the manual.

Scope: `linguexx.sty` v1.1, test suite, manual.
Read `CLAUDE.md` first; its verification rules are binding for every phase
below. In particular: never conclude from exit codes, run
`python3 tests/runtests.py` (all three engines) before delivering, run
`verapdf` on `examples/ua-demo.pdf` after anything that touches tagging,
and remember that PDF/UA validity needs a THIRD pass under pdflatex/xelatex.

Line numbers below refer to the tree as of commit `eb449e6`. If they have
drifted, the quoted code is the anchor, not the number.

Execution order: A before B before C before D. Phases A and B are
independent of C. One commit per numbered item.

---

## Phase A — bug fixes (each ships with the test that would have caught it)

### A1. `\z.` is unusable inside an `exe` batch (VERIFIED bug)

Evidence (both verified by compilation on 2026-07-30):

```latex
\begin{exe}
\ex GBONE main one.
\a. SUBA sub via dot syntax.
\z.                     % -> "! Package linguexx Error: \z. outside an example."
\ex GBTWO ...
\end{exe}
```

and with the `\z.` omitted, `\ex GBTWO` is SILENTLY demoted to sub-item
"b." instead of becoming example (2) — no error, wrong output.

Cause: `\lx@zpop` (near line 1066) gates only on `\iflx@inexample`, which
is set exclusively by the dot-syntax path `\lx@run@ex` (line ~828); `exe`
sets `\iflx@inexe` instead. The demotion happens because
`\lx@gbex@plain` dispatches on `\lx@subdepth`, still 1 after the `\a.`.

Fix:
- `\lx@zpop` accepts the pop whenever `\lx@subdepth > 0` (the
  `\begingroup`-opened sublevels are exactly what `\lx@closelist\endgroup`
  unwinds), regardless of `\iflx@inexample`.
- The "ends the example" branch (`\lx@zexit`) stays gated on
  `\iflx@inexample`. A main-level `\z.` inside `exe` becomes a package
  error whose message says what is true: at the main level of an exe
  batch, end it with `\end{exe}`.
- DELIBERATE NON-CHANGE: `\ex` after `\a.` continuing at the letter level
  is kept — it is the same rule xlist documents (`\ex` = item at the
  current level), and `\z.` now provides the escape. Document it (D1)
  instead of "fixing" it.

Test: extend `tests/gbfour.tex` — `\a.` inside `exe`, then `\z.`, then
`\ex`; assert in `a_gbfour` that the following `\ex` numbers at the MAIN
level (label sequence + x-position, not just compilation).

### A2. hyperref anchor collision for footnote sub-examples (VERIFIED bug)

Evidence: with hyperref, a sub-example "a" under main example 1 and a
sub-example "a" under a footnote example (while `ExNo`=1) both get anchor
`lxex.1.a`; pdfTeX warns `destination with the same identifier
(name{SubExNo.lxex.1.a})` and the `.aux` shows both `\newlabel`s storing
the same anchor, so `\ref` to the footnote sub-example links to the
main-text one.

Cause: `\theHSubExNo` / `\theHSubSubExNo` (lines ~242–243) build anchors
from `ExNo` unconditionally, with no `\if@noftnote` branch — unlike the
printed `\theSubExNo`, which does branch.

Fix: branch both on `\if@noftnote` (an expandable plain-`\newif`
conditional, safe in the `\theH...` context), giving footnote sub-examples
`lxfnex.<FnExNo>.<alph>` / `lxfnex.<FnExNo>.<alph>.<n>` anchors.

Test: new case `tests/hypanchors.tex` + `ASSERTIONS` entry — hyperref
loaded; a main sub-example and a footnote sub-example labeled "a" under
the same `ExNo`; assert (i) the log does NOT contain "destination with
the same identifier" (log assertions are a supported pattern, see
`a_lpzgcheck`), (ii) both `\ref`s print their distinct forms
("(1a)" vs "(ia)"). Remember `DEFAULT_PASSES = 2` already covers the
cross-referencing reruns.

### A3. Stray `\a.` in prose leaks an open list

A bare `\a.` outside any example silently opens a list and a
`\begingroup` that nothing closes; the failure surfaces as
"\begin{list} ended by \end{document}" arbitrarily far away.

Fix: in the depth-0 push (`\lx@subpush@i`, line ~1133), raise a package
error when neither `\iflx@inexample` nor `\iflx@inexe` holds. (Note
`\a.` inside `exe` reaches this path legitimately via the global `\a`
hook — that is why the guard must accept `\iflx@inexe`.)

Test: new case + entry in `EXPECT_ERROR` in `tests/runtests.py` (the
harness category built for exactly this; the raised error is the
assertion).

### A4. `\lpzg` records an empty key for trailing/doubled periods

`\lpzg{sg.}` splits into `{sg}{}`; the empty segment is recorded as a used
key and `\lpzgcheck` later warns "No expansion known for ." (confusing,
harmless).

Fix: skip blank segments in `\lx@lpzg@build` (line ~1524), one
`\tl_if_blank`-style guard in the `\seq_map_inline`.

Test: add `\lpzg{sg.}` to `tests/lpzgcheck.tex`; assert the log does not
warn about an empty key and `sg` is still recorded once.

---

## Phase B — coverage gaps (no package change)

EXECUTED (`87bcb92`, `ffcdb1b`), and it did stay a no-package-change
phase: both items pin behaviour that was already correct, and neither
needed a line of `linguexx.sty`. What each landed is recorded under the
item.

### B1. `[legacy,gb4e]` test case

The combination COMPILES AND RENDERS CORRECTLY (verified 2026-07-30:
legacy geometry, hanging `\ex[*]{...}` judgment, xlist letters all
correct), so it stays supported — the shortcoming is only that no case
pins it. New case `tests/legacy-gb4e.tex` + assertions: legacy sub-indent
(`\SubExleftmargin`=2em, cf. `a_legacy`'s measured-em technique) inside
`exe`, judgment not displacing text, xlist letters, `\Last` resolving
across the batch.

DONE (`87bcb92`): `tests/legacy-gb4e.tex` + `tests/_preamble-legacy-gb4e.tex`
(the combination needed its own preamble; `_preamble-gb4e.tex` is
`[lazy,gb4e]`) + `a_legacy_gb4e`, 13 assertions. Beyond the four asked
for: the sub labels sit flush at the parent's text margin (legacy's
`\labelsep\z@`), the roman label likewise and prints `(i)`, the mark
actually protrudes left of the text block, and two marks still clear the
letter in legacy's tighter sub label box. Mutation-checked — `\labelsep`
non-zero, `\SubExleftmargin` 2.2em, `\SubSubExLBr/RBr` dropped, and
`\llap`→`\mbox` in `\lx@hangjudge` each kill assertions here.

### B2. `\crefrange` assertions

`tests/cleveref.tex` only exercises `\cref` lists. Add `\crefrange`
over two sub-examples and assert it prints "(1a) to (1b)" with the empty
`\crefname`s — pinning both cleveref's behaviour and the `\lx@crefname`
guard. Note for the manual (D1): `\refrange` remains the compact
"(1a–c)" form; cleveref cannot compress shared-prefix ranges, so the
`\sublabel` machinery is NOT redundant and must not be removed.

DONE (`ffcdb1b`): four assertions in `a_cleveref`. `\crefrange` prints
"(1a) to (1b)" over two sub-examples and "(1) to (2)" over two whole
ones; `\refrange` over the SAME pair prints "(1a–b)" and is not
cleveref's spelling of it — the non-redundancy above is now
machine-checked, not just written down. The two sub-examples carry a
`\sublabel` beside their `\label` so both commands can address them.
Mutation-checked: `\rangedash`→"~to~" kills the compression assertion, a
non-empty `\lx@crefname` kills both `\crefrange` assertions. The manual
note is still D1's, and still unwritten.

---

## Phase C — behavior-neutral refactors (the suite + veraPDF are the proof)

NOT EXECUTED — deferred by user. C1/C2/C3 are untouched; in particular
`\altn`'s spoken /Alt does NOT yet carry the Leipzig expansion, and the
`\cs_generate_variant:Nn \tag_struct_begin:n { e }` and
`\lx@assert@letters` cleanups are still pending.

Run the FULL gate after each item: 3-engine suite, `verapdf` on
`examples/ua-demo.pdf`, `pdfinfo -struct-text` sanity read.

### C1. One tagged-Span helper

The idiom exist-guard → `\tag_if_active:` → `\tag_mc_end_push:` →
`\tag_struct_begin:` → `\tag_mc_begin:` → content → close →
`\tag_mc_begin_pop:n{}` is hand-copied ~6 times: `\lx@hangjudge` (~492),
`\lpzg` (~1531), `\lx@glt@langbegin/end` (~2181), `\__lxp_alt_emit_tagged:`
(~2352), `\__lxp_altg_emit:n` (~2571), and the gloss column/word wrappers
(~1961–1987). Add `\lx@tag@span:nn {keyvals}{content}` plus an open/close
pair (needed for the `\glt` case, whose open and close sit in different
places), and replace the copies.

Side effect to fold in: the helper carries the single canonical guard,
and the unguarded `\cs_generate_variant:Nn \tag_struct_begin:n { e }`
(line ~2369) is deleted — use `\exp_args:Ne \tag_struct_begin:n` at the
call sites instead. This removes the inconsistency where every use site
guards for a kernel without `\tag_...` commands but the variant
generation would already have failed at load on such a kernel.

CAUTION (from CLAUDE.md history): Span placement relative to the ambient
MC is exactly where v0.10 broke PDF/UA. The helper must reproduce the
push/pop order byte-for-byte; the `ua` case, `struct_label_depths`, and
veraPDF on ua-demo are the oracles, and none alone is sufficient.

### C2. Unify `\altn` / `\altg` internals

Near-clones to merge: the grab loops (`\__lxp_alt_grab:` /
`\__lxp_altg_grab:`), the spoken-/Alt builders (`\__lxp_alt_buildalt:` /
`\__lxp_altg_buildalt:`), the two TikZ brace drawers (same logic,
different y-anchoring — parameterize by the two y-coordinates), and the
setstack routines (parameterize by column spec + font hook).

Two decided behavior points, both for the changelog:
- `\altn` gains the Leipzig expansion in its spoken /Alt that `\altg`
  already has (today `\altn{\lpzg{sg}}...` speaks "SG" where `\altg`
  speaks "singular"; the unified builder makes the better behavior
  uniform). This CHANGES /Alt strings, so it lands only after C1 is
  green, and `tests/tagged.tex` gets an assertion for it.
- Replace the `\tl_gput_right` (global) writes into
  `\l__lxp_altg_alt_tl` — an `l_`-named local, violating the expl3
  naming contract — with a `g_`-named scratch, or restructure so the
  group scoping the `\lpzg` redefinition is not straddled.

### C3. Small cleanups

- Delete the `\lx@assert@letters` alias (line ~1010); it is
  `\lx@install@letters` under a second name.
- Factor the six zeroed list parameters + `\let\makelabel\lx@flushlabel`
  shared by `\lx@mainlist` / `\lx@sublist@i` / `\lx@sublist@ii` into one
  setup macro. No new user-facing names.

---

## Phase D — documentation and one deferred decision

NOT EXECUTED — deferred by user. The manual has NOT been extended, so the
A1 rule that Phase A just established (inside `exe`, `\ex` continues at the
current level; pop with `\z.`) is implemented and tested but still
undocumented in `linguexx-doc.tex`. D2 remains deferred on its own terms.

### D1. Manual additions (`linguexx-doc.tex`; builds with LUALATEX ONLY,
it errors by design under pdflatex — see CLAUDE.md)

- Body-collection limitation: `\verb` and catcode changes inside example
  bodies cannot work (tokens are collected before typesetting; inherent,
  same as linguex's `\par`-delimited grab).
- Cross-referencing guidance: `\Last`/`\Next`/`\NNext`/`\LLast` are the
  positionally fragile linguex compatibility surface; steer new documents
  to `\label` + `\cref`/`\refrange`. They are kept — removing them breaks
  the compatibility promise.
- The A1 rule: inside `exe`, `\ex` continues at the current level; pop
  with `\z.`.

### D2. Minipage footnotes — DEFERRED, decision needed

Only `\@footnotetext` is patched (line ~218); `\@mpfootnotetext` is not,
so examples in minipage footnotes number on the main `ExNo` series.
Whether they should share `FnExNo`, stay on the main series, or get a
per-minipage series is a semantic choice with no linguex precedent.
Decision: document the current behavior in D1 and DO NOT patch until a
real use case decides the semantics. Do not "fix" this in passing.

---

## Explicitly out of scope

- Removing `\refrange`/`\prefrange`/`\sublabel` (not redundant with
  cleveref — see B2).
- Removing `[legacy,gb4e]` (verified working — see B1).
- Any new default user syntax (CLAUDE.md: forbidden without prior
  explicit validation).
