# Open issues

Defects found and confirmed, but not fixed yet. Each says how it was seen
and how to reproduce it. These are BUGS. Undecided behaviour belongs in
`DEFERRED-DECISIONS.md` instead. Remove an entry in the commit that fixes it.

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

## XeLaTeX, tagged: `\GlossRTL` in a Hebrew document reads an undeclared tier reversed

*Found 2026-11-03, while testing the gloss fix.*

In `\GlossRTL`'s cells, a tier that declares no language is taken as left
to right (`\__lx_gl_tier_if_rtl:n`), in a Hebrew document too. Under
XeLaTeX its Hebrew words then get no `/ActualText` and read in visual
order in the tree ("ץע" for "עץ"). The page is right. With
`\GlossTierLang{1}{he}` they read right, and `rtl-gloss-xetex-ua` declares
it. Taking an undeclared tier as right to left wherever the document is
would also change LuaLaTeX's cells, so it was not done in passing. Repro:
`\GlossRTL\exg. עץ גדול\\ A B\\` in `_preamble-rtlmain-ua`, under xelatex.
