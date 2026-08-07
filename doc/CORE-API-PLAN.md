# Plan: a documented core API for syntax front-ends and geometry modes

Implementation plan for an executing model. Self-contained: read this file,
`CLAUDE.md`, and the cited line ranges of `linguexx.sty` before editing.
Line numbers refer to the state at commit `5a75e53`; re-locate by the quoted
macro names if the file has moved on.

## 0. Purpose, approach, ground rules

**Goal.** Expose the seams that already exist in `linguexx.sty` as a small,
documented, stable API, so that a third-party syntax front-end (e.g. an
expex-style layer) or an alternative geometry mode can be built on the same
engine without touching internals. Two protocols:

- **Protocol A** — consumed by a *syntax front-end*: example lifecycle,
  item construction, judgments, body collection, list funnel, tagging
  helpers.
- **Protocol B** — supplied by a *geometry mode*: the three geometry hooks
  and a defaults table, behind a named registry (`default`, `legacy`).

**Non-goals.** No user-facing package split. No new user syntax. No behavior
change of any kind: every PDF this package produces must be pixel-identical
and structure-identical before and after. Do not touch the private internals
(peek_analysis loop bodies, the `\__block_list_begin:` patch, the `@endpe`
compensation, `\lx@kernel@item`, `\lx@flushlabel`, the judgment loop).

**Approach: alias-first.** Public names are created with `\cs_new_eq:NN`
pointing at the existing internal macros, placed immediately AFTER each
original definition (the target must exist), wrapped in a local
`\ExplSyntaxOn`/`\ExplSyntaxOff` pair where one is not already open. This
guarantees zero behavior change and copies `\protected` status
automatically. Only four places need real edits, each called out below
(Stages 2.1, 2.2, 3, and the test/doc stages).

The package already owns the `lx` prefix (`\l__lx_...`, `\lx@...`), so the
public names use it too: `\lx_⟨name⟩:⟨args⟩`.

**Verification discipline (from CLAUDE.md — non-negotiable).**
After EVERY stage:

```sh
python3 tests/runtests.py            # all 3 engines; runs verapdf on `ua`
```

Before delivering (Stage 6): rebuild `examples/ua-demo.pdf`, run `verapdf`
on it, check `pdfinfo -struct-text`, and compare renders against the
baseline captured in Stage 0. Never conclude correctness from an exit code.

**Git discipline.** Work on a branch (`core-api`). One commit per stage,
message stating the stage. Do not push, do not open a PR.

## Stage 0 — Baseline capture

The refactor claims to be purely nominal; capture the evidence that lets
every later stage prove it.

1. `git switch -c core-api`
2. `python3 tests/runtests.py` — must be fully green before you start.
3. Build `examples/ua-demo.pdf` with lualatex, run to convergence
   (lualatex converges in two passes). Then:
   ```sh
   verapdf examples/ua-demo.pdf                      # must pass
   pdfinfo -struct-text examples/ua-demo.pdf > BASE/ua-demo.struct
   pdftoppm -r 150 -png examples/ua-demo.pdf BASE/ua-demo
   sha256sum BASE/*.png > BASE/pixels.sha256
   ```
   Keep `BASE/` outside the repo (scratch directory). Also build
   `examples/accessible-demo.tex` and `examples/altg-demo.tex` the same way
   and capture their struct/pixel baselines.
4. Do NOT capture a baseline of `linguexx-doc.pdf` yet; the manual changes
   in Stage 5 (lualatex only — it errors under pdflatex by design).

**Per-stage oracle** (run after each of Stages 1–3): rebuild the three
example PDFs, diff `pdfinfo -struct-text` output against `BASE/`, and
compare `pdftoppm` checksums. Any difference = the stage was not nominal;
stop and fix before proceeding.

## Stage 1 — Shared services: list funnel and tagging helpers

Pure aliases. Place each block right after the original's definition.

| Public name | Aliases | Original at |
|---|---|---|
| `\lx_list_open:n` | `\lx@openlist` | `linguexx.sty:906` |
| `\lx_list_close:` | `\lx@closelist` | `linguexx.sty:907` |
| `\lx_ol_class:n` | `\lx@ol@set` | `linguexx.sty:879` |
| `\lx_tag_if_active:TF` (+T, F) | `\lx@tag@if@active:` | `linguexx.sty:497` |
| `\lx_tag_span_open:n` / `\lx_tag_span_close:` | `\lx@tag@span@open:n` / `close:` | `linguexx.sty:508-512` |
| `\lx_tag_span_begin:n` / `\lx_tag_span_end:` | `\lx@tag@span@begin:n` / `end:` | `linguexx.sty:514-518` |
| `\lx_tag_span:nn` | `\lx@tag@span:nn` | `linguexx.sty:522` |

