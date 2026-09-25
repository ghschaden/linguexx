"""\altn and \altg: the alternatives stack, in text mode throughout.

Split out of runtests.py; the assertion bodies are unchanged.  Each
function takes a parsed Page and returns a list of (ok, description) pairs
built with check(), which is the whole protocol.
"""

import re

from suite.check import check
from suite.geometry import (
    brace_bulge, ink_clearance, stroke_width,
)
from suite.pdf import (
    TOL, Page, inflated,
)
from suite.structure import (
    struct_alt_kids, struct_alts, struct_empty_alts, struct_exps,
)

def a_altg(p: Page):
    """\altg: two calls (object line, gloss line) assembling one paradigm,
    centred on the object/gloss midline."""
    r = []
    rows = [p.find(t) for t in ("ROWAA", "ROWBB", "ROWCC", "ROWDD")]
    gls = [p.find(t) for t in ("glaa", "glbb", "glcc", "gldd")]

    def cy(w):
        return (w.y0 + w.y1) / 2

    # the two columns of the block each share an x origin, gloss right of object
    xs = [w.x0 for w in rows]
    r.append(check(max(xs) - min(xs) < TOL,
                   f"object column shares one x origin (spread {max(xs)-min(xs):.2f}pt)"))
    gxs = [w.x0 for w in gls]
    r.append(check(max(gxs) - min(gxs) < TOL,
                   f"gloss column shares one x origin (spread {max(gxs)-min(gxs):.2f}pt)"))
    r.append(check(min(gxs) > max(w.x1 for w in rows),
                   "gloss column sits right of the object column"))
    # each alternative is one row: object word and its gloss on one line
    for o, g in zip(rows, gls):
        r.append(check(abs(cy(o) - cy(g)) < 2.0,
                       f"{o.text}/{g.text} form one row ({cy(o):.1f} vs {cy(g):.1f})"))
    # four distinct rows, in order
    r.append(check(all(cy(a) < cy(b) - 2 for a, b in zip(rows, rows[1:])),
                   "four alternatives occupy four distinct rows"))
    # centring on the interlinear frame: row 2 rides the object line,
    # row 3 the gloss line; rows 1 and 4 protrude
    det, gdet = p.find("FRAMEDET"), p.find("framedet")
    r.append(check(abs(cy(rows[1]) - cy(det)) < 2.0,
                   f"row 2 rides the object line ({cy(rows[1]):.1f} vs {cy(det):.1f})"))
    r.append(check(abs(cy(rows[2]) - cy(gdet)) < 2.0,
                   f"row 3 rides the gloss line ({cy(rows[2]):.1f} vs {cy(gdet):.1f})"))
    r.append(check(cy(rows[0]) < det.y0 and cy(rows[3]) > gdet.y1,
                   "rows 1 and 4 protrude above and below the frame"))
    # the example number sits on the object line, untouched by the block
    num = p.find("(2)")
    r.append(check(abs(cy(num) - cy(det)) < 2.0,
                   f"example number rides the object line ({cy(num):.1f} vs {cy(det):.1f})"))
    # the frame's gloss pairing stays intact after the paradigm column
    for top, below in [("FRAMEVERB", "frameverb"), ("FRAMEADV", "frameadv")]:
        wt, wb = p.find(top), p.find(below)
        r.append(check(abs(wt.x0 - wb.x0) < TOL,
                       f"column {top}/{below} aligned after the stub "
                       f"({wt.x0:.2f} vs {wb.x0:.2f})"))
    # solo use outside a gloss still stacks
    sa, sb = p.find("SOLOA"), p.find("SOLOB")
    r.append(check(abs(sa.x0 - sb.x0) < TOL and cy(sb) > cy(sa) + 2,
                   "solo \\lxAltg stacks its alternatives"))
    return r


