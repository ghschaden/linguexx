# Work order: fixes from the 2026-07-30 code review

Status: ALL OF A, B, C AND D1 EXECUTED, all on `main`. D2 remains
deferred — on its own terms, as the item itself prescribes: its current
behaviour is now documented and nothing is patched. The descriptions
below are unchanged; each item records what landed under it.

Executed, one commit each, every one gated on the full three-engine suite:

| Item | Status | Commit |
|------|--------|--------|
| A1 `\z.` inside `exe` | done | `c48a6a1` |
| A2 hyperref anchor collision | done | `47097d8` |
| A3 stray `\a.` leaks a list | done | `eaf1d2f` |
| A4 `\lpzg` empty key | done | `21f7d4b` |
| B1 `[legacy,gb4e]` test case | done | `87bcb92` |
| B2 `\crefrange` assertions | done | `ffcdb1b` |
| C1 one tagged-Span helper | done | `6fca2d0` |
| C2 unify `\altn`/`\altg` | done | `a406394` |
| C3 small cleanups | done | `3e83767` |
| D1 manual additions | done | `8cdb80b` |
| D2 minipage footnotes | deferred by design | — |

No item was blocked. Final gate at `8cdb80b`: `python3 tests/runtests.py`
1017/1017 assertions on pdflatex, xelatex and lualatex; `verapdf
examples/ua-demo.pdf` compliant on all three profiles (PDF/UA-2 + Tagged
PDF, WTPDF 1.0 Accessibility, WTPDF 1.0 Reuse); `linguexx-doc.tex` builds
clean under lualatex and still errors by design under pdflatex.

How the three C refactors were shown to be behaviour-neutral, since the
suite alone cannot show it: each was compiled against the previous
commit's `linguexx.sty` over the cases it touches, under pdflatex and
lualatex, and BOTH the 200dpi rendering and the `pdfinfo -struct-text`
tree compared byte for byte. C1 and C2: altg, tagged, gloss, glt,
judgments, lpzgcheck, ua, altg-demo, plus a probe of all three `\altn`
alignments. C3: the list-geometry cases (tagged, legacy, legacy-gb4e,
zpop, gbfour, numbering, judgment-align, gloss, ua). All identical.

Three things a later run should know:

- The suite harness attaches the case's `.aux` to the page object
  (`page.aux`), alongside the existing `page.log`. A2 needed it because a
  hyperref anchor is invisible in the rendering and only two of the three
  engines report a duplicate destination at all.
- It also has `brace_bulge()`, which re-renders a page with `pdftoppm` and
  measures which way a drawn brace curls. It exists because the suite was
  BLIND to a mirrored brace — the v0.13 bug — and C2 put both braces on
  one shared drawer, where a single mutation would have broken `\altn`
  and `\altg` at once. It is the only assertion in the suite that reads
  ink rather than the text layer; no new dependency (`pdftoppm` was
  already required).
- C2's one user-visible change: `\altn`'s spoken `/Alt` now expands a
  Leipzig key, as `\altg`'s already did. In `CHANGELOG.md` under 1.1,
  which is where the A-phase fixes went too; no version bump was made.

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

EXECUTED (`6fca2d0`, `a406394`, `3e83767`). The heading's premise turned
out to be half right: the suite and veraPDF caught nothing, because there
was nothing to catch, but they could not have PROVED neutrality either —
they pass on plenty of layouts that are not the previous one. The
byte-comparison of renderings and structure trees described at the top is
what actually did the proving, and it is the method to reuse.

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

DONE (`6fca2d0`). The helper is a PAIR of pairs, which the item did not
anticipate: `\lx@tag@span@open:n`/`@close:` (suspend the ambient MC, open
the Span) and `\lx@tag@span@begin:n`/`@end:` (those plus our own MC, for
leaf content), with `\lx@tag@span:nn` and `\lx@tag@span@exp:nn` as the
guarded one-shot forms. The split is what the gloss column needs: its
content is the tier words, each opening marked content of its own, so it
takes the outer pair only. `\lx@gl@wordbegin/end` fit NEITHER — their
struct is conditional but their MC is not — and take the shared guard
alone; the item's count of six sites was one too many.

The guard `\lx@tag@if@active:` is deliberately not named `@span`: the
text-unit close at `\lx@tag@close@textunit` needs the same two conditions
and now shares it, so five hand-copied spellings became one. Two of the
five tested `\cs_if_exist:N` on `\tag_if_active:T`, a conditional variant
rather than the base name. The unguarded `\cs_generate_variant:Nn
\tag_struct_begin:n { e }` is gone with them.

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

DONE (`a406394`). All four merges landed: `\__lxp_grab:NN`,
`\__lxp_buildalt:NN`, `\__lxp_setstack:NNnn` (column spec + a hook that
carries both the tier font and the local `\lpzg`), `\__lxp_brace:nnn`
(the two ordinates; `baseline=0pt` is what lets one drawer serve both,
since it is where a tikzpicture puts the baseline by default anyway when
the box bottom is 0). The `g_`-named scratch was taken, not the
restructuring.

Both decided behaviour points landed as written, and NOTHING ELSE
changed: `\altn` still prints a nested `\lpzg` as a tagged abbreviation
with its own `/E`, where `\altg` sets it plain. That asymmetry was left
alone deliberately — it is UA-valid (checked), the item did not ask for
it, and `tests/tagged.tex` now pins it so any future change is a decision
rather than a side effect.

One addition beyond the item, agreed with the user mid-run: `tests/altn.tex`
and `brace_bulge()`. Merging the two brace drawers put both braces behind
one mutation, and the suite was demonstrably blind to a mirrored brace —
verified by mutating the drawer and watching all 329 lualatex assertions
pass. See the note at the top.

### C3. Small cleanups

- Delete the `\lx@assert@letters` alias (line ~1010); it is
  `\lx@install@letters` under a second name.
- Factor the six zeroed list parameters + `\let\makelabel\lx@flushlabel`
  shared by `\lx@mainlist` / `\lx@sublist@i` / `\lx@sublist@ii` into one
  setup macro. No new user-facing names.

DONE (`3e83767`). Both, as written; the shared setup is
`\lx@listdefaults`, and what differs between the three levels (`\topsep`
and the level geometry) stays at each call site, which is the point.

---

## Phase D — documentation and one deferred decision

D1 EXECUTED (`8cdb80b`). D2 remains deferred on its own terms — its
current behaviour is documented, as the item itself prescribes, and
nothing is patched.

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

DONE (`8cdb80b`), all three, plus the D2 behaviour note under "Notes and
limitations". The A1 rule went into §3.5 as a LIVE example, so the
rendering is the package's own answer rather than a claim about it — and
it replaced a sentence that said the opposite ("`\z.` has no role to
play" inside `exe`), which was the one place the manual actively misled.
B2's converse note is in §6.4.

CORRECTION to the first bullet, and the reason to read it before reusing
this file: the blanket claim is FALSE, as compiling it shows. `\verb`
fails in the dot syntax (collected body) and in the braced
`\ex[j]{text}` form (macro argument), but works normally under `exe` and
`xlist` with an unbraced `\ex`, including inside an `\a.` written within
the batch. The manual documents that matrix and names the workaround;
the blanket version would have hidden a construct that works.

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