Notes:
- The conditional needs `\prg_new_eq_conditional:NNn \lx_tag_if_active:
  \lx@tag@if@active: { TF , T , F }`, not `\cs_new_eq:NN`.
- Do NOT generate any new variants of kernel `\tag_...` commands — the
  comment at `linguexx.sty:539-543` explains why v1.1's attempt was wrong.
- `\lx@openlist`/`\lx@closelist` are `\def`-defined; `\cs_new_eq:NN` copies
  the meaning including the parameter text — correct as-is. Do not rewrite
  their call sites.

Run the per-stage oracle. Commit.

## Stage 2 — Protocol A: lifecycle, items, judgments, body collection

### 2.1 Split the example lifecycle (real edit #1)

`\lx@run@ex` (`linguexx.sty:942-952`) currently inlines the setup half.
Extract it verbatim — same tokens, same order — into a named macro:

```latex
\def\lx@example@begin{%
  \ifdim\lastskip=\Extopsep\vspace{\Exredux}\fi
  \lx@subdepth\z@
  \setcounter{SubExNo}{0}\setcounter{SubSubExNo}{0}%
  \let\lx@saved@currentlabel\@currentlabel
  \ifdefined\@currentHref
    \let\lx@saved@currentHref\@currentHref
  \fi
  \lx@inexampletrue
  \lx@letters@on}
\long\def\lx@run@ex#1{\lx@example@begin\lx@exstart#1\lx@bodyend}
```

Then alias:
- `\lx_example_begin:` ← `\lx@example@begin`
- `\lx_example_end:` ← `\lx@bodyend` (`linguexx.sty:957`)

`\lx@bodyend` is placed as a token at the end of the grabbed body and doubles
as the early-termination anchor for `\z.` — alias it, never move, duplicate,
or inline it.

`\lx@letters@on`/`@off` stay inside the pair deliberately: under `[gb4e]`
alone, `\lx@letters@local` is `\relax` (`linguexx.sty:1121-1122`), so the
save/restore degrades to a harmless no-op; documenting the pair as the
lifecycle is simpler and safer than making letters a separate call.

### 2.2 Parameterize body collection (real edit #2)

`\lx@collectbody` (`linguexx.sty:750-758`) is hard-wired to run the example:
the collector's break paths all call `\lx@runbody`, which is
`\exp_args:NV \lx@run@ex \l__lx_body_tl` (`linguexx.sty:847-848`).
Generalize the continuation, keeping the dot syntax's behavior identical:

```latex
\cs_new_eq:NN \lx@body@cont \lx@run@ex        % default continuation
\cs_new_protected:Npn \lx_body_collect:N #1
  {
    \cs_gset_eq:NN \lx@body@cont #1
    % ...the existing init lines of \lx@collectbody, unchanged...
    \__lx_body_loop:
  }
\cs_gset_protected:Npn \lx@collectbody { \lx_body_collect:N \lx@run@ex }
\cs_gset_protected:Npn \lx@runbody
  { \exp_args:NV \lx@body@cont \l__lx_body_tl }
```

The continuation is a single function taking the collected body as its one
argument. `\__lx_body_loop:` and `\__lx_body_cs:n` are NOT touched — the
terminator logic (`\par`, `\z.`, unmatched `\end`/`\endgroup`, nested
`\ex.`) stays private.

### 2.3 Item and judgment aliases (pure aliases)

| Public name | Aliases | Original at |
|---|---|---|
| `\lx_item_main:` | `\lx@exstart@normal` | `linguexx.sty:1006` |
| `\lx_item_next:` | `\lx@mainitem` | `linguexx.sty:1007` |
| `\lx_item_emit:` | `\lx@makeitem` | `linguexx.sty:1025` |
| `\lx_sub_push:` | `\lx@subpush` | `linguexx.sty:1242` |
| `\lx_sub_next:` | `\lx@subnext` | near `\lx@subpush` |
| `\lx_subenv_begin:` | `\lx@subenv@begin` | `linguexx.sty:1329` |
| `\lx_judgment_scan:` | `\lx@scanjudge` | `linguexx.sty:570` |
| `\lx_judgment_scan:n` | `\lx@scanjudgeto` | `linguexx.sty:564` |
| `\lx_judgment_set:n` | `\lx@setjudge` | `linguexx.sty:592` |

