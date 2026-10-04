r"""Movement arrows: \mvfrom and \mvto.

An arrow is vector ink and nothing else, so the page checks here measure a
rendering (ink_bbox) and never the text layer; the text layer only says
where the words at its two ends are.
"""

from suite.check import check
from suite.geometry import ink_bbox
from suite.pdf import Page
from suite.structure import painted_marked_content, struct_alts


def _mid(w):
    return (w.x0 + w.x1) / 2


def _ink(pdf, x0, y0, x1, y1, page=1):
    """ink_bbox, or None where there is no ink at all."""
    try:
        return ink_bbox(pdf, x0, y0, x1, y1, page=page)
    except AssertionError:
        return None


def a_movement(p: Page):
    r"""The arrow: where it is, which way it points, and the room it takes.

    Every check below is about something an exit code cannot see and a
    coordinate alone does not settle: an arrow drawn backwards, or at one
    level for two nested movements, or into the line underneath, compiles
    and sits roughly where it should.
    """
    r = []
    f = p.find
    land, base, nxt = f("LANDA"), f("BASEA"), f("MVNEXT")
    arrow = _ink(p.path, land.x0, land.y1, base.x1, nxt.y0 - 0.3)
    r.append(check(arrow is not None,
                   "an arrow is drawn under MVPLAIN's line"))
    if arrow is None:
        return r
    # It runs from the middle of one word to the middle of the other.  The
    # head is wider than the stroke, hence the tolerance at the left end.
    r.append(check(abs(arrow[0] - _mid(land)) < 2.5
                   and abs(arrow[2] - _mid(base)) < 1.0,
                   f"from the middle of BASEA to the middle of LANDA "
                   f"(ink {arrow[0]:.1f}..{arrow[2]:.1f}, middles "
                   f"{_mid(land):.1f}, {_mid(base):.1f})"))
    # The direction.  The head is at the landing site: under LANDA the ink
    # is as wide as an arrowhead, under BASEA as wide as the stroke.
    head = _ink(p.path, _mid(land) - 4, land.y1, _mid(land) + 4, arrow[3] - 1)
    tail = _ink(p.path, _mid(base) - 4, base.y1, _mid(base) + 4, arrow[3] - 1)
    if head and tail:
        hw, tw = head[2] - head[0], tail[2] - tail[0]
        r.append(check(hw > 2.0 and tw < 1.0,
                       f"the head is at the landing site, LANDA "
                       f"(ink {hw:.2f}pt wide under it, {tw:.2f}pt under "
                       f"BASEA)"))
    else:
        r.append(check(False, f"both ends have a vertical ({head}, {tail})"))
    # The room.  The line after an arrow is pushed down, and by enough that
    # the arrow stays clear of it; MVCTRL is the same two lines without one.
    with_arrow = nxt.y0 - f("MVPLAIN").y0
    without = f("MVCTRLNEXT").y0 - f("MVCTRL").y0
    r.append(check(with_arrow > without + 3.0,
                   f"the line after an arrow is pushed down to make room "
                   f"({with_arrow:.1f}pt between the lines, {without:.1f}pt "
                   f"without an arrow)"))
    r.append(check(arrow[3] < nxt.y0,
                   f"and the arrow stays clear of it (ink ends at "
                   f"{arrow[3]:.1f}, the next line starts at {nxt.y0:.1f})"))
    # And past it, which the line above cannot show: that one is a new
    # example, with a skip before it that hides a strut ending right at the
    # horizontal.  The next sub-example has no skip, so it is set \lineskip
    # under whatever the strut says -- a point from the arrow, when the
    # strut stopped at it.  The words keep the distance a further level
    # would, so it is held against the step between two nested arrows.
    step = None
    mid = (f("INL").x1 + f("INB").x0) / 2
    nested = _ink(p.path, mid - 0.5, f("INL").y1, mid + 0.5, f("CHW").y0 - 1)
    if nested:
        step = nested[3] - nested[1]
    # The horizontal is found in a thin column between its two words, as
    # the first ink met coming from them: whatever the next line puts in
    # that column is further on, so it cannot be taken for the arrow.
    def clearance(words, near, far, other):
        mid = (words[0].x1 + words[1].x0) / 2
        col = _ink(p.path, mid - 0.5, min(near, far), mid + 0.5,
                   max(near, far))
        if not col:
            return None
        if far > near:
            bar = col[1] + 0.6
            ink = _ink(p.path, other.x0, bar, other.x1, far)
            return ink and ink[1] - bar
        bar = col[3] - 0.6
        ink = _ink(p.path, other.x0, far, other.x1, bar)
        return ink and bar - ink[3]

    def shown(v):
        return "none" if v is None else f"{v:.2f}pt"

    kl, kb, kn = f("KLAND"), f("KBASE"), f("KNEXT")
    gap = clearance((kl, kb), kl.y1, kn.y1, kn)
    r.append(check(step is not None and gap is not None
                   and gap > 0.8 * step,
                   f"the next sub-example keeps clear of an arrow above it "
                   f"(capitals {shown(gap)} under the horizontal; a step "
                   f"is {shown(step)})"))
    hl, hb, hp = f("HLAND"), f("HBASE"), f("KPREV")
    gap = clearance((hl, hb), hl.y0, hp.y0, hp)
    r.append(check(step is not None and gap is not None
                   and gap > 0.8 * step,
                   f"and the one before keeps clear of an arrow below it "
                   f"(capitals {shown(gap)} over the horizontal; a step "
                   f"is {shown(step)})"))
    # Nesting.  Between INL and INB both horizontals pass, one level apart;
    # between OUTL and INL only the outer one does.
    below = f("CHW").y0 - 1
    mid = (f("INL").x1 + f("INB").x0) / 2
    both = _ink(p.path, mid - 0.5, f("INL").y1, mid + 0.5, below)
    mid = (f("OUTL").x1 + f("INL").x0) / 2
    outer = _ink(p.path, mid - 0.5, f("INL").y1, mid + 0.5, below)
    if both and outer:
        r.append(check(both[3] - both[1] > 3.0,
                       f"an arrow over a stretch holding another goes a "
                       f"level further out ({both[3] - both[1]:.2f}pt "
                       f"between the two horizontals)"))
        r.append(check(abs(outer[3] - both[3]) < 0.5,
                       f"and it is the outer one that is lower "
                       f"({outer[3]:.2f} vs {both[3]:.2f})"))
    else:
        r.append(check(False, f"both nested arrows are drawn "
                              f"({both}, {outer})"))
    # A chain: CHMID is where one arrow lands and the next one leaves.  The
    # two meet it side by side, with a gap in the middle, instead of
    # running down one line where the reader cannot tell them apart.
    # The centre is looked at below the arrowhead, whose barb reaches a
    # fraction of a point past the middle of the word.
    m, nx = f("CHMID"), f("MVPREV")
    left = _ink(p.path, _mid(m) - 3.5, m.y1, _mid(m) - 1.0, nx.y0 - 1)
    right = _ink(p.path, _mid(m) + 1.0, m.y1, _mid(m) + 3.5, nx.y0 - 1)
    centre = right and _ink(p.path, _mid(m) - 0.5, right[1] + 5.0,
                            _mid(m) + 0.5, nx.y0 - 1)
    r.append(check(left is not None and right is not None and centre is None,
                   f"a word shared by two movements has their two ends side "
                   f"by side (left {left}, right {right}, centre {centre})"))
    # And the two are on one level.  They only share a word, which is not
    # a stretch holding another, so neither steps out: each horizontal is
    # measured in a column just inside its own end at CHW or CHEND, past
    # that end's vertical, and the two run at one depth.
    w, e = f("CHW"), f("CHEND")
    first = _ink(p.path, w.x1 + 2.0, m.y1, w.x1 + 3.0, nx.y0 - 1)
    second = _ink(p.path, e.x0 - 3.0, m.y1, e.x0 - 2.0, nx.y0 - 1)
    r.append(check(first is not None and second is not None
                   and abs(first[3] - second[3]) < 0.3,
                   f"the two links of a chain are on one level "
                   f"(horizontals at {first and round(first[3], 2)} and "
                   f"{second and round(second[3], 2)})"))
    # In a gloss the arrow goes above the object line: below, it would cut
    # through the gloss tier.
    g, prev, tier = f("GLAND"), f("MVPREV"), f("GTIER")
    r.append(check(_ink(p.path, _mid(g) - 2, prev.y1 + 0.5,
                        _mid(g) + 2, g.y0 + 1) is not None,
                   "in a gloss the arrow is drawn above the object line"))
    r.append(check(_ink(p.path, _mid(g) - 1, g.y1, _mid(g) + 1,
                        tier.y0) is None,
                   "and not between the object line and the gloss tier"))
    # [above] outside a gloss.
    u = f("ULAND")
    r.append(check(_ink(p.path, _mid(u) - 2, tier.y1 + 1,
                        _mid(u) + 2, u.y0 + 1) is not None
                   and _ink(p.path, _mid(u) - 2, u.y1, _mid(u) + 2,
                            f("MVLONE").y0 - 1) is None,
                   "[above] puts a plain example's arrow above its line"))
    # An end with no partner draws nothing, and says why.  The next
    # example's \mvfrom{z} is not its partner: labels are per example, so
    # that (a) can be used in every one of them.
    lone, two = f("LONELY"), f("LONETWO")
    r.append(check(_ink(p.path, lone.x0, lone.y1, lone.x1,
                        lone.y1 + 8) is None
                   and _ink(p.path, two.x0, two.y1, two.x1,
                            two.y1 + 8) is None,
                   "an end with no partner in its own example draws "
                   "nothing, even with one in the next example"))
    r.append(check("\\mvto{z} has no partner" in p.log
                   and "\\mvfrom{z} has no partner" in p.log,
                   "and the log says so, naming both"))
    # The strut is the floor of an end, not the ink: the arrow under DOG,
    # which has no descender, starts where one under "gypsy" would, below
    # the descenders.  In the column of the "g" the descender has ended
    # before that depth.
    d, g, low = f("DOG"), f("gypsy."), f("MVLEVEL")
    dog = _ink(p.path, _mid(d) - 1, d.y1, _mid(d) + 1, low.y0 - 1)
    tail = _ink(p.path, g.x0, g.y0, g.x0 + 4, low.y0 - 1)
    clear = dog and _ink(p.path, g.x0, dog[1] - 0.4, g.x0 + 4, dog[1])
    r.append(check(dog is not None and tail is not None and clear is None,
                   f"the ends start below the descenders, also under a word "
                   f"without one (DOG's end at {dog}, ink in the g's column "
                   f"just above it: {clear})"))

    # And above the line: over "ace", which has no ascender, the arrow
    # ends where it does over "fly" -- above the ascender of its "f".
    ace, fly = f("ace"), f("fly")
    top = f("MVSIDES").y1
    over = _ink(p.path, _mid(ace) - 2, top, _mid(ace) + 2, ace.y0 + 2)
    clear = over and _ink(p.path, fly.x0, over[3], fly.x0 + 2.5,
                          over[3] + 0.4)
    r.append(check(over is not None and clear is None,
                   f"an arrow above starts above the ascenders, also over a "
                   f"word without one (its end over 'ace' at {over}, ink in "
                   f"the f's column just under that: {clear})"))

    def horizontal(land, base):
        """How far below its line an arrow's horizontal runs: the first
        ink under the gap between its two words."""
        mid = (land.x1 + base.x0) / 2
        ink = _ink(p.path, mid - 0.5, land.y1, mid + 0.5, land.y1 + 25)
        return ink and ink[1] - land.y1

    plain = horizontal(land, base)
    level3 = horizontal(f("MLAND"), f("MBASE"))
    r.append(check(plain and level3 and 8.0 < level3 - plain < 12.0,
                   f"level=3 runs two steps further out than level 1 "
                   f"({plain}, {level3})"))
    sides = horizontal(f("SLAND"), f("TLAND"))
    r.append(check(plain and sides and abs(sides - plain) < 0.3,
                   f"an arrow above does not push one below out a level "
                   f"({sides} vs {plain})"))
    # Two lines.  The arrow still reaches the landing site on the line
    # above, straight up through the empty end of the second line; the log
    # says the room was kept on one line only.
    wl, wb = f("WLAND"), f("WBASE")
    up = _ink(p.path, _mid(wl) - 0.5, wl.y1, _mid(wl) + 0.5, wb.y1)
    r.append(check(up is not None and up[1] < wl.y1 + 4.0,
                   f"an arrow across two lines reaches the line above ({up})"))
    r.append(check("movement 'w' are on different lines" in
                   " ".join(p.log.split()),
                   "and the log says the ends are on different lines"))
    # Paragraph start: the mark leaves vertical mode rather than being put
    # on the page as a line of its own.
    r.append(check(abs(f("RUNL").y0 - f("starts").y0) < 0.5,
                   "a mark can start a paragraph of running text"))
    # Two pages: nothing is drawn, rather than a line across the page.
    pb, pa = f("PBASE"), f("PAFTER")
    r.append(check(_ink(p.path, pa.x0, pb.y1, pb.x1 + 5, pb.y1 + 15,
                        page=2) is None,
                   "ends on two pages draw nothing"))
    r.append(check("movement 'p' are on different pages" in
                   " ".join(p.log.split()),
                   "and the log says why"))
    # Two passes are final: the room is reserved in the run itself, so the
    # second run does not move a word the first one measured.
    r.append(check("Movement arrows have changed" not in p.log,
                   "the second run is settled (no rerun warning)"))
    return r