def a_altn(p: Page):
    r"""\altn: a braced stack in running text, its three column alignments,
    and -- the part no coordinate proves -- which way the braces curl."""
    r = []

    def cy(w):
        return (w.y0 + w.y1) / 2

    rows = {k: [p.find(f"{k}TOPPPP"), p.find(f"{k}M"), p.find(f"{k}BOTTOMMM")]
            for k in ("C", "L", "R")}
    # three distinct rows, in source order, in every alignment
    for k, ws in rows.items():
        r.append(check(all(cy(a) < cy(b) - 2 for a, b in zip(ws, ws[1:])),
                       f"[{k}] the alternatives occupy three rows in order"))
    # the alignment option is what distinguishes the three stacks: [l]
    # shares left edges, [r] right edges, the default centres the rows.
    lw = rows["L"]
    r.append(check(max(w.x0 for w in lw) - min(w.x0 for w in lw) < TOL,
                   f"[l] rows share a left edge "
                   f"(spread {max(w.x0 for w in lw) - min(w.x0 for w in lw):.2f}pt)"))
    rw = rows["R"]
    r.append(check(max(w.x1 for w in rw) - min(w.x1 for w in rw) < TOL,
                   f"[r] rows share a right edge "
                   f"(spread {max(w.x1 for w in rw) - min(w.x1 for w in rw):.2f}pt)"))
    cw = rows["C"]
    ctrs = [(w.x0 + w.x1) / 2 for w in cw]
    r.append(check(max(ctrs) - min(ctrs) < TOL,
                   f"default rows share a centre line "
                   f"(spread {max(ctrs) - min(ctrs):.2f}pt)"))
    # ... and each of the three really is a different shape: a centred and
    # a right-aligned stack of the SAME rows would both pass their own
    # check if the option were ignored and one spec used for all three.
    r.append(check(abs(min(w.x0 for w in cw) - min(w.x0 for w in rw)) > TOL
                   or abs(max(w.x1 for w in cw) - max(w.x1 for w in rw)) > TOL,
                   "the [r] stack is not laid out like the default one"))
    r.append(check(max(w.x0 for w in lw) - min(w.x0 for w in lw)
                   < max(w.x0 for w in rw) - min(w.x0 for w in rw) - TOL,
                   "the [l] stack is not laid out like the [r] one"))
    # judgment marks survive into every row, not just the first.  With
    # alignment off (the default here) the mark stays inside the
    # alternative, so the sentinel word carries it and a lost star shows up
    # as the bare stem -- which p.find would still happily match, hence the
    # explicit test on the text rather than on mere presence.
    for tok in ("STOPPPP", "SBOTTOMMM"):
        got = p.find(tok).text
        r.append(check(got == f"*{tok}",
                       f"{tok} keeps its judgment mark; got {got!r}"))

    # the stack is set into the line: the sentinels on either side stay on
    # the text baseline while the rows straddle it
    left, right = p.find("CENTREDL"), p.find("CENTREDR")
    r.append(check(abs(cy(left) - cy(right)) < 2.0,
                   "the text around the stack stays on one baseline"))
    r.append(check(cy(cw[0]) < cy(left) and cy(cw[2]) > cy(left),
                   f"the stack straddles the text line "
                   f"(rows at {cy(cw[0]):.1f}/{cy(cw[2]):.1f}, text at "
                   f"{cy(left):.1f})"))
    r.append(check(right.x0 > max(w.x1 for w in cw),
                   "the following text clears the stack"))
    # and it works inside an example, where the label must stay put
    ex = p.find("(1)")
    r.append(check(abs(cy(ex) - cy(p.find("EXAMPLEL"))) < 2.0,
                   "an \\altn in an example leaves the number on its line"))

    # --- the braces themselves ------------------------------------------
    # Their ink lies in the gaps the stack leaves on either side: left
    # brace between CENTREDL and the leftmost row, right brace between the
    # rightmost row and CENTREDR.  Vertically they span the stack.
    top, bot = min(w.y0 for w in cw), max(w.y1 for w in cw)
    lgap = (left.x1, min(w.x0 for w in cw))
    rgap = (max(w.x1 for w in cw), right.x0)
    r.append(check(lgap[1] - lgap[0] > 4.0 and rgap[1] - rgap[0] > 4.0,
                   f"both braces have room ({lgap[1]-lgap[0]:.1f}pt left, "
                   f"{rgap[1]-rgap[0]:.1f}pt right)"))
    # The pen.  A brace drawn at a hairline reads as a wire beside the type
    # it stands next to, which is what the tikz brace decoration drew here
    # until v1.2: 0.4pt against Computer Modern's own 1.2pt brace stem at
    # 11pt.  The shaft is measured a quarter of the way down, where the
    # curve is straight and the horizontal run is the pen itself.
    quarter = top + (bot - top) / 4
    for gap, side in ((lgap, "left"), (rgap, "right")):
        pen = stroke_width(p.path, gap[0], gap[1], quarter - 1, quarter + 1)
        r.append(check(pen > 0.9,
                       f"the {side} brace is drawn with a typographic pen, "
                       f"not a hairline ({pen:.2f}pt at the shaft)"))
    lbulge = brace_bulge(p.path, lgap[0], lgap[1], top, bot)
    rbulge = brace_bulge(p.path, rgap[0], rgap[1], top, bot)
    r.append(check(lbulge < -5.0,
                   f"the left brace is an opening one: its tip points away "
                   f"from the stack (tip - ends = {lbulge:.1f}px, want < -5)"))
    r.append(check(rbulge > 5.0,
                   f"the right brace is a closing one: its tip points away "
                   f"from the stack (tip - ends = {rbulge:.1f}px, want > +5)"))
    return r


