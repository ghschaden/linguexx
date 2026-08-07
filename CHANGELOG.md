# Changelog

All notable changes to `linguexx`. Versions refer to the `\ProvidesPackage`
version string.

## 1.2
- New: a documented API for building a syntax front-end or a geometry mode
  on this package's machinery, without touching its internals. The seam was
  already there -- the dot syntax and the `exe`/`xlist` environments are
  thin layers over one shared engine, and neither the numbering, the label
  boxes, the judgments, the glossing nor the tagging knows which called it.
  What is new is that the seam has names: `\lx_example_begin:`,
  `\lx_body_collect:N`, the `\lx_item_...` family, `\lx_sub_push:`,
  `\lx_judgment_...`, the list funnel and the tagged-Span helpers
  (Protocol A), and `\lx_mode_new:nNNNN` / `\lx_mode_select:n` for a
  geometry beside `[legacy]` (Protocol B). Documented in the manual's new
  §11, including the four invariants a front-end has to respect, and
  exercised by `tests/frontend.tex`, which builds a working front-end out
  of the public names alone and is validated with veraPDF.

  **No behaviour changes.** Everything user-facing is what it was: the
  public names are aliases of the internals they expose, the `[legacy]`
  branch became a named mode selected the same way, and the three example
  documents rebuild to byte-identical pages with an identical structure
  tree. Nothing in an existing document needs to change, and no internal
  spelled `\lx@...` was renamed or removed -- but those remain private and
  unsupported, which is the point of publishing the others.
- `\altn`'s spoken `/Alt` now expands a Leipzig abbreviation, as `\altg`'s
  already did: `\altn{a \lpzg{pl} of cats}{a dog}` is announced as "a plural
  of cats or a dog" rather than "a pl of cats or a dog". Only the spoken form
  changes -- the stack still prints the small-cap abbreviation, and that
  abbreviation still carries its own `/E` expansion inside the stack (unlike
  in an `\altg` stack, which sets `\lpzg` plain). Simple keys only, as in
  `\altg`: a compound or unknown key is spoken as printed.
- Fix: `\z.` is now usable inside an `exe` batch. Mixing the syntaxes is
  documented, so an `\a.` inside `exe` legitimately opens a sub-level -- but
  `\z.`, the only thing that could close it again, raised "`\z.` outside an
  example": the command was gated on a flag only the dot syntax sets. It is
  now gated on the open sub-level itself, so `\a. ... \z.` inside a batch
  returns to the main level and the next `\ex` is a main-level example
  again. (With the `\z.` omitted that `\ex` is still silently demoted to a
  sub-item: `\ex` continues at the *current* level, which is the rule
  `xlist` documents, and `\z.` is now the escape.) Only the branch that ends
  the example stays dot-syntax-only; a `\z.` at the main level of a batch is
  a package error saying to end the batch with `\end{exe}`.
- Fix: hyperref anchors for sub-examples in footnotes no longer collide with
  main-text ones. `\theSubExNo` (the printed label) branches on
  `\if@noftnote`, but `\theHSubExNo`/`\theHSubSubExNo` (the anchors) built
  their name from `ExNo` unconditionally, so a sub-example "a" in a footnote
  and one under main example 1 both claimed `lxex.1.a`. hyperref keeps the
  first destination of a name and drops the rest, so a `\ref` to the
  footnote sub-example linked to the main-text one -- a wrong *link*, never
  a wrong number, which is why it stayed invisible. Footnote sub-examples
  now anchor on the footnote series, `lxfnex.<FnExNo>.<letter>` and
  `lxfnex.<FnExNo>.<letter>.<n>`, matching `\theHFnExNo`. Main-text anchors
  are unchanged.
- Fix: a stray `\a.` in prose, with no example of either kind open, is now a
  package error naming itself. It used to open a list and a `\begingroup`
  that nothing ever closed, and the document died much later with
  "`\begin{list} ended by \end{document}`" -- a message naming neither `\a.`
  nor the line it stood on. `\a.` inside an `exe` batch is unaffected: it
  reaches the same code path legitimately, and stays legal.