def a_movement_beamer(p: Page):
    r"""One arrow per slide, drawn from that slide's own positions.

    On slide 2 the example is pushed down by the material \only<2> adds.
    The arrow must be at the same place relative to its words on both
    slides -- the same place on the PAGE would be the bug.
    """
    r = []
    lands, bases = p.find_all("BLAND"), p.find_all("BBASE")
    r.append(check(len(lands) == 2 and len(bases) == 2,
                   f"the example is on both slides (found {lands}, {bases})"))
    if len(lands) != 2:
        return r
    r.append(check(lands[1].y0 - lands[0].y0 > 5,
                   f"and slide 2 moves it down ({lands[0].y0:.1f} -> "
                   f"{lands[1].y0:.1f})"))
    boxes = []
    for i, (land, base) in enumerate(zip(lands, bases)):
        box = _ink(p.path, land.x0, land.y1, base.x1, land.y1 + 14,
                   page=i + 1)
        r.append(check(box is not None, f"slide {i + 1} has its arrow"))
        if box is None:
            return r
        boxes.append((box[0] - land.x0, box[1] - land.y1,
                      box[2] - land.x0, box[3] - land.y1))
    off = max(abs(a - b) for a, b in zip(*boxes))
    r.append(check(off < 0.3,
                   f"at one place relative to its words on both slides "
                   f"(differ by {off:.2f}pt: {boxes})"))
    r.append(check("Movement arrows have changed" not in p.log,
                   "the second run is settled"))
    return r