def a_altn_phantomalign(p: Page):
    r"""A judgment in an \altn stack hangs left, and the stems line up.

    Two failures are pinned here and they are independent.  The alignment:
    without the gutter column, "*sont" over "est" left-aligns on the star,
    so the two words being contrasted are the only pair NOT aligned.  And
    the star's survival: an alternative after the first handed the tabular
    row separator its own starred form \\*, which ate the mark -- clean
    compile, no warning, and a page that reads as a typo.

    The stars are counted rather than located, because that failure removes
    a word instead of moving one, and no coordinate assertion sees it.
    """
    r = []

    def cy(w):
        return (w.y0 + w.y1) / 2

    def stems(tok, n):
        ws = sorted(p.find_all(tok), key=cy)
        if len(ws) != n:
            raise AssertionError(f"expected {tok} {n} times, got {len(ws)}: {ws}")
        return ws

    def aligned(ws, tok):
        """The stems line up -- measured on the RIGHT edge, deliberately.

        Every probe stack repeats one identical stem, so aligned stems agree
        on both edges.  But the left edge cannot tell the two layouts apart:
        with the mark still inside the alternative, pdftotext reports one
        word "*PSTEM" whose x0 IS the column origin, so a broken layout
        shares a left edge just as happily.  The right edge is where the
        star's width lands, which is why phantomalign.tex measures there
        too.
        """
        spread = max(w.x1 for w in ws) - min(w.x1 for w in ws)
        return check(spread < TOL,
                     f"{tok} stems line up (right-edge spread {spread:.2f}pt)")

    # The mark must CLEAR the brace it tucks toward.  \AltJdgTuck pulls the
    # stack into the hollow the brace's arm leaves, and how much room that
    # hollow has depends on the brace's own ink -- so this is the assertion
    # that a heavier brace, or a deeper tuck, cannot quietly print the mark
    # on top of the curve.  It is the fault the package warns about when
    # the tuck is set past the brace's box, and the one it cannot warn
    # about when the ink simply grows: measured, not argued.
    probe_l = p.find("PROBEL")
    marked = [w for w in p.find_all("PSTEM") if w.text.startswith("*")]
    if len(marked) != 1:
        raise AssertionError(f"expected one *PSTEM, got {marked}")
    clear = ink_clearance(p.path, probe_l.x1, marked[0].x1 + 1,
                          marked[0].y0, marked[0].y1)
    r.append(check(clear > 1.0,
                   f"the hanging mark clears the opening brace "
                   f"({clear:.2f}pt of air at the closest row)"))

    def hangs(marked, plain, tok):
        """`marked` carries a mark, `plain` does not, and the stems agree.

        The mark is butted straight onto its word -- the gutter adds no
        separation, so the distance is the font's own and pdftotext reports
        "*PSTEM" as ONE word.  So the mark is not located, it is measured:
        the stems line up (right edges agree, the stems being identical)
        and the marked word starts further left by exactly the mark it
        carries.  Both halves are needed.  Right edges alone would pass a
        stack with no gutter at all if the stems happened to be equal, and
        the left-edge difference alone would pass a stack that hung the
        mark but lost the alignment.
        """
        out = [check(abs(marked.x1 - plain.x1) < TOL,
                     f"{tok}: the stems line up "
                     f"({marked.x1:.2f} vs {plain.x1:.2f})"),
               check(plain.x0 - marked.x0 > TOL,
                     f"{tok}: the mark hangs outside the column "
                     f"({plain.x0 - marked.x0:.2f}pt)")]
        return out

    # the probe: one marked alternative, one bare, same stem
    probe = stems("PSTEM", 2)
    r.append(aligned(probe, "PSTEM"))
    r += hangs(probe[1], probe[0], "PSTEM")
    # A hung mark takes exactly the room a typed one takes.  The gutter adds
    # no separation of its own -- the distance between a mark and its word
    # is the font's, and aligning the OTHER rows to it must not change it.
    # Had the first version's \JdgSep survived, this is the assertion that
    # would have caught it: the hung advance would exceed the typed one by
    # that length.  Measured as a difference of widths, so nothing here
    # needs to know what an asterisk is worth.
    typed = p.find("*QSTEM").x1 - p.find("*QSTEM").x0 \
        - (p.find("QSTEM").x1 - p.find("QSTEM").x0)
    hung = probe[0].x0 - probe[1].x0
    r.append(check(abs(typed - hung) < TOL,
                   f"a hung mark takes the room a typed one takes "
                   f"({hung:.2f}pt hung, {typed:.2f}pt typed)"))

    # two marks of different widths: the gutter takes the widest, so the
    # stems still line up and the wider mark reaches further left
    wide = stems("WSTEM", 3)
    r.append(aligned(wide, "WSTEM"))
    r += hangs(wide[0], wide[2], "*WSTEM")
    r += hangs(wide[1], wide[2], "??WSTEM")
    r.append(check(wide[1].x0 < wide[0].x0 - TOL,
                   f"the wider mark reaches further left "
                   f"({wide[1].x0:.2f} vs {wide[0].x0:.2f})"))

    # no mark anywhere: the split layout must not engage.  Compared against
    # the same stack with alignment off, so a stray gutter shows up as a
    # difference between the two rather than as an absolute coordinate.
    plain = stems("NSTEM", 2)
    off = stems("OSTEM", 2)
    r.append(aligned(plain, "NSTEM"))
    on_gap = plain[0].x0 - p.find("PLAINL").x1
    off_gap = off[0].x0 - p.find("OFFL").x1
    r.append(check(abs(on_gap - off_gap) < TOL,
                   f"an unmarked stack is unmoved by the option "
                   f"({on_gap:.2f}pt on, {off_gap:.2f}pt off)"))

    # the report this case came from: the contrasted words line up, and the
    # star is on the row the source put it on -- (a) marks the second
    # alternative, (b) the first, so a fix that hung the mark on a fixed
    # row would pass one and fail the other
    fr = sorted((w for w in p.words
                 if w.text in ("est", "sont", "*est", "*sont")), key=cy)
    r.append(check([w.text for w in fr] == ["est", "*sont", "*est", "sont"],
                   f"(a) marks sont and (b) marks est; got "
                   f"{[w.text for w in fr]}"))
    if len(fr) == 4:
        # "est" and "sont" differ in width, so the stems cannot be compared
        # on either edge.  What separates the two layouts is the mark: hung,
        # the marked word starts a mark-width LEFT of the unmarked one;
        # unaligned, the two start at the very same x and this is 0.
        for i, (marked, plain) in enumerate(((fr[1], fr[0]), (fr[2], fr[3]))):
            r.append(check(plain.x0 - marked.x0 > TOL,
                           f"({'ab'[i]}) the star hangs left of the column "
                           f"({plain.x0 - marked.x0:.2f}pt)"))

    # \AltJdgTuck: the marked stack moves toward its opening brace by the
    # length given, and only when a mark is there.  Measured as a
    # DIFFERENCE between two stacks set at 0pt and 6pt, so the assertion
    # survives a change of default and still pins the sign: tucking must
    # move the stack left, not right.
    def offset(stem, sentinel):
        return sorted(p.find_all(stem), key=cy)[0].x0 - p.find(sentinel).x1

    tuck = offset("TZSTEM", "TZEROL") - offset("TSSTEM", "TFIVEL")
    r.append(check(abs(tuck - 5.0) < TOL,
                   f"a marked stack tucks by \\AltJdgTuck ({tuck:.2f}pt for "
                   f"a 5pt tuck)"))
    # the default is in force and is not 0pt: the probe stack, set at the
    # package default, sits nearer its sentinel than the 0pt stack does
    r.append(check(offset("PSTEM", "PROBEL") < offset("TZSTEM", "TZEROL") - TOL,
                   f"the default tuck is applied "
                   f"({offset('PSTEM', 'PROBEL'):.2f} vs "
                   f"{offset('TZSTEM', 'TZEROL'):.2f}pt from the sentinel)"))
    # an unmarked stack ignores the tuck entirely -- 6pt set, nothing moved
    r.append(check(abs(offset("UZSTEM", "UZEROL")
                       - offset("NSTEM", "PLAINL")) < TOL,
                   f"an unmarked stack does not tuck "
                   f"({offset('UZSTEM', 'UZEROL'):.2f} vs "
                   f"{offset('NSTEM', 'PLAINL'):.2f}pt)"))

    # the \\* regression, counted: three of the four stars in this document
    # sit on an alternative that is not the first of its stack
    # seven words carry a mark: six in stacks (four of them not the first
    # alternative of theirs, which is where the separator ate them) and the
    # typed yardstick.  Counted rather than located, because that failure
    # removes a mark instead of moving one.
    r.append(check(len(p.find_all("*")) == 7,
                   f"every judgment mark survived the row separator; "
                   f"found {len(p.find_all('*'))} of 7"))

    # the default tuck is below the warning threshold.  Asserted here, in
    # the case that uses the default throughout, because a warning at the
    # default would be a warning in every document that never touches the
    # knob -- alttuck.tex pins the warning firing, this pins it not firing.
    r.append(check("is deeper than the brace"
                   not in re.sub(r"\n\(linguexx\)\s*", " ",
                                 getattr(p, "log", "")),
                   "the default \\AltJdgTuck does not warn"))
    return r