- Fix: a trailing or doubled period in a `\lpzg` label no longer records an
  empty abbreviation. `\lpzg{sg.}` splits into `sg` and an empty piece, and
  the empty piece was recorded as a used key like any other, so `\lpzgcheck`
  reported "No expansion known for" nothing at all -- a warning naming a key
  the author could not find in the source -- and the `/E` expansion carried
  a trailing space. Blank segments are now skipped; the real pieces beside
  them are recorded exactly as before.

## 1.1
- `\lpzglist`: the list of the abbreviations the document actually uses, each
  with its full form. Every label passed to `\lpzg` is recorded piece by piece
  (`\lpzg{3sg.pst}` contributes `3`, `sg` and `pst`), written to the `.aux`,
  and reported by `\lpzglist` wherever it stands -- in the front matter as
  readily as at the end; when the list is a run behind, a rerun is requested.
  `\lpzgadd{erg,abs}` registers abbreviations used outside `\lpzg`.
  Abbreviations with no known expansion are omitted with a warning naming them
  (`unexplained=keep` lists them unexplained instead). Customisation, per list
  via `\lpzglist[...]` or document-wide via `\lpzglistsetup{...}`: `style`
  (`list`/`inline`), `sort`, `include` (`used`/`all`), `ignore`, `add`,
  `unexplained`, `title`, `titlestyle`, `sep`, `itemsep`, and `format` (the
  one-shot form of `\lpzglistentry`, `#1` the abbreviation, `#2` its full
  form). Under tagging the default style is a real tagged list (`L → LI → Lbl
  → LBody`) whose labels keep their `/E` expansion and stay flush left;
  verified with veraPDF on `examples/ua-demo`. `\lpzg` inside an `\altg` stack,
  which prints plain, now counts as used as well.
- Phantom bracket alignment for interlinear glosses (opt-in, off by default).
  When an object word opens with a run of brackets, parentheses or judgment
  marks, the gloss word below it can be padded by a `\phantom` of that run --
  set in the object-line font -- so its first real glyph sits under the object
  word's first real glyph rather than under the mark. Enable with the package
  option `phantomalign` or `\GlossPhantomAlign` (`\GlossPhantomAlignOff` to
  scope it); `\GlossPhantomChars{...}` sets the leading characters that count
  (default `*?#%([<`). For material the automatic scan cannot see (a
  macro-wrapped bracket) or a hand-picked target, `\GlossPhantom{material}`
  is a manual override: placed at the front of a gloss word it pads it by an
  invisible box the width of `material`, set in the object-line font. The
  phantom ships no ink and no marked content, so PDF/UA tagging is unchanged
  (verified with veraPDF on `examples/ua-demo` and on a `\GlossPhantom`
  build). Alignment survives a size change of the gloss tier (e.g.
  `\footnotesize`). `\altg` alternative columns are not covered.
- Fix: the sub-example letters and the kernel accent commands `\b`, `\c`,
  `\d` now coexist, **everywhere, including inside the same example**:

  ```latex
  \ex. \a. Fran\c cois est fatigu\'ee.   % \c = cedilla
       \b. \c Ca c'est chiant.           % \b = sub-example, \c = cedilla
  ```

  Each letter dispatches on what follows it: a period is the sub-example
  command, anything else (`{`, a letter, a space) is the accent, i.e.
  whatever the letter meant before linguexx touched it. `\c{c}` and an
  inputenc-decomposed "ç" (literally `\c c`) both take the accent branch.
  Previously, under `[lazy]` (the default), all six of `\a`-`\f` were
  redefined globally and permanently, so `\c{c}` or "ç" anywhere in the
  document raised "Use of `\c` doesn't match its definition", and in a
  hyperref `\section` title the accent was dropped *silently* from both the
  printed heading and the PDF outline entry. The hooks are `\protected`, so
  hyperref's `\edef` over a title leaves them alone instead of running their
  lookahead; only `\a` is held globally (it must be able to *open* a level,
  and it is no accent at all), while `\b`-`\f` are hooked just where a
  sub-level is reachable. Under `[gb4e]` alone nothing is redefined, as
  documented. `\e`/`\f` without a period, which the kernel does not define,
  now give a named package error instead of "undefined control sequence".
