# Open issues

Defects found and confirmed, but not fixed yet. Each says how it was seen
and how to reproduce it. These are BUGS. Undecided behaviour belongs in
`DEFERRED-DECISIONS.md` instead. Remove an entry in the commit that fixes it.

## XeLaTeX, tagged: a head line in a right-to-left example fails veraPDF

*Found 2026-11-03.*

Under XeLaTeX with `\DocumentMetadata{... ua-2 ...}`, `\ex. HEAD` fails
8.2.2-1 with one content item that is neither tagged nor an artifact, in two
cases. The first is a Hebrew document (`_preamble-rtlmain-ua`). The second
is `\begin{hebrew}` in an English one (`_preamble-ua-polyglossia`). It
happens whether the head line is Latin or Hebrew, and with or without
anything else in the example. LuaLaTeX passes. The `\CommonGloss`
right-to-left UA cases avoid head lines on Hebrew examples because of it.

## XeLaTeX, tagged: an ordinary gloss in a Hebrew document fails veraPDF

*Found 2026-11-03.*

`\ex. ... \ag. א ב ג\\ RG1 RG2 RG3\\ \bg. *ד ה ו\\ ...` in a Hebrew
document (`_preamble-rtlmain-ua`) fails 8.2.2-1 with 14 content items under
XeLaTeX, and already did with the package before 2026-11-03. Probably the
same mechanism that `\CommonGloss` had to avoid: XeTeX reverses an R
segment's boxes inside, marked-content operators included (finding 4 of
`experiments/rtl`), and the paragraph's R segment holds the cells' and the
judgment's marked content. See `\__lx_cg_gcell:nnnn` and `\__lx_cg_head:n`
for how the table keeps its marked content out of R segments.

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
