# Changelog

All notable changes to `linguexx`. Versions refer to the `\ProvidesPackage`
version string.

## 1.0
- `\alt`/`\lxAlt` renamed to `\altn`/`\lxAltn`. `\alt` is claimed by
  `beamer`, `glossaries-extra`, `revtex`/`revsymb`, `tex4ht`,
  `mdwtools/syntax`, and several document classes; `\altn` is unclaimed by
  anything in TeX Live 2026. `\altg`/`\lxAltg` are unaffected -- no known
  collisions, so the name stays. As before, if some other package already
  owns `\altn`, `linguexx` leaves it alone and only `\lxAltn` is available.
  **Breaking change**: documents using `\alt` must switch to `\altn`.

## 0.14
- `\altg`/`\lxAltg` return, rebuilt in text mode as a glossed paradigm of
  alternatives. Inside an interlinear gloss it is written **twice** -- once in
  the object line with the object words, once in the gloss line with their
  glosses:

  ```latex
  \exg. Die \altg{Frau}{Socke}{Maus}{Tonne} ist da.\\
        The.\lpzg{sg} \altg{woman.\lpzg{sg}}{sock.\lpzg{sg}}%
          {mouse.\lpzg{sg}}{ton.\lpzg{sg}} is.\lpzg{prs} there.\\
  ```

  The two calls occupy the two tiers of one gloss column and assemble a
  single paradigm: object stack on the left, gloss stack to its right
  (offset by `\AltgColSep`), braced on BOTH sides, centred on the
  object/gloss midline -- with four alternatives, rows 2 and 3 ride the
  object and gloss lines and rows 1 and 4 protrude symmetrically, with
  surrounding lines kept clear. The example number stays on the object
  baseline. Both calls must list the same number of alternatives (package
  error otherwise), and no spaces may separate the brace groups (break long
  calls with `%`). Outside a gloss, a single `\altg` sets one both-braced
  stack on the current baseline. Under tagging each call is wrapped in a
  `Span` carrying its own spoken `/Alt` ("Frau, Socke, Maus, or Tonne" /
  "woman.singular, ..."); simple `\lpzg` keys are expanded from the Leipzig
  table in the spoken form, compound or unknown keys pass through verbatim,
  and inside the printed stacks `\lpzg` reduces to plain small caps. No math
  anywhere, so the PDF/UA-2 `Formula`-in-`Span` failure that forced the 0.12
  removal cannot recur. Settings: `\AltgColSep` (default `1.2em`),
  `\AltgTransFont` (gloss stack font, default `\normalfont`); the braces
  share `\AltBraceWidth`/`\AltBraceAmplitude`/`\AltBraceSep` with `\alt`.
  Under beamer or any class that owns `\altg`, use `\lxAltg`.
- `\alt` closes its stack with a right brace again, restoring the pre-0.13
  math-mode look (`\left\{ ... \right\}`); v0.13 drew the left brace only.
- Brace direction fixed: the TikZ `brace` decoration bulges according to the
  path direction, and the v0.13 path drew the brace mirrored (a closing
  shape on the left of the stack). Both `\alt` and `\altg` braces now curve
  the right way.

## 0.13
- `\alt` rebuilt in text mode: a `tabular` stack with a TikZ-drawn brace, no
  math and no `amsmath`. The alternatives are now ordinary tagged text, and
  under tagging the stack is wrapped in a `Span` carrying a spoken `/Alt`
  ("A, B, or C", built with `\text_purify:n` so formatting is stripped for
  speech). Brace tunables: `\AltBraceWidth`, `\AltBraceAmplitude`,
  `\AltBraceSep`, `\AltBraceRaise`. Dependency change: `-amsmath`, `+graphicx`,
  `+tikz`.

## 0.12
- Remove `\altg`/`\lxAltg` (alternatives with translations) and its
  `\AltgColSep`/`\AltgTransFont` settings. `\alt` is unaffected.