- Fix: `\end{exe}` now closes any sub-level opened by an `\a.` inside the
  batch (`\lx@closesubs`). It previously closed only the main list and
  leaked `\lx@subpush`'s `\begingroup`, leaving `\lx@subdepth` stuck at the
  sub-level for the rest of the document.
- `\glt` (the free translation) gains two hooks, both opt-in and both
  leaving the default output and the default tag tree byte-for-byte as they
  were:
  - `\GlossTransStyle` styles the translation. It is a *declaration*
    (`\renewcommand\GlossTransStyle{\itshape}`), not a one-argument command
    like `\GlossTierFont`, because the translation is delimited by the end of
    its paragraph rather than by braces; a declaration also scopes itself to
    the example, so it neither reaches the gloss tiers above the `\glt` nor
    leaks past the end of the example.
  - `\GlossTransLang{code}` marks the translation's language, as
    `\GlossTierLang` does for a gloss tier: under tagging the translation is
    wrapped in a `Span` carrying `/Lang`, so a screen reader pronounces it
    correctly. This is not redundant with babel — on TL2026,
    `\foreignlanguage` inside the translation leaves no `/Lang` in the
    structure tree at all, so there was previously no way to mark a
    translation whose language differs from the document's, which is the
    normal case when writing in one language and glossing into another.
    Verified with veraPDF on `examples/ua-demo`.
- Fix: `\sublabel` records the label of the level it is used at. It always
  recorded the letter counter, so at the roman level every sub-sub-example
  under one letter stored that same letter, and `\refrange` over them printed
  `(1b-i--b)` instead of `(1b-i--iii)` — a silently wrong reference, since
  nothing about it raised an error. On a main-level example it now records
  nothing and the range closes with a full `\pref` (it used to expand
  `\alph{0}`, i.e. "Counter too large"). `\ref` to a sub-sub-example went
  through a different path and was always correct.
- Fix: an `\altg` in a gloss column with no partner is now a package error
  instead of overlapping text. The two calls of a paradigm are paired by a
  single global toggle (object call sets it, gloss call clears it), so a
  column that announced a stack without completing it left the toggle set
  and gave *every later* `\altg` in that gloss the opposite role — object
  stacks were typeset with the gloss shape, raised half a baseline and
  indented, on top of their neighbours. A `\glll` carrying an `\altg` in a
  third tier hit the same thing, the third call being read as a fresh object
  call. Both compiled silently. Alternatives in three tiers remain
  unsupported; that would be a feature, not a fix.
- The suite can now assert that a case *fails* (`EXPECT_ERROR`), so a package
  error is guarded like any rendering: `tests/altg-unpaired.tex` fails if the
  check stops firing, and the valid `altg` case fails if it starts firing
  when it should not.
- `\lpzgcheck{...}`: consistency checks on the gloss abbreviations
  themselves. Until now the only report was a side effect of building a
  list, so a document that never called `\lpzglist` could mistype
  `\lpzg{pres}` for `\lpzg{prs}` and get PRES in small caps in complete
  silence. `unknown` (**on by default**) reports every abbreviation used
  with no known expansion, at the end of the document, list or no list;
  `ignore={...}` exempts ones deliberately left unexplained. `unused` (off
  by default) reports the reverse — declared with `\SetLeipzig` and never
  used — and considers only your own declarations, not the ~100 built-ins.
  A key a `\lpzglist` has already reported is not reported twice.