def a_altg_phantomalign(p: Page):
    r"""A judgment in an \altg stack hangs left -- on the OBJECT tier only.

    The asymmetry is the point and is asserted in both directions.  A
    judgment is a claim about the object language; a gloss is a translation
    of it and is not itself grammatical or not, so a mark in a gloss
    alternative is left exactly where it was typed.  Hanging it there would
    look like a fix and would be saying something false.

    OGLOSS also pins the thing an earlier comment in linguexx.sty got
    wrong: that the two tiers must keep one width, so a gutter on the
    object tier alone would tear them apart.  They need not -- the gloss
    cell's indent is derived from the object emit's own width -- and the
    gloss column here stays a column while the object stack widens.
    """
    r = []

    def cy(w):
        return (w.y0 + w.y1) / 2

    def stems(tok, n):
        ws = sorted(p.find_all(tok), key=cy)
        if len(ws) != n:
            raise AssertionError(f"expected {tok} {n} times, got {len(ws)}: {ws}")
        return ws

    def lined_up(ws, tok, edge="x1"):
        vals = [getattr(w, edge) for w in ws]
        spread = max(vals) - min(vals)
        return check(spread < TOL,
                     f"{tok} share one {edge} ({spread:.2f}pt spread)")

    # --- object tier marked: the stems line up, the mark leaves the column.
    # The mark is butted onto its word (no separation of the gutter's own,
    # see \__lxp_alt_setstack:), so pdftotext reports "*OSTEM" as one word
    # and the mark is measured rather than located: same right edge as the
    # unmarked rows, left edge further out by the mark it carries.
    obj = stems("OSTEM", 3)
    r.append(lined_up(obj, "OSTEM"))
    marked = [w for w in obj if w.text.startswith("*")]
    r.append(check(len(marked) == 1 and marked[0].text == "*OSTEM",
                   f"the object row keeps its mark; got {[w.text for w in obj]}"))
    if len(marked) == 1:
        plain = [w for w in obj if w is not marked[0]][0]
        r.append(check(plain.x0 - marked[0].x0 > TOL,
                       f"the object mark hangs outside the column "
                       f"({plain.x0 - marked[0].x0:.2f}pt)"))
    # ... and the gloss column follows it rather than parting company
    r.append(lined_up(stems("OGLOSS", 3), "OGLOSS", "x0"))

    # --- gloss tier marked: the mark stays INSIDE the alternative, so the
    # marked row is the one row whose glyphs do not line up with the others
    ggl = stems("GGLOSS", 3)
    marked = [w for w in ggl if w.text.startswith("*")]
    r.append(check(len(marked) == 1 and marked[0].text == "*GGLOSS",
                   f"a gloss mark is not hung, it stays in its word; "
                   f"got {[w.text for w in ggl]}"))
    if len(marked) == 1:
        plain = [w for w in ggl if w is not marked[0]]
        r.append(lined_up(plain, "unmarked GGLOSS", "x0"))
        r.append(check(marked[0].x1 > plain[0].x1 + TOL,
                       f"the marked gloss is wider by its mark "
                       f"({marked[0].x1:.2f} vs {plain[0].x1:.2f})"))
    # the object tier of that same paradigm is untouched by the gloss mark
    r.append(lined_up(stems("GSTEM", 3), "GSTEM"))

    # --- no mark on either tier: nothing moves.  Measured against the same
    # paradigm with alignment off, so a stray gutter shows up as a
    # difference between the two rather than as an absolute coordinate.
    non, foff = stems("NSTEM", 2), stems("FSTEM", 2)
    r.append(lined_up(non, "NSTEM"))
    on_gap = non[0].x0 - p.find("NDET").x1
    off_gap = foff[0].x0 - p.find("FDET").x1
    r.append(check(abs(on_gap - off_gap) < TOL,
                   f"an unmarked paradigm is unmoved by the option "
                   f"({on_gap:.2f}pt on, {off_gap:.2f}pt off)"))

    # --- a solo \altg is an object stack too
    solo = stems("SSTEM", 2)
    r.append(lined_up(solo, "SSTEM"))
    smarked = [w for w in solo if w.text.startswith("*")]
    r.append(check(len(smarked) == 1,
                   f"a solo stack keeps its mark; got {[w.text for w in solo]}"))
    if len(smarked) == 1:
        splain = [w for w in solo if w is not smarked[0]][0]
        r.append(check(splain.x0 - smarked[0].x0 > TOL,
                       f"a solo stack hangs its mark too "
                       f"({splain.x0 - smarked[0].x0:.2f}pt)"))
    return r


