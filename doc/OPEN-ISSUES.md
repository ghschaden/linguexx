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
