# Notes from the Lexique pandoc + LuaLaTeX exploration (2026-10-03)

Found while setting all numbered examples of 13 *Lexique* articles with
linguexx (`~/src/linguex-peren/pandoc-test/`). Every example there uses a
custom label, `\ex.[(n)]`, because the authors' numbers must be kept.

Tested with linguexx 1.3.2 (2026/09/21, `~/texmf`, commit `d6bfa1f`),
TeX Live 2026, LuaHBTeX 1.24.0, LaTeX 2025-11-01.

## 1. Sub-examples under a custom label: wrong number, shared anchor (linguexx)

**Fixed 2026-10-03** (uncommitted): references print the label with the
letter, and anchors come from serials (DEFERRED-DECISIONS entry closed,
option 2). Test case `tests/customlabel-refs.tex`; CHANGELOG, Unreleased.

```latex
\documentclass{article}
\usepackage[phantomalign]{linguexx}
\usepackage{hyperref}
\begin{document}
\ex.[(1)] \a. first a\label{one-a}
\b. first b

\ex.[(2)] \a. second a\label{two-a}
\b. second b

\ex. \a. auto a\label{auto-a}
\b. auto b

See \ref{one-a}, \ref{two-a} and \ref{auto-a}.
\end{document}
```

**Observed**
- It prints "See **(0a), (0a)** and (1a)". Expected: "(1a), (2a) and (1a)".
- The `.aux` file has:
  ```
  \newlabel{one-a}{{\hbox {\theExLBr 0a\theExRBr }}{1}{}{SubExNo.lxex.0.a}{}}
  \newlabel{two-a}{{\hbox {\theExLBr 0a\theExRBr }}{1}{}{SubExNo.lxex.0.a}{}}
  \newlabel{auto-a}{{\hbox {\theExLBr 1a\theExRBr }}{1}{}{SubExNo.lxex.1.a}{}}
  ```
- The pdf backend warns twice: `ignoring duplicate destination with the
  name 'SubExNo.lxex.0.a'`. Both sub-examples get the same anchor, so the
  second link goes to the first example.

**Cause [inferred].** A custom label does not advance `ExNo`, by design.
But the sub-example's reference text and its anchor name are still built
from `\theExNo` (here 0), not from the custom label.

**What might be expected [inferred].**
- The reference text: the custom label with the letter, "(1a)" (or "1a"
  under `[langsci]`).
- The anchor: unique per example, for instance from an internal counter
  stepped by every example, custom or not.

**Seen in practice.** 1950's 16 examples gave repeated
`SubExNo.lxex.0.b` duplicate-destination warnings.

## 2. `\label` on a custom-labelled example: empty reference (linguexx; perhaps by design)

```latex
\ex.[(7)]\label{seven} A plain example with a custom label.
See \ref{seven}.
```

**Observed**
- "See ." The `.aux` has `\newlabel{seven}{{}{1}{}{Doc-Start}{}}`: empty
  text, and an anchor at the start of the document.
- No warning, so the empty reference passes unnoticed.

The manual presents custom labels mainly for repeating an example
(`\ex.[\ref{…}]`), so a label on one may be out of scope. If so, a warning
would help; otherwise the reference text could be the custom label.

## 3. Not linguexx: nested lists split across a page break under tagging (LaTeX kernel)

Recorded here because it hits linguexx sub-examples. It is reproducible
with the kernel's own nested `enumerate` and no linguexx.

```latex
\DocumentMetadata{lang=en, pdfversion=2.0, pdfstandard=ua-2, tagging=on}
\documentclass{article}
\usepackage{hyperref}
\hypersetup{pdftitle={t}, pdfdisplaydoctitle=true}
\begin{document}
\count255=0 \loop\ifnum\count255<44 \advance\count255 1
  Filler line of text number \the\count255.\par\repeat

\begin{enumerate}
\item[(4)] \begin{enumerate}
  \item im le-mi\v{s}ehu ba lepaprec [x.com]
  \item kol exan haya yaxol laasot paparaci [mikmak.co.il]
  \end{enumerate}
\end{enumerate}

After the example.
\end{document}
```

**Observed.** With 44 filler lines the list breaks between its two inner
items, and the run ends with:

```
! Package tagpdf Error: The number of automatic begin (…) and end (…+1)
```

Every structure element after the break is attached to the structure root.
veraPDF then fails the file (8.2.5.2, and the parent–child rules).

**Results of the scan:**

| Case | Splits tested | Errors |
|---|---|---|
| No list | 1 | none |
| Flat 2-item `enumerate` | 2 | none |
| Nested `enumerate` (kernel) | 1 | 1 |
| linguexx sub-examples, `article` | 3 (filler 42, 43, 44) | 2 (42, 44) |
| linguexx sub-examples, `scrartcl` | 3 (filler 40, 41, 42) | 2 (40, 42) |

The linguexx cases ran with items as one line each, and with items of two
lines joined by `\\`. Not every split of a nested list fails: one break
point in each class passed (filler 43 in `article`, 41 in `scrartcl`).

**Worth reporting upstream:** github.com/latex3/latex2e, or the
tagging-project. Until it is fixed, a linguexx example that breaks across
a page in a tagged document can break the whole structure tree.