def a_alttuck(p: Page):
    r"""\AltJdgTuck reports a tuck deeper than the brace, once, and obeys it.

    The knob is deliberately unclamped -- it is a tunable like
    \AltBraceRaise, and one that silently ignores its value would be worse
    than one that does as it is told.  What is not acceptable is that too
    deep a value fails SILENTLY, so the package warns.  Three things have
    to hold at once: the default says nothing, an unmarked stack says
    nothing however absurd the length, and a deep one is reported exactly
    once no matter how many stacks are affected.
    """
    r = []
    # TeX wraps a package warning at the line width and indents the
    # continuations under "(linguexx)", so any phrase long enough to be
    # worth matching is split across lines in the file.  Flatten first.
    log = re.sub(r"\n\(linguexx\)\s*", " ", getattr(p, "log", ""))
    fired = log.count("is deeper than the brace it tucks into")

    r.append(check(fired == 1,
                   f"a deep tuck is reported exactly once; found {fired}"))
    # it names the offending value, so the log says which stack to look at
    r.append(check("18.0pt" in log,
                   "the warning names the value that triggered it"))
    # ... and names the threshold it was measured against
    r.append(check("AltBraceWidth" in log and "AltBraceSep" in log,
                   "the warning names the lengths that set the threshold"))
    # the SECOND deep stack does not report again
    r.append(check("22.0pt" not in log,
                   "the warning does not repeat for a later stack"))
    # the value is used, not corrected: the deep stack really is pulled in,
    # so its stem sits nearer its sentinel than the default stack's does
    def offset(stem, sentinel):
        return p.find(stem).x0 - p.find(sentinel).x1

    r.append(check(offset("DSTEM", "DEEPL") < offset("*QSTEM", "QUIETL") - TOL,
                   f"the value is obeyed, not clamped "
                   f"({offset('DSTEM', 'DEEPL'):.2f} vs "
                   f"{offset('*QSTEM', 'QUIETL'):.2f}pt from the sentinel)"))
    return r


