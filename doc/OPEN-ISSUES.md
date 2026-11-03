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
segment. Doing the same for the ordinary gloss is a linguexx fix. It
would leave the document failing only where the kernel fails. `\CommonGloss` gets its own marked content right
(`\__lx_cg_gcell:nnnn`, `\__lx_cg_head:n`), and its right-to-left UA cases
pass only because they keep paragraph text out of Hebrew examples. Next
step: report it to the LaTeX tagging project (latex3/tagging-project)
with the document above. Not done yet: it waits for a go-ahead.

## LuaLaTeX, tagged: an English example's number in a Hebrew document

*Found 2026-11-03.*

`struct_lbl_depths` does not find the number of an example in
`\begin{english}` in a Hebrew document under LuaLaTeX. It does find it
under XeLaTeX. The cause may be the number's text in the tree (mirrored?)
rather than a missing `Lbl`, so check that first. The test helpers would
then be what needs changing, not the package. Repro: `\ex. HONE הילד`, then
`\begin{english}\ex. ETWO\end{english}` in `_preamble-rtlmain-ua`.

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
