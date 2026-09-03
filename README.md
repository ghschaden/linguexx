# linguexx

A standalone LaTeX package for linguistic examples, with a `linguex`-compatible
input syntax and first-class support for **accessible (tagged) PDF output**.

`linguexx` reimplements the familiar dot-syntax of `linguex`
(`\ex.`, `\a.`, `\b.`, `\z.`, `\exg.`, `\gll`, `\glt`, `\Next`, `\Last`, …) on a
fresh `expl3` engine, with no dependency on `linguex`, `cgloss4e`, or `xspace`.
It runs on **pdfLaTeX, XeLaTeX and LuaLaTeX**. A `[legacy]` option reproduces
`linguex`'s exact geometry for drop-in replacement; the default mode is a
slightly tighter variant.

Two other input syntaxes are available as options and drive the same engine, so
they share one counter, one label system and all layout parameters with the dot
syntax: `[gb4e]` for the `exe` / `xlist` environments, and `[langsci]` for the
`\ea` … `\z` front-end of `langsci-gb4e`. Loaded alongside `[lazy]`, either
lets a document move over one example at a time. `[langsci]` provides what
`langsci-gb4e` does — the criterion is what works there, not what its two
documents describe — including `\eal` … `\zl`, the sub-list numbering
variants, the box and font commands and its four package options. It also
takes that package's reference convention: under `[langsci]` a plain `\ref`
prints `1` rather than `(1)`, as `langsci-gb4e` does, and `\ExParenRefs`
asks for the other one. The two names that have never worked upstream
(`xlistabr`, `qlist`) are refused by name, with an error saying what to write
instead.

## Accessibility

When the document enables the LaTeX tagging code, `linguexx` writes its examples
into the PDF structure tree as genuine, accessible objects:

- examples are ordered lists — `L → LI → Lbl → LBody`, sub-levels nested, with
  valid per-level `/ListNumbering` (decimal / lower-alpha / lower-roman);
- examples inside footnotes keep a valid tree;
- grammaticality marks carry a spoken form (`/Alt`), so a screen reader says
  "ungrammatical" rather than "asterisk" — see `\DeclareJudgment[spoken=…]`;
- interlinear glosses are grouped column by column, read word-bundle by
  word-bundle in the right order (not as loose text, and not as a table, which
  screen readers read in the wrong order);
- a gloss tier's language can be recorded (`\GlossTierLang{1}{de}` → `/Lang`);
- a free translation set beside the gloss rather than under it
  (`\GlossTransSide`) keeps its place in the reading order, grid first;
- structural labels set beside the examples (`\exannot{[CP]}`) carry a spoken
  form too (`\SetAnnotSpoken` → `/Alt`), so a reader hears "complementizer
  phrase" while the page still shows `[CP]`
  (and `\ExAnnotFit` puts that column where the examples themselves say it
  belongs, one column per example);
- Leipzig category abbreviations carry their expansion (`\lpzg{sg}` → `/E`
  "singular"), so they are spoken in full while the page still shows SG, and
  `\lpzglist` prints the list of those actually used, as a tagged list;
- cross-references are links, and reach the tree as `Link` elements with their
  annotation under them: `\ref` as always, and with it `\Next`, `\Last` and
  the rest of the relative references, which link to the example they name
  without needing a label — and never to one the document does not have.

See `doc/TAGGING-NOTES.md` for the technical account and `doc/PDFUA-CHECKLIST.md`
for turning a document into a PDF/UA-conformant build.

## Usage

```latex
\documentclass{article}
\usepackage[lazy]{linguexx}   % or [legacy], [gb4e], [langsci], combinations
\begin{document}
\ex. A first example.
\a. a sub-example
\b. *a judged sub-example

\exg. Der Hund bellte.\\ 
the dog barked.\\
\glt `The dog barked.'
\end{document}
```

For accessible output, add a `\DocumentMetadata` line before `\documentclass`;
the simplest current form is

```latex
\DocumentMetadata{lang=en, tagging=on}
```

The full manual is `linguexx-doc.pdf`. Rebuild it with **lualatex**, not
pdflatex: it documents (§9.3) that characters with a diacritic below the
letter — Indic and Semitic transliteration, Latvian, Romanian — get a broken
text layer under pdflatex, and it contains those characters in the table that
explains it. The manual refuses to build with pdflatex for that reason.

## Installation

Put `linguexx.sty` where LaTeX can find it — the working directory for a single
project, or `TEXMF/tex/latex/linguexx/` (then `texhash`) for a system-wide
install.

## Tests

The regression suite checks example geometry (via `pdftotext -bbox`) and, for the
tagged cases, the PDF structure tree, across all three engines:

```sh
cd tests
python3 runtests.py            # all cases, all engines
python3 runtests.py -k tagged  # one case
python3 runtests.py -v         # show every assertion
```

It needs the three TeX engines plus `poppler-utils` (`pdftotext`, `pdfinfo`) and
Python 3. One assertion (`pdflatex/judgment-align`) is a known `pdftotext`
token-merging artifact, not a layout bug; it is marked expected-fail.

## Requirements

- A reasonably current TeX Live (2023 or later; the tagging support tracks the
  LaTeX tagging project, which is still evolving — see the notes).
- `expl3` (part of the LaTeX kernel).

## Licence

LaTeX Project Public License 1.3c or later — see `LICENSE`.

## Author

Gerhard Schaden \& Claude (Fable, Opus, Sonnet).