def a_altspoken(p: Page):
    r"""\SetAltSpoken: the connector between spoken alternatives.

    Everything here is invisible on the page -- the /Alt strings are the
    whole subject -- so the geometry is not the check; the exact strings
    are.  They are matched WHOLE rather than by substring, because the
    interesting failures are all about spacing and punctuation ("aa orbb",
    "dd, ee, ou ff") and a substring test passes straight through them.
    """
    r = []
    alts = struct_alts(getattr(p, "raw", b""))
    got = sorted(set(alts))

    def has(s, why):
        r.append(check(s in alts, f"{why}: expected {s!r}, got {got}"))

    # the default, untouched by the hook existing at all
    has("aa or bb", "default connector, two alternatives")
    has("cc, dd, or ee", "default keeps the serial comma at three")
    # the word is replaced, and the author writes it bare
    has("ff ou gg", "\\SetAltSpoken{ou} replaces the connector")
    # the point of the whole exercise: French does not take the comma
    has("hh, ii ou jj", "and drops the serial comma at three")
    has("kk, ll oder mm", "German likewise")
    # the starred form must reproduce the default exactly
    has("nn, oo, or pp", "\\SetAltSpoken*{or} restores the default form")
    # the punctuation itself is settable
    has("qq; rr y ss", "the optional argument replaces the punctuation")
    # \altg shares the builder, on both tiers of the gloss
    has("tt ou uu", "the setting reaches \\altg (object tier)")
    has("vv ou ww", "the setting reaches \\altg (gloss tier)")
    # a word written with spaces is the same setting, not a wider one
    has("c1 ou d1", "\\SetAltSpoken{ ou } is the same setting as {ou}")
    r.append(check("c1  ou  d1" not in alts,
                   f"the padded form does not double the spaces (got {got})"))
    has("e1; f1 y g1", "the optional argument is trimmed too")
    # an empty connector gives ONE space, not the two of naive spacing
    has("a1 b1", "an empty connector collapses to a single space")
    r.append(check("a1  b1" not in alts,
                   f"and not to two spaces (got {got})"))
    # and it is a setting, not a table: it respects grouping
    has("xx, yy, or zz", "the setting does not leak past its group")
    # a leak would show up as the French form surviving to the last example
    r.append(check("xx, yy ou zz" not in alts,
                   f"no French connector after the group closed (got {got})"))
    # Every string above can be exactly right while the element carrying it
    # wraps nothing, and that is not hypothetical: with the pre-2026-09-17
    # .sty this case builds 13 such elements under lualatex and every
    # assertion above still passes.  struct_alts() reads the strings out of
    # the raw bytes and never asks what they are attached to -- which is
    # precisely how the defect reached a release.  This case is named for
    # the spoken forms, so it is the one that should have said so first.
    orphans = struct_empty_alts(p.path)
    r.append(check(not orphans,
                   f"every spoken /Alt wraps the content it speaks for; "
                   f"these wrap nothing: {orphans}"))
    return r


