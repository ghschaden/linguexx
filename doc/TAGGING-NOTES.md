# linguexx and PDF tagging (accessibility): objective 1 — tagging-safety

**Goal.** A document that turns on the LaTeX tagging code
(`\DocumentMetadata{... testphase={tagpdf,text,sec,block}}`) and loads
linguexx must compile and produce a **valid, uncorrupted structure
tree** — the precondition for everything else (real tagging, PDF/UA).
This is the level Alan Munn expected to be unreachable for a
linguex-style package. It is reached here for linguexx v0.2, on
lualatex, pdflatex and xelatex.

This is *tagging-safety*, not full semantic tagging: examples currently
inherit generic list structure (`L`/`LI`/`Lbl`/`LBody`) from the kernel,
which is correct and standards-valid. Turning that into example-,
judgment- and gloss-specific structure with language tags is later work.

## What broke, and why

Two failure modes appeared under the 2023 `latex-lab` "block" testphase:

1. **List interface.** linguexx opened example lists with the *command*
   pair `\list ... \endlist`. The tagged block code keys part of its
   state restoration to the *environment* hooks of `list`, which never
   fire in command form. Fix: funnel every open/close through
   `\begin{list}`/`\end{list}`, via one internal pair
   (`\lx@openlist`/`\lx@closelist`). Geometry is unchanged.

2. **The example's outer group + the paragraph-continuation dance.**
   linguexx wrapped each example in an extra `\begingroup…\endgroup`.
   A `list` inside an extra group inside a footnote desynchronises
   tagpdf's *text-unit* bookkeeping (`\g__tag_para_main_(begin|end)_int`),
   because the list's `\end` arms the kernel's "continue the paragraph"
   mechanism (`@endpe` + a one-shot `\everypar`) and defers a structure
   close to it — but linguexx's semantics *cancel* that continuation (a
   blank line after an example starts a new, indented paragraph).
   Cancelling only one half of the mechanism left the structure element
   open.

   Fix: drop the outer group entirely (the list's own group already
   scopes everything), and make cleanup explicit and coherent:
   - save/restore `\@currentlabel`/`\@currentHref` (so a trailing
     `\label` still refers to the enclosing context — this is what the
     group used to do);
   - clear **both** halves of the continuation (`\everypar{}` +
     `\@endpefalse`);
   - if the block layer had opened a deferred text-unit element, close
     it now, using tagpdf's own operations
     (`\__tag_gincr_para_main_end_int:` + `\tag_struct_end:`),
     existence-guarded so it is a no-op without active tagging or under
     a different tagpdf.

3. **Label alignment.** linguexx set sub-labels flush left with a
   trailing `\hfil` in a natural-width label box. The tagged block code
   re-boxes any label narrower than `\labelwidth` to `\labelwidth` using
   its own alignment (`label-align`, default **right**), which silently
   shifted `(1)`, `a.`, `b.`, ... right toward their text. Fix: set the
   label in a box of exactly `\labelwidth` with content flush left
   (`\makebox[\labelwidth][l]{...}`); a label that already fills
   `\labelwidth` is left untouched by the re-boxing. Untagged output is
   byte-identical; tagged output now matches it (verified: sub-label `a.`
   sits at the main-example text margin, offset 0.00pt, on all engines).

## Verified

- `analyze.py` (bundled) walks the structure tree and scans every
  content stream: **0 text operations outside marked content** on all
  three engines, for plain examples, sub-levels, judgments, glosses,
  `alt`/`altg`, `exsource`, `exe`/`xlist`, page-straddling examples,
  examples in footnotes, and `[legacy]` mode.
- Geometry is untouched: a tagged/untagged diff shows identical text
  positions (only the number's x-origin shifts, by design of the
  tagging code, not ours).
- Regression: new `tagged` case in the suite (halts on any tagpdf
  accounting error); full suite 212/213 green on all three engines
  (the one known failure is a pdftotext token-merging artifact,
  unrelated).


## Objective 2 — examples as proper (ordered) list structure

Because linguexx builds examples from genuine `\begin{list}` environments,
the tagged structure tree already nests

    list (L) > LI > Lbl ("(1)") + LBody
                              LBody > ... > list (L) > LI > Lbl ("a.") + LBody
                                                                 ...> list (L) ("i.")

i.e. `L > LI > Lbl + LBody`, with letter and roman sub-levels as **nested
`L`s** inside the parent `LBody`. That much came for free from objective 1's
choice to use real lists.