- Fix: `\DeclareJudgment` rejects a first mandatory argument that is not a
  single command, instead of hanging. That argument is the command being
  *defined* and the second is the mark it prints — an order easy to read the
  wrong way round, and `\DeclareRobustCommand` takes the first token of
  whatever it is handed, so `\DeclareJudgment{\%\%}{\%\%}` quietly
  redefined `\%`, which the judgment scanner peeks for, and the run then
  spun forever with nothing in the log to say why.
- Test coverage for the previously untested public surface: judgment
  customisation including the `/Alt` it produces under tagging
  (`tests/judgments.tex`), its misuse error (`tests/judgment-badarg.tex`),
  and the numbering parameters at non-default values together with every
  relative-reference command no other case called — `\NNext`, `\TextNext`,
  `\Refrange` and the four `\p*` twins (`tests/customise.tex`). All were
  correct; this is regression insurance, not repair. `tests/lpzgsetup.tex`
  adds the document-wide half of the abbreviation-list interface —
  `\lpzglistsetup`, and `\lpzglisttitle`/`\lpzglistentry` redefined
  wholesale — including that a per-list key beats a document-wide one
  without disturbing the rest of it. Still uncovered: the `\AltBrace*`,
  `\AltgColSep` and `\AltgTransFont` visual tunables.
- The suite caps each engine run (`CASE_TIMEOUT`). A TeX loop ignores
  `-interaction=nonstopmode` and spins with an empty log, so one bad case
  hung the whole suite rather than failing it.
- `\cref` works on examples when `cleveref` is loaded. It used to print
  `?? (1)` — cleveref's marker for a counter it has no name for. The names
  are declared *empty*, so `\cref` prints the number alone, `(1)` and
  `(1a)`, which is how examples are referred to in prose; what it adds over
  `\ref` is cleveref's list and range handling, `\cref{a,b}` giving
  `(1) and (2)`. A `\crefname` the document sets itself is left alone —
  linguexx declares its defaults at `\begin{document}`, after the preamble,
  so without that guard it would silently overwrite the author's choice.
- The manual documents the transliteration extraction trap (§9.3) and is now
  built with **lualatex**, refusing to build under pdflatex. It contains the
  affected characters in the table that explains them, so built with pdflatex
  it exhibited the defect it was describing — copying the first column out of
  the PDF gave you the second. Verified while writing it: tagging does *not*
  repair this (the mapping is per glyph, and there are two glyphs where one
  was meant), and veraPDF passes such a file on all three profiles — so the
  only authoritative PDF/UA check gives a clean bill to a document a screen
  reader misreads.
- `examples/ua-demo.tex` loads `fontenc` (T1 under pdfLaTeX only) and now
  contains an accented example written as literal UTF-8, so the
  accessibility demo exercises the input path the `ç` bug lived on — it
  previously had no non-ASCII character in it at all. Recorded in the file
  itself, because it is easy to assume otherwise: the text layer is correct
  *without* `fontenc` too, since the tagging machinery supplies the
  `ToUnicode` mapping, and veraPDF passes either way. T1 is there as correct
  practice for accented input, not as a fix for a demonstrated defect.
- Fix: **linguexx could not be used with French `babel` at all.** `babel`'s
  French option defines `\fg`, the closing guillemet of `\og … \fg`, and
  linguexx claimed the same name for its glossed shorthand `\fg.` — fatally,
  in both load orders. With linguexx first, `babel`'s own `\newcommand\fg`
  raised "Command `\fg` already defined" and the document did not build.
  With `babel` first, linguexx silently overwrote it and **every closing
  guillemet in the document disappeared**, with no error at all.
  The dot shorthands (`\z.`, `\exg.`, `\ag.`–`\fg.`) are now claimed at
  `\begin{document}` and only if the name is still free. Both halves are
  needed and fix different orders: deferring lets `babel` define `\fg`
  first, and the guard stops linguexx overwriting it afterwards. In a French
  document `\fg.` is therefore unavailable — write `\f.` then `\gll` — and
  the `.log` records why. `\f.` itself is unaffected; `\fg` and `\f` are
  different control sequences. The same guard hands back any shorthand name
  you have defined yourself, `\eg` being the common case.
