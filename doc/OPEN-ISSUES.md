# Open issues

Defects found and confirmed, but not fixed yet. Each says how it was seen
and how to reproduce it. These are BUGS. Undecided behaviour belongs in
`DEFERRED-DECISIONS.md` instead. Remove an entry in the commit that fixes it.

## XeLaTeX, tagged: right-to-left paragraphs fail veraPDF (upstream, not linguexx)

*Found 2026-11-03. Traced to upstream the same day.*

Under XeLaTeX with `\DocumentMetadata{... ua-2 ...}`, a right-to-left
paragraph fails 8.2.2-1 ("content that is not considered real shall be an
artifact"). Two entries were filed here: `\ex. HEAD` in a Hebrew document
or in `\begin{hebrew}` (1 item), and an ordinary gloss in a Hebrew
document (14 items). Both are this one problem. linguexx is not needed to
show it. A bare document fails with one Hebrew word, on the release kernel
and on `xelatex-dev` (LaTeX 2027-07-01 pre-release, 2026-11-02):

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
XeTeX reverses the boxes of an R segment from the inside, marked-content
operators included (finding 4 of `experiments/rtl`), and polyglossia sets
Hebrew paragraphs through `bidi`. Plain paragraphs, `itemize` and
`enumerate` all fail the same way. LuaLaTeX passes.

linguexx cannot repair the kernel's paragraph tagging from inside the
package. The ordinary gloss is partly linguexx's, though. In
`\ex. \ag. א ב ג\\ RG1 RG2 RG3\\`, every cell's own `/Span` comes out empty
as well, next to the kernel's `text-block`, and its text is untagged. That
is the package's marked content hit by the same reversal, and it is what
`\CommonGloss` avoids by setting each cell's marked content inside an L
segment.

Porting that wrapping is NOT enough. It was tried on 2026-11-03 and is
kept on the local branch `wip/rtl-gloss-xetex-tagging`. Each word and
each column (with the paragraph marked content it suspends and resumes)
was set as an L segment, and so was the judgment mark in a gloss. veraPDF
then PASSES `\exg.` and `\ag./\bg.` in a Hebrew document, but the
content stream is not balanced: the kernel closes the paragraph's marked
content at `\par`, inside bidi's R segment, so that EMC comes out first and
the last BDC is never closed. veraPDF does not catch it (poppler's
`pdfinfo -struct-text` reports "Mismatched EMC"). The plain mark in a plain
paragraph made it worse, so the branch limits that part to glosses.

What would work is what `\CommonGloss` does: paragraph tagging off for
the grid (`para/tagging = false`, as `\__lx_gl_rtl_boxsetup:` does) and the
grid set in a frame of its own. For the ordinary gloss that is a change
of layout path under XeTeX in right-to-left documents. It needs its own
decision and a nominal check of the untagged pages.

The suite has no check that BDC/EMC balance in a content stream. veraPDF
and the structure checks both missed this. `\CommonGloss` gets its own marked content right
(`\__lx_cg_gcell:nnnn`, `\__lx_cg_head:n`), and its right-to-left UA cases
pass only because they keep paragraph text out of Hebrew examples. Next
step: report it to the LaTeX tagging project (latex3/tagging-project)
with the document above. Not done yet: it waits for a go-ahead.

## LuaLaTeX, tagged: an English example's number reads ")2(" in a Hebrew document

*Found 2026-11-03. Diagnosed the same day.*

In a Hebrew document, the number of an example in `\begin{english}` is
set right to left (`\lx@dir@listbegin`: at the level outside the list) in
the English font. On the page it is right: "(2)", on the right. In the
text layer, and so for a screen reader, it is ")2(". A Hebrew example's
number reads "(1)". `struct_lbl_depths` was right not to find "(2)":
there is no such string in the tree.

Cause, shown without linguexx: a Latin font set right to left mirrors the
parentheses' GLYPHS, but its ToUnicode map names each glyph by its own
shape. The font with `Script=Hebrew` maps the mirrored glyph back to the
character typed. In `_preamble-rtlmain-ua` without linguexx,
`\begin{english}\hbox{\textdir TRT (3)}\end{english}` extracts as
") 3 (" (lualatex, TL 2026). Both labels' content streams draw the same
glyph ids in the same order. Only the fonts, and so the maps, differ.

Possible fixes, not yet decided:
- `/ActualText` with the logical number on the label's marked content
  under LuaTeX. Nothing changes on the page, but the `itemlabel` marked
  content is the kernel's, and a Span of linguexx's own under `Lbl` changes
  the tree that `struct_lbl_depths` reads.
- Set the number itself left to right (`\textdir TLT` around the label
  text). Same ink for "(2)", but not for a sub-label like "a.", whose
  period moves sides. So it would cover the main number only.
- Report it to luaotfload / fontspec as a ToUnicode defect for mirrored
  glyphs.

Repro: `\ex. HONE הילד`, then `\begin{english}\ex. ETWO\end{english}` in
`_preamble-rtlmain-ua`, under lualatex; `pdfinfo -struct-text` shows the
Lbl text.

## To confirm: two `\CommonGloss` choices made in passing

*2026-11-03, with the right-to-left fix. Not bugs, but chosen without being
asked; confirm, or move to `DEFERRED-DECISIONS.md`.*

- The annotation of a table whose example runs against the document is
  set in the frame's mirrored annotation column. In an English table in a
  Hebrew document, it goes where a Hebrew example's annotation goes. An
  ordinary crossed gloss sets it right after its grid instead, and a
  right-to-left ordinary gloss refuses `\exannot` altogether (`rtl-annot`),
  where a table carries it.
- A table's judgment mark stays at the row letter in every direction
  (the `\CommonGloss` rule of 2026-11-02). For ordinary right-to-left glosses
  the mark's side is still provisional in `DEFERRED-DECISIONS.md`.