What v0.3 adds is the missing *semantics*: an example list is **ordered**
(numbered `(1)`, lettered `a.`, roman `i.`), but the block code, seeing a
`\begin{list}` with an empty default label, tagged it with the label-less
class (`/ListNumbering/None`). linguexx gives each example list a valid, per-level `/ListNumbering`:
`/Decimal` for the numbered level, `/LowerAlpha` for letters, `/LowerRoman`
for romans. (An earlier attempt routed them through the block code's
`enumerate` class, whose value `/Ordered` is **not** a spec-valid
`/ListNumbering` and is rejected by validators such as poppler's
`pdfinfo`; the per-level classes fix that. If the tagged-list internal is
ever unavailable the lists fall back to the default valid `/None`.) Verified on all three engines for
main examples, letter and roman sub-levels, glosses, `exe`/`xlist`
environments, and footnote examples: every example list carries a valid per-level ordered
`/ListNumbering`, and `LI`/`Lbl`/`LBody` are present and correctly nested. The
`tagged` regression case asserts this (`>=2` nested `L`s; `LI`/`Lbl`/`LBody`
present; every example list ordered).

Still generic in the sense of objective 4: the *interior* of a gloss (its
word-by-word alignment) is not yet a semantic structure — it currently sits
as text inside the `LBody`. Judgments likewise are not yet given spoken
alternatives (objective 3).


## Objective 3 — spoken forms for judgment marks

A judgment mark is a meaningful symbol a screen reader would otherwise
read literally ("asterisk"). Under active tagging, `\jdg` now wraps the
mark in a `Span` structure element carrying `/Alt` (UTF-16), so it is
announced by meaning. `\g_lx_judge_alt_prop` maps a mark string to a
phrase, with defaults `* -> ungrammatical`, `? -> questionable`,
`?? -> highly questionable`, `?* -> extremely degraded`,
`# -> infelicitous`, `% -> grammatical for some speakers`. The map is
consulted for both scanned leading marks (`\ex. *...`) and named ones.

`\DeclareJudgment[spoken=<phrase>]{\cmd}{<mark>}` names a mark and, if a
phrase is given, registers it for `<mark>` too (so the scanned form is
announced identically). `\SetJudgmentSpoken{<mark>}{<phrase>}` sets a form
without naming a command, and `\jdg[<phrase>]{<mark>}` carries a one-off
form. All of this is tag-guarded: printed output is unchanged and nothing
happens without active tagging. Verified: `*`, `?`, `#`, a `%%`-based
named judgment, and a sub-level `??` each emit a `Span` with the correct
decoded `/Alt`; the `tagged` regression case asserts the `*` mark's
spoken alt.


## Enabling tagging (which \DocumentMetadata line)

The invocation has changed as the tagging project matured:

- **TeX Live 2025-11 and newer:** `\DocumentMetadata{lang=en,tagging=on}`
  (recommended).
- **TeX Live ~2023 through 2026:** `\DocumentMetadata{lang=en,testphase={phase-III}}`
  is portable and selects the current comprehensive tagging; it also works
  on the newest releases.
- **Do not** use the older module list `testphase={tagpdf,text,sec,block}`:
  `tagpdf` is now only an alias for the intermediate phase-II, and the
  individual module names (`text`, `sec`) were reorganised, so on recent
  TeX Live that line loads only part of the machinery (symptom: mostly
  tagged output with a stray untagged operator, or an incomplete tree).

All three objectives above were re-verified under `testphase={phase-III}`:
valid tree incl. footnote examples, ordered `enumerate` example lists with
`LI`/`Lbl`/`LBody`, and judgment `/Alt` spoken forms. The internal
compensations (objective 1's text-unit/`@endpe` cleanup, objective 2's
ordered-list flag) hook provisional latex-lab internals; they are
existence-guarded, so if a future release renames them the code becomes a
no-op rather than an error, but those pieces may then need re-fitting.


## Objective 4 - interlinear glosses as structure

The gloss engine emits its columns left to right (word 1 of every tier,
then word 2, ...), so the reading order is already word-by-word. What was
missing was grouping: the aligned words sat as loose text in one
paragraph. Now each column - an object word together with its gloss(es) -
is wrapped in a `Span`, so a screen reader reads and navigates the gloss
one word bundle at a time, in object-then-gloss order.

The words live inside `\vtop`/`\hbox` boxes, whose marked content would
otherwise attach to the enclosing paragraph rather than to the column
`Span` (the first attempt produced empty Spans). The fix follows tagpdf's
own idiom for tagging a sub-piece inside an open paragraph mc: per column,
`\tag_mc_end_push:` pauses the paragraph's marked content,
`\tag_struct_begin:n{tag=Span}` opens the bundle, each tier word is given
its own `\tag_mc_begin:n{tag=Span}`...`\tag_mc_end:` inside its box, then
`\tag_struct_end:` and `\tag_mc_begin_pop:n{}` close the bundle and
resume the paragraph. Verified (pdfinfo `-struct-text`) for two- and
three-tier glosses: each column is a `Span` containing its aligned words
in order. The `tagged` case asserts the gloss columns are grouped
(>=4 `Span` elements). Not a table: a table is read row-major by screen
readers, which for a gloss would read the whole object line then the whole
gloss line - the wrong order; column grouping keeps the word-by-word order.