def a_movement_spoken(p: Page):
    r"""The spoken forms, matched whole: they are the only thing that
    carries a movement to a reader who does not see the arrow."""
    r = []
    alts = struct_alts(getattr(p, "raw", b""))
    got = sorted(alts)

    def has(s, why):
        r.append(check(alts.count(s) == 1,
                       f"{why}: expected {s!r} once, got {got}"))

    has("SPBASE (moved)", "the base position is read with the note")
    has("SPGREY (moved)", "\\textcolor is read as its text, not its colour")
    has("SPRGB (moved)", "... with a colour model too")
    has("SPDECL (moved)", "\\color is dropped from the spoken form")
    has("where it was", "spoken= replaces the base position's form")
    has("where it went", "spoken= gives the landing site one")
    has("SPFR (déplacé)", "\\SetMoveSpoken replaces the note, trimmed")
    has("SPAFTER (moved)", "and is local: the note is back after the group")
    has("SPCHAIN (moved)", "a mark nested in \\mvfrom is read as its text")
    has("SPCHB (moved)", "and is itself the base of the next movement")
    r.append(check(not any(a.startswith(("SPLAND", "SPX", "SPY", "SPZ"))
                           for a in alts),
                   f"a landing site with no spoken= has no /Alt (got {got})"))
    for tok in ("SPBASE", "SPGREY", "SPLAND", "SPFROM"):
        r.append(check(p.find(tok) is not None,
                       f"printed as written: {tok}"))
    # The arrows are decoration: what they mean is in the /Alt above.  The
    # only paint on this page is theirs, a stroke and a head each.
    tags = painted_marked_content(getattr(p, "raw", b""))
    r.append(check(len(tags) == 18 and set(tags) == {"/Artifact"},
                   f"all nine arrows are painted as artifacts (paint "
                   f"operators found in {tags})"))
    return r


def a_movement_rerun(p: Page):
    """A first run cannot draw the arrows, and says so in words latexmk
    reruns on."""
    return [check("Movement arrows have changed. Rerun" in
                  " ".join(p.log.split()).replace("(linguexx) ", ""),
                  "a first run asks for a rerun")]