- The manual's "Notes and limitations" no longer claims the `\b`, `\c`, `\d`
  accents are unavailable — that stopped being true when the letters were
  made to dispatch on a following period, and the note was left promising
  the old broken behaviour.
- Regression coverage for the two `babel` hazards, in both load orders
  (`tests/babel-fr.tex`, `tests/babel-fr-order.tex`, `tests/babel-de.tex`):
  French makes `?` `!` `:` `;` **active**, and `?` is a judgment mark — that
  works only because the scanner uses `\peek_charcode`, which ignores
  catcode, so switching it to `\peek_meaning` would look like a tidy-up and
  silently stop judgments working in French. German's active `"` shorthand
  is checked through the body collector, the gloss tiers and `\altn`. Both
  orders are needed: `\AtBeginDocument` hooks run in registration order, so
  with linguexx loaded first `babel` re-establishes `\fg` afterwards and
  masks a clobber that sticks in the other order.
- Regression coverage for literal UTF-8 input, which is how the `ç` bug
  escaped: every case wrote its accents the way the manual does (`\c c`,
  `\"a`), and none typed what a user types. `tests/utf8.tex` puts raw UTF-8
  in every example position — body collector, judgment scanner, gloss tiers,
  `\glt`, `\altn`/`\altg`, `\exsource` — under all three engines, with the
  languages chosen for the accent command each exercises rather than for
  prestige. Restoring the old letter-clobbering makes it fail under pdflatex
  with the original error while xe/lua still pass, i.e. it reproduces the
  bug's exact signature. No new fault was found: raw multi-byte input
  survives every position already.
- `tests/utf8-unicode.tex` covers what pdflatex cannot represent at all —
  Hittite `ḫ`, Semitic `ʾ ʿ ḏ ṯ ẓ`, Vietnamese stacked vowels, IPA — under
  the Unicode engines only, via a new `ENGINES_FOR` in the suite. Recorded
  there too, because it is silent and matters for accessibility: pdflatex
  *typesets* Indic dot-below (`ḍ ṇ ṭ ṣ ḥ`) and Latvian comma-below
  (`ģ ķ ļ ņ`) correctly but does not *extract* them — copy-paste and screen
  readers get `kr.s.n.ah.` and `gimen , u`. A Unicode engine is needed for
  those scripts to be accessible, not merely to look right.
- The suite now runs veraPDF itself, on a new PDF/UA-2 case (`tests/ua.tex`),
  so the release gate that used to be a manual step before delivering is
  enforced on every run and under all three engines. This is what catches a
  structure element opened at the *wrong moment* — marked content straddling
  its parent, which veraPDF rejects (`<Span> contains <P>`) and which no
  geometric or flat-structure assertion can see. Two supporting changes:
  cases can now declare how many LaTeX passes they need (`PASSES`), because
  PDF/UA validity does not converge until the third run under pdflatex and
  xelatex, and an unconverged file fails veraPDF exactly like a real
  regression would; and the integrity check also rejects a stale `PASSES`
  key. veraPDF is now a hard requirement of the suite.
- The suite gained a structure-*nesting* check (`struct_label_depths`).
  Every flat structure assertion, and veraPDF itself, accepts an inline
  element that is opened and never closed: it stays spec-valid while
  silently reparenting the rest of the document underneath itself. Top-level
  example numbers are siblings, so they must all sit at one depth in the
  tree; if anything leaks, the ones after it drop a level and the check
  fires.
- Regression coverage for both of the above (`tests/cedilla.tex`,
  `tests/cedilla-gb4e.tex`), including the hyperref-title cases and the
  accent-restoration points after each example syntax; mutation-checked.
  Verified with veraPDF on `examples/ua-demo`.

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