Remaining: the object language is not yet marked (`/Lang`), and formal
PDF/UA validation (veraPDF) is still to do.


## Objective 5 - language of a gloss tier

`\GlossTierLang{tier}{code}` records a (BCP-47) language code for a gloss
tier. Under tagging, each word of that tier is wrapped in its own `Span`
carrying `/Lang` (nested inside the objective-4 column Span), so a screen
reader pronounces the object language with its own phonetics instead of the
document's. Other tiers are untouched, and a tier with no declared language behaves
exactly as before. Scope follows the usual rule: `\GlossTierLang` in the
preamble/body is a document-wide default; issued inside an example (a
local assignment, and the example body is typeset within the example's
list group) it overrides that tier for that example only and reverts
afterwards. Verified with a three-example document (German default,
French override in the middle example, German again in the third).

Mechanism: the per-word helpers from objective 4 consult
`\g_lx_gl_lang_prop`; when tier n has a language, `\lx@gl@wordbegin`
opens `\tag_struct_begin:n{tag=Span,lang=<code>}` around the word's mc and
`\lx@gl@wordend` closes it. (`/Lang` is a real key on
`\tag_struct_begin:n`; note `pdfinfo -struct-text` does *not* print
`/Lang`, so verify with a raw grep for `/Lang` in the PDF.) Verified: with
`\GlossTierLang{1}{de}` on a German/English gloss, the three object-tier
words each carry `/Lang(de)` and the gloss tier carries none. The `tagged`
case declares `\GlossTierLang{1}{de}` and asserts a `/Lang` appears.


## Objective 6 - Leipzig gloss abbreviations with spoken expansions

Category labels (SG, PST, NOM) read aloud as meaningless letter strings.
`\lpzg{3sg.pst}` typesets a whole compound label in one call and, under tagging,
wraps it in a `Span` carrying `/E` - the PDF "expansion text" of an
abbreviation - so a screen reader announces "singular" while the page
still shows SG and copy-paste still yields `sg`. `/E` is the right
property here (not `/Alt`, not `/ActualText`): it is the abbreviation-
specific entry and does not disturb text extraction.

The table is the standard Leipzig Glossing Rules list (83 entries, keyed by
the printed short form, line-break hyphens stripped; person numbers 1/2/3
map to "first/second/third person"). `\SetLeipzig{key}{expansion}`
extends or overrides; an unknown key is set in small caps with no `/E` and
no warning. `\lpzg` is used inside a gloss cell, i.e. inside the cell's
open marked content, so it uses the same `\tag_mc_end_push:` /
`\tag_mc_begin_pop:n{}` idiom as the column grouping to nest its own
`Span`+mc. The label is split on periods and a leading person digit (1/2/3) is
peeled off; each piece is expanded and the results joined into one `/E`
(`3sg.pst` -> "third person singular past"), pieces not in the table
passing through verbatim. Verified: a compound cell yields one abbreviation
Span whose `/E` is the joined expansion, nested in the column
Span beside a `/Lang`-tagged object word; alignment and print are
unchanged; untagged it is a plain `\textsc`. The `tagged` case asserts a
`/E` expansion is emitted. Self-contained: no dependency on the `leipzig`
package.


## Stacked alternatives (\altn)

`\altn` is set in text mode -- a `tabular` stack with a TikZ-drawn brace, no
math -- so the alternatives are ordinary tagged text and there is no
`Formula`. Under active tagging the stack is wrapped in a `Span` carrying a
spoken `/Alt` ("A, B, or C"), built from the alternatives with
`\text_purify:n` so formatting (`\sout`, ...) is stripped for speech. This
replaces the earlier math implementation, whose `Formula` could not be given
an accessible reading without breaking PDF/UA-2 (a `Span` may not contain the
`Part`/`P` the math tagging built). Requires `graphicx`+`tikz` instead of
`amsmath`. Verified: no `Formula`, valid `Span`, `/Alt` present, no untagged
content; the `tagged` test asserts the `/Alt`.


## Caveats

- The text-unit compensation is matched to the 2023 testphase
  internals. The API is explicitly provisional upstream; the guards
  make it degrade to a no-op rather than break if those internals
  change, but it will want revisiting as the tagging project moves out
  of testphase.
- `\DocumentMetadata` requires a recent LaTeX (2022+). Without it,
  nothing here activates and the package behaves exactly as before.