Plus one small extraction (real edit #3): `\lx@exstart@opt`
(`linguexx.sty:999`) fuses bracket-parsing with the custom-label item; give
the item half a name so front-ends get it without the bracket syntax:

```latex
\def\lx@custom@item#1{\def\lx@itemlabel{#1}\lx@mainlist\lx@scanjudge}
\def\lx@exstart@opt[#1]{\lx@custom@item{#1}}
```
and alias `\lx_item_main:n` ← `\lx@custom@item`.

Run the per-stage oracle. Commit.

## Stage 3 — Protocol B: geometry-mode registry (real edit #4)

Today the mode is chosen by `\iflx@legacy` at two sites: the defaults
selection (`linguexx.sty:395-399`) and the geometry hooks
(`linguexx.sty:434-458`). Replace the *selection mechanism* with a registry;
the *bodies* move verbatim.

```latex
\ExplSyntaxOn
\cs_new_protected:Npn \lx_mode_geometry:nnnn #1#2#3#4
  {
    \cs_set:cn { lx@geom@main@#1 } {#2}
    \cs_set:cn { lx@geom@sub@#1 } {#3}
    \cs_set:cn { lx@geom@subsub@#1 } {#4}
  }
\cs_new_protected:Npn \lx_mode_defaults:nn #1#2
  { \cs_set:cn { lx@defaults@#1 } {#2} }
\cs_new_protected:Npn \lx_mode_select:n #1
  {
    \cs_if_exist:cTF { lx@geom@main@#1 }
      {
        \cs_gset_eq:Nc \lx@geom@main { lx@geom@main@#1 }
        \cs_gset_eq:Nc \lx@geom@sub { lx@geom@sub@#1 }
        \cs_gset_eq:Nc \lx@geom@subsub { lx@geom@subsub@#1 }
        \cs_gset_eq:Nc \resetExdefaults { lx@defaults@#1 }
      }
      { \msg_error:nnn { linguexx } { unknown-mode } {#1} }
  }
\ExplSyntaxOff
```

Then:
1. Register the two existing modes under the names `default` and `legacy`,
   with the geometry bodies copied token-for-token from the two branches of
   the `\iflx@legacy` at line 434 (the non-legacy `\lx@geom@main` MUST keep
   its `\lx@ol@set{lxOLdecimal}` line, and likewise sub/subsub) and the
   defaults bodies from `\lx@defaults@lazy` / `\lx@defaults@legacy`
   (`linguexx.sty:353-393`).
2. Replace the two `\iflx@legacy` selection sites with
   `\lx_mode_select:n {legacy}` / `{default}` at the SAME position in the
   load order (the end-of-package `\resetExdefaults` call must still find
   the right table).
3. Keep `\lx@defaults@lazy` and `\lx@defaults@legacy` as `\let` aliases to
   the registry entries — comments and possibly user code reference them.
4. Add the `unknown-mode` message via `\msg_new:nnn`.

The length registers (`\Exlabelwidth`, `\SubExleftmargin`, …) and
`\lx@calc@Exlabelwidth` stay core-owned and untouched: modes read them, the
core declares them.

Run the per-stage oracle, INCLUDING the legacy cases: `runtests.py` covers
`legacy` and `legacy-gb4e` — watch those specifically. Commit.

## Stage 4 — Conformance test: a front-end built only on the API

Add `tests/frontend.tex`: a minimal expex-style front-end defined in the
preamble USING ONLY `\lx_...` public names — this is the proof the API is
sufficient, and the tripwire if a later change breaks it.

Sketch of the preamble part (adjust to what compiles cleanly):

```latex
\makeatletter
\ExplSyntaxOn
\NewDocumentCommand \pex { }
  { \lx_example_begin: \lx_body_collect:N \lx@pex@run }
\cs_new_protected:Npn \lx@pex@run #1
  { \lx_item_main: #1 \lx_example_end: }
\ExplSyntaxOff
\NewDocumentCommand \pa { } { \lx_sub_push: }
\NewDocumentCommand \pb { } { \lx_sub_next: }
\makeatother
```

Wait — `\lx_example_begin:` belongs inside the continuation with the rest;
follow the ordering of `\lx@run@ex` exactly (begin, then item, then body,
then end). The body must exercise: a plain example, a judgment
(`\pex *Sentence`), a sub-level with two items, and a custom label via
`\lx_item_main:n`.

Wiring (read the header comment of `tests/runtests.py` first):
- The suite refuses to run with an unwired case file (exit 2): add a
  `frontend` entry to `ASSERTIONS`. Model the assertions on the `numbering`
  and `judgments` entries — assert the rendered geometry (label positions,
  judgment hang, sub-item indent), not mere compilation.
- Use `_preamble-tagged.tex` so the case also exercises the tagging path of
  the funnel; add a structure assertion in the style of
  `struct_label_depths` if the suite exposes one per-case.
- **Mutation check** (the suite is mutation-tested; keep it that way): for
  each new assertion, make a temporary breaking change (e.g. `\let`
  `\lx_sub_push:` to `\lx_sub_next:`) and confirm the assertion FAILS, then
  revert. Record in the commit message which mutation kills which assertion.

Run the full suite on all three engines. Commit.

## Stage 5 — Documentation

1. `linguexx-doc.tex`: new section "For front-end authors" containing:
   - the two protocols with a table of public names and one-line semantics;
   - the worked `\pex` mini front-end from Stage 4;
   - the **four load-bearing invariants**, stated as binding contract:
     1. The item label is fixed BEFORE the list opens (`[legacy]` sizes the
        label box from it — `linguexx.sty:994-995`).
     2. Grouping is the depth stack: sub-level depth is only ever advanced
        inside the group opened for that level; never advance it globally.
     3. No extra TeX group may wrap a whole example (it breaks tagged
        text-unit accounting in footnotes — `linguexx.sty:932-936`).
     4. Every list open/close goes through `\lx_list_open:n` /
        `\lx_list_close:` (environment form + tagging attribute patch).
   - a stability note: `\lx_...` names are the contract; `\lx@...` and
     `\__lx_...` names are private and may change without notice.
2. Build the manual with **lualatex only** (it errors under pdflatex by
   design; do not "fix" that, and do not add fontspec — see CLAUDE.md).
   Render the new pages with `pdftoppm` and inspect them.
3. `CHANGELOG.md`: entry under the open 1.2 section describing the new
   public API, explicitly stating "no behavior change".

## Stage 6 — Final verification and delivery checklist

In order, all mandatory:

1. `python3 tests/runtests.py` — all cases, all three engines, green.
2. Rebuild `examples/ua-demo.pdf` (lualatex, to convergence);
   `verapdf examples/ua-demo.pdf` passes. Remember: an UNCONVERGED file
   fails veraPDF exactly like a real regression — `ua` needs 3 passes under
   pdflatex/xelatex (`PASSES` in runtests.py); don't misdiagnose.
3. `pdfinfo -struct-text examples/ua-demo.pdf` — diff against
   `BASE/ua-demo.struct`: must be identical.
4. `pdftoppm` checksums of all three example PDFs — identical to `BASE/`.
   If any differ: render both, inspect visually, and treat as a defect in
   the refactor until proven otherwise.
5. Visually inspect at least one rendered page containing a brace
   (`\altn`): position AND curvature (ascending path = opening `{`).
6. Manual builds clean under lualatex; new section renders correctly.
7. `git log --oneline` shows one commit per stage; working tree clean.

## Appendix — traps, in decreasing order of bite

1. **`\lx@bodyend` is a placed token**, not just a macro: `\lx@run@ex` puts
   it after the body, and `\z.` early-termination relies on it executing as
   cleanup. Alias it; never inline, move, or duplicate it.
2. **Catcodes.** Every `\lx_...` definition/alias must sit inside
   `\ExplSyntaxOn`/`Off`; `@`-names additionally need the package's own
   catcode regime (you are inside the .sty, so `@` is already a letter).
   Put alias blocks directly after the original so the target exists.
3. **`\protected` matters**: the letter hooks and several expl3 functions
   are protected for hyperref's `\edef`-expansion of bookmarks
   (`linguexx.sty:1045-1051`). `\cs_new_eq:NN` preserves protection;
   re-`\def`-ing does not. Alias, don't redefine.
4. **No variants of `\tag_...` kernel commands** (`linguexx.sty:539-543`).
5. **`\lx@kernel@item`** is captured at load AND `\AtBeginDocument`
   (`linguexx.sty:1015-1016`) because xlist rebinds `\item` locally. Leave
   both capture sites alone.
6. **The `\iflx@lazy` letter machinery** (`linguexx.sty:1117-1166`) is
   syntax-front-end territory, not core: do not give it public names. A
   front-end that wants dot-letter-like shorthands defines its own.
7. **`\lx@guesslabel`** (`linguexx.sty:924-930`) is used by `exe` to size a
   list opened before its first item. It is a candidate public name
   (`\lx_label_guess:`) only if the Stage 4 front-end turns out to need it;
   otherwise leave it private — smallest sufficient API wins.
8. **Suite integrity is enforced**: an unwired case file, a stale
   `KNOWN_XFAIL`/`PASSES` key, or a passing XFAIL is a hard error (exit 2).
   Read the runtests.py header before adding the test case.