## 0.11
- Revert the 0.10 `\alt`/`\altg` tagging. Wrapping the alternatives formula in a
  `Span` carrying `/Alt` is invalid under PDF/UA-2 when the formula begins an
  example (a `Span` may not contain the `Part`/`P` the math tagging then builds),
  and veraPDF rejects it. `\alt`/`\altg` revert to the plain formula, which
  validates; a spoken form needs the "positioning text" math interface and is
  deferred.

## 0.10 (reverted in 0.11)
- `\alt` and `\altg` (stacked alternatives, set as math arrays) now carry a
  spoken alternate text under tagging -- "alternatively: the cat, a dog, or the
  bird" -- so a screen reader no longer reads the braces and array as a jumble;
  `\altg` keeps each translation with its alternative.

## 0.9
- `\lpzg` accepts a whole compound gloss label in one call: `\lpzg{3sg.pst}`
  splits on periods, peels a leading person digit, expands each piece and joins
  them into one `/E` ("third person singular past").
- `\GlossTierLang` is now scoped: a document-wide default when set in the
  preamble or body, overridable for a single example by issuing it inside that
  example (it reverts afterwards).

## 0.8
- PDF tagging, objective 6: Leipzig gloss abbreviations. `\lpzg{sg}` sets the
  abbreviation in small caps and, under tagging, records its expansion as the
  PDF `/E` (expansion text), so a screen reader announces "singular" while print
  and copy-paste keep SG. Built-in standard Leipzig table (keyed by short form);
  `\SetLeipzig{key}{expansion}` extends or overrides; unknown keys print with no
  expansion. Self-contained (no dependency on the `leipzig` package).

## 0.7
- PDF tagging, objective 5: language of a gloss tier. `\GlossTierLang{tier}{code}`
  records a language code; under tagging each word of that tier is wrapped in a
  span carrying `/Lang`, so the object language is pronounced with its own
  phonetics.

## 0.6
- PDF tagging, objective 4: interlinear glosses as structure. Each gloss column
  (an object word with its aligned glosses) is grouped as a span, so a screen
  reader reads the gloss word-bundle by word-bundle in the correct order rather
  than as loose text.

## 0.5
- Fix an invalid PDF attribute value introduced in 0.3: ordered example lists
  emitted `/ListNumbering /Ordered`, which is not a spec-valid value and is
  rejected by validators. Each level now uses a valid class of its own
  (`/Decimal`, `/LowerAlpha`, `/LowerRoman`), with a safe fallback to `/None`.

## 0.4
- PDF tagging, objective 3: spoken forms for judgment marks. Under tagging a
  mark is wrapped in a span carrying `/Alt`, so it is announced by meaning
  ("ungrammatical") rather than by glyph. Defaults for `* ? ?? ?* # %`;
  `\DeclareJudgment[spoken=…]` and `\SetJudgmentSpoken` to customise.

## 0.3
- PDF tagging, objective 2: examples as proper list structure. Examples already
  produced `L → LI → Lbl → LBody` with nested sub-levels (they are real lists);
  this marked them as ordered. (The value used here was corrected in 0.5.)

## 0.2
- PDF tagging, objective 1: tagging-safety under `\DocumentMetadata`. Valid
  structure tree on all three engines, including examples inside footnotes.
  Lists opened/closed through the environment interface; no extra group around
  the example; explicit paragraph-continuation and text-unit cleanup.
- Label alignment under tagging: labels are set flush left in a full-width box so
  the tagged list code does not re-box them flush right.

## 0.1
- `[legacy]` option reproducing `linguex` geometry and conventions exactly;
  orthogonal to the syntax options, so combinable (e.g. `[legacy,gb4e]`).
- Default ("lazy") mode: empty `\firstrefdash` (references print "(3a)", not
  "(3-a)"); `\resetExdefaults` restores the current mode's lengths.

## Earlier
- Evolution from `linguex-patch.sty` into a standalone `expl3`-based package,
  removing dependencies on `linguex` / `cgloss4e` / `xspace`; complete manual and
  regression suite across pdfLaTeX, XeLaTeX and LuaLaTeX.