def a_altkids(p: Page):
    r"""Every spoken /Alt wraps the content it speaks for.

    The mutation this kills is the one that shipped: build the stack box
    before opening its Span -- which is what \__lxp_alt_print: and
    \__lxp_altg_emit: did until 2026-09-17 -- and under lua mode every one
    of these elements comes back with an empty /K.  Nothing else in the
    suite says so: the ink is identical, veraPDF passes all three profiles
    (an /Alt that is present and well-formed satisfies them however little
    it wraps), and struct_alts() still finds every string.

    Runs on all three engines deliberately, and the reason is stronger than
    it was first written.  The claim used to be that pdflatex and xelatex
    pass with the defect present, generic mode writing its marked content at
    the point of use, and that only lualatex fails.  That is true of the
    three flat stacks and FALSE of ALTKLPZG: with the pre-fix .sty all three
    engines leave that element wrapping nothing a reader can hear, because
    the \lpzg Spans built into the box are parented where the box was
    filled, not where it is used.  It took an oracle that resolves the tree
    to see it (struct_empty_alts); counting /MCID in the object sees three
    empty marked-content sequences and calls them kids.
    """
    r = []
    pairs = struct_alt_kids(p.path)
    got = {t: k for t, k in pairs}
    for want in ("aa or bb", "cc or *dd", "singular or plural",
                 "tt or uu", "vv or ww", "kk or ll"):
        r.append(check(want in got,
                       f"{want!r} reached the structure tree; "
                       f"got {sorted(got)}"))
    # DOMINATED, and kept deliberately.  Measured on 2026-09-18 over 27
    # builds (nine tagged cases x three engines, with the .sty both fixed
    # and reverted to ad113db^): this check uniquely caught NOTHING, while
    # struct_empty_alts below uniquely caught two -- ALTKLPZG under
    # pdflatex and xelatex, where the element wraps three EMPTY marked
    # content sequences and counting /MCID entries calls them three kids.
    # It stays because it is the one oracle here that is ours rather than
    # upstream's, so the two fail differently; it is not a second opinion
    # on anything, and a mutation that kills it kills the other as well.
    empty = sorted(t for t, k in pairs if k == 0)
    r.append(check(not empty,
                   f"every /Alt element wraps marked content; these wrap "
                   f"nothing: {empty}"))
    # The same question put to the LaTeX team's own tool, which resolves /K
    # the way a consumer does rather than by counting /MCID in one object.
    stale = struct_empty_alts(p.path)
    r.append(check(not stale,
                   f"show-pdf-tags: every /Alt element wraps content; "
                   f"these wrap nothing: {stale}"))
    # ALTKLPZG: the \lpzg written into an alternative keeps its own
    # expansion.  This is what a blind \tag_mc_reset_box:N would have cost,
    # so it is asserted rather than assumed.
    r.append(check("singular" in struct_exps(inflated(getattr(p, "raw", b""))),
                   "the \\lpzg inside an \\altn alternative keeps its /E"))
    return r
