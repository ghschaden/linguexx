# Open issues

Defects found and confirmed, but not fixed yet. Each says how it was seen
and how to reproduce it. These are BUGS. Undecided behaviour belongs in
`DEFERRED-DECISIONS.md` instead. Remove an entry in the commit that fixes it.

## babel, right-to-left main language: the "left to right" fallback mangles text

*Found 2026-11-03, while sizing babel support. Not fixed: recorded only.*

Right-to-left layout under babel is undecided (DEFERRED-DECISIONS, "Right-
to-left documents under babel"), and what linguexx promises meanwhile is
the `rtl-babel` warning: "Examples are set left to right, as in a
left-to-right document." With a right-to-left MAIN language that is not
what happens. babel mirrors the lists itself, so examples are numbered at
the right, and linguexx's own boxes are then reordered by babel's bidi
code. The English example inside `otherlanguage` is fine; the rest is
broken. Seen with babelbidi 0.4.1 (2026/10/26) and babel 26.15 (2026/10/29),
TeX Live 2026; the document builds without an error on both engines and
gives the one warning.

    \documentclass[11pt]{article}
    \usepackage[a4paper,margin=25mm]{geometry}
    \usepackage[english,hebrew]{babelbidi}
    \babelfont{rm}{FreeSerif.otf}
    \usepackage{linguexx}
    \pagestyle{empty}
    \begin{document}
    \ex. הילד אכל את התפוח.
    \a. הילד אכל.
    \b. *אכל הילד.
    \z.

    \begin{otherlanguage}{english}
    \ex. The boy ate the apple.
    \a. first.
    \b. *second.
    \z.
    \end{otherlanguage}

    \exg. הילד אכל\\ DEF.boy eat.PST\\
    \glt `The boy ate.'
    \end{document}

- **LuaLaTeX** (`bidi=basic`): the gloss line is reversed letter by
  letter -- `DEF.boy eat.PST` prints as `TSP.tae yob.FED` -- and the
  translation's quotes and full stop are mirrored (`'.The boy ate'`). The
  example number sits against the text instead of at its usual distance,
  and the judgment mark runs into the label (`*.b`).
- **XeLaTeX** (`bidi=bidi-r`): the translation's words come out in
  reverse order (`ate.' boy 'The`), and the sub-example labels read `a.`
  rather than `.a`. The gloss line itself is readable.

Not covered by any case: `tests/rtl-babel.tex` has English as its main
language and on purpose measures nothing in its Hebrew example. It also
copies babelbidi's `\if@RTLmain` rather than loading the package. The
CHANGELOG's Unreleased entry ("with babel's right-to-left support
(babelbidi included) every example is now set as in a left-to-right
document") claims the same thing the warning does, and is wrong in the
same case.

Fixing this does not mean settling the deferred decision. The smallest fix
keeps the decision open: either the warning says that a right-to-left
main language needs polyglossia, or linguexx protects its gloss and
translation boxes from babel's reordering. Then add a Hebrew-main babelbidi
case that measures the result, and correct the changelog wording.

## XeLaTeX, tagged: right-to-left paragraphs fail veraPDF (upstream, not linguexx)

*Found 2026-11-03. Traced to upstream the same day. linguexx's own part
(ordinary glosses) fixed on 2026-11-03, see below.*

Under XeLaTeX with `\DocumentMetadata{... ua-2 ...}`, a right-to-left
paragraph fails 8.2.2-1 ("content that is not considered real shall be an
artifact"). linguexx is not needed to show it. A bare document fails with
one Hebrew word, on the release kernel and on `xelatex-dev` (LaTeX
2027-07-01 pre-release, 2026-11-02):

    \DocumentMetadata{lang=he,pdfversion=2.0,pdfstandard=ua-2,tagging=on}
    \documentclass{article}
    \usepackage{fontspec}
    \setmainfont{FreeSerif.otf}
    \usepackage{polyglossia}
    \setmainlanguage{hebrew}
    \newfontfamily\hebrewfont{FreeSerif.otf}[Script=Hebrew]
    \usepackage{hyperref}
    \hypersetup{pdftitle={t},pdfdisplaydoctitle=true}
    \begin{document}
    הילד
    \end{document}

In the content stream, the paragraph's marked content comes out empty
(`/text-block <</MCID 1>> BDC EMC`) and the glyphs follow it, untagged.
XeTeX reverses an R segment's boxes from the inside, marked-content
operators included, and polyglossia sets Hebrew paragraphs through `bidi`.
Plain paragraphs, `itemize` and `enumerate` all fail the same way.
LuaLaTeX passes.

So in a linguexx document under XeLaTeX, a head line (`\ex. HEAD`), a
`\glt` translation and any plain text of a Hebrew example still fail, as
any Hebrew paragraph does. Next step: report it to the LaTeX tagging
project (latex3/tagging-project) with the document above. Not done yet:
it waits for a go-ahead.

**Fixed in linguexx: ordinary glosses.** A gloss's paragraph is now set
with the kernel's paragraph tagging off (`\__lx_gl_paraoff_begin:`), so no
kernel marked content is left in bidi's R segment. Each word and the
judgment mark are L segments of their own (`\l__lx_gl_rframe_bool`), so
the reversal only reorders whole units. The column is deliberately NOT an
L segment: the R segment's mirroring of the column box is what sets a word
flush right in its column. Pages are identical to before in every
right-to-left case. `rtl-gloss-xetex-ua` (Hebrew document) and
`rtl-gloss-hebenv-ua` (`\begin{hebrew}`) pass veraPDF under XeLaTeX.

How it got there: L segments alone (the first attempt) passed veraPDF
with an unbalanced stream, because the kernel's closing EMC still came out
first. The suite's balance check (`marked_content_balance`) exists
because of that.
