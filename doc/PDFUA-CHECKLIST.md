# Making a linguexx document PDF/UA-conformant

This is the close-out of the accessibility work. Objectives 1-6 make the
*linguistic* content (examples, judgments, glosses, abbreviations) carry
correct structure and semantics. PDF/UA (ISO 14289) conformance is a
larger, document-level checklist on top of that. LaTeX can *declare*
PDF/UA and satisfies most of the checklist automatically, but it cannot
*guarantee* conformance -- only a validator (veraPDF) can confirm it. This
file is the preamble to use and the checklist to walk before validating.

Important framing: `pdfstandard=ua-2` writes the PDF/UA metadata but does
**not** enforce the rules. It is a claim, which veraPDF then checks.


## The preamble

```latex
% TeX Live 2025-11 or newer:
\DocumentMetadata{lang=en, pdfversion=2.0, pdfstandard=ua-2, tagging=on}
% TeX Live 2023-2025 (portable; also works on newer):
% \DocumentMetadata{lang=en, pdfversion=2.0, pdfstandard=ua-2,
%                   testphase={phase-III}}

\documentclass{article}
\usepackage[lazy]{linguexx}
\usepackage{hyperref}
\hypersetup{pdftitle={<your document title>},
            pdfdisplaydoctitle=true}
\title{<your document title>}
\author{<you>}
```

For a PDF 1.7 target instead of 2.0, use `pdfversion=1.7` and
`pdfstandard=ua-1`. `ua-2` must go with PDF 2.0. Several validators still support only
UA-1; if you must pass one of those, target `ua-1` / PDF 1.7.


## What is handled for you

Automatic (LaTeX tagging kernel), verified present in the output:

- [x] `/MarkInfo /Marked true` -- the PDF is marked as tagged.
- [x] `/StructTreeRoot` -- a structure tree exists.
- [x] Document `/Lang` -- from `lang=` in `\DocumentMetadata`.
- [x] `pdfuaid:part` in the XMP metadata -- the PDF/UA declaration.
- [x] `/ViewerPreferences /DisplayDocTitle true` and `dc:title` -- from
      the `hyperref` lines above (a UA document must show its title, not
      its filename).
- [x] All real content marked, decorative content artifacted -- in the
      demo, zero text operators fall outside marked content.

By linguexx (objectives 1-6), verified with `pdfinfo -struct-text`:

- [x] Examples are ordered lists: `L -> LI -> Lbl -> LBody`, sub-levels
      nested, valid per-level `/ListNumbering`
      (`Decimal`/`LowerAlpha`/`LowerRoman`).
- [x] Examples inside footnotes keep a valid tree.
- [x] Grammaticality marks carry a spoken `/Alt` ("ungrammatical").
- [x] Gloss columns are grouped as `Span`s in word-by-word reading order.
- [x] A gloss tier's language is recorded (`/Lang`) via `\GlossTierLang`.
- [x] Leipzig abbreviations carry their expansion (`/E`) via `\lpzg`.


## What you must do

These are outside linguexx and are the usual reasons a LaTeX document
fails PDF/UA:

- [ ] **Give the document a title** (the `\title` + `hyperref` lines
      above). This is the single most common UA failure.
- [ ] **Alt text on every graphic.** Each `\includegraphics`, `tikzpicture`,
      or `picture` needs `alt={...}` in its options -- or `artifact` if it
      is purely decorative, or `actualtext={...}` if it is text as image.
      An untagged or un-described image fails UA.
- [ ] **Heading hierarchy.** Use `\section`/`\subsection`/... in order;
      do not skip a level (no `\subsubsection` directly under `\section`).
- [ ] **Math needs handling** under UA-2: add
      `tagging-setup={math/setup=mathml-SE}` (and fill in the MathML), or
      at least `math/alt/use` with `\mathalt`. linguexx examples contain
      no math, but your surrounding text might. (The harmless luamml
      warning you may see when there is no math can be silenced with
      `\tagpdfsetup{math/mathml/luamml/load=false}`.)
- [ ] **Avoid tagging-incompatible packages.** `listings` in particular
      is not yet compatible (it validates but raises a compile error);
      `microtype`'s footnote patch has been reported to cause trouble.
      Check yours with the `check-tagging-status` key in
      `\DocumentMetadata`.
- [ ] **Tables**, if you use them, need the tagged-table support and are a
      common source of validator complaints (`\multicolumn`/`\multirow`
      especially). linguexx glosses are *not* tables, so they are fine.


## How to validate

- **veraPDF** -- <https://verapdf.org/software/>. The authoritative PDF/UA
  validator; this is the real test. Run it on your compiled PDF.
- **PAC** -- <https://pac.pdf-accessibility.org>. An alternative; note it
  cannot validate UA-2/PDF-2.0, so for PAC target UA-1.
- **Structure only** -- <https://texlive.net/showtags> extracts the
  structure tree as XML and checks it against a schema. Good for a quick
  structural sanity check without installing anything.
- **In-source** -- add `check-tagging-status` to `\DocumentMetadata` to
  have LaTeX report, in the log, whether your class and packages are
  tagging-ready.


## Honest caveats

- LaTeX tagging is still an evolving (testphase) feature; the interface and
  the emitted structure change between releases. Re-validate after a TeX
  Live upgrade.
- Validators sometimes disagree, and some flag correct structure: e.g.
  Adobe Preflight has been reported to dislike the `L` (list) element that
  the examples legitimately use. A veraPDF pass is the target; a single
  tool's complaint is not necessarily a real defect.
- This checklist covers what can be checked from the structure and
  metadata. Genuine accessibility also needs testing with an actual screen
  reader by someone who uses one -- the structure being correct is
  necessary but not sufficient.
