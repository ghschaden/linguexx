#!/usr/bin/env python3
r"""
linguexx regression suite.

Compiles every case in cases/ under every engine and checks assertions
against the RENDERED GEOMETRY of the resulting PDF, not merely against the
exit status.  This matters: every real bug found during development of this
package compiled with zero errors and was visible only in the coordinates
(a judgment mark that failed to hang left, a source that fell flush left
instead of flush right, a \z. that popped the wrong number of levels).

Adding a case: drop <name>.tex in this directory AND add a <name> entry to
ASSERTIONS.  Only what ASSERTIONS lists is ever run, so a case file without
an entry is dead weight; the suite refuses to run until every case file is
either wired up or declared SMOKE_ONLY (see suite_integrity).

Usage:
    python3 runtests.py                  # all cases, all engines
    python3 runtests.py -e pdflatex      # one engine
    python3 runtests.py -k gloss         # cases matching a substring
    python3 runtests.py -v               # show every assertion, not just failures

Requires: pdflatex / xelatex / lualatex, pdftotext and pdfinfo
(poppler-utils), and veraPDF on PATH as `verapdf` -- the only authoritative
oracle for PDF/UA, used by the `ua` case.
Exit status: 0 iff every assertion passed, 1 on a failing assertion,
2 on a suite-integrity problem (an unwired case file, a missing case file,
a stale KNOWN_XFAIL or PASSES key) or when no case matches -k.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINES = ["pdflatex", "xelatex", "lualatex"]
# pdflatex/judgment-align fails one assertion because pdftotext merges the
# label and the two judgment marks into a single token; the geometry is
# correct (the case passes on xe/lua).  Known pdftotext artifact, not a bug.
KNOWN_XFAIL = {"pdflatex/judgment-align"}
# LaTeX passes per case; two is enough for cross-references, which is all
# most cases need.  The `ua` case needs three: its PDF/UA validity does not
# converge until the third run under pdflatex and xelatex (lualatex gets
# there in two), and a not-yet-converged file fails veraPDF on all three
# profiles -- which would look exactly like a tagging regression.
DEFAULT_PASSES = 2
PASSES = {"ua": 3}
CASES = Path(__file__).parent / "cases"
if not CASES.is_dir():                       # flat layout: cases beside the script
    CASES = Path(__file__).parent
STY = Path(__file__).parent / "linguexx.sty"
if not STY.exists():                          # repo layout: sty at the root
    STY = Path(__file__).parent.parent / "linguexx.sty"

# Coordinates are in PostScript points, origin top-left (pdftotext -bbox).
# Tolerance for "same position": 0.5pt, far below any real layout difference
# but above the sub-point noise between engines.
TOL = 0.5


class Word:
    __slots__ = ("text", "x0", "y0", "x1", "y1")

    def __init__(self, text, x0, y0, x1, y1):
        self.text, self.x0, self.y0, self.x1, self.y1 = text, x0, y0, x1, y1

    def __repr__(self):
        return f"{self.text!r}@({self.x0:.1f},{self.y0:.1f})"


class Page:
    """The words of a PDF, queryable by content."""

    def __init__(self, words, width):
        self.words = words
        self.width = width

    def find(self, text):
        """The word for sentinel `text`.

        Exact match wins (so TIERONE does not collide with TIERONEC); if
        there is none, fall back to a unique containment match, which is how
        sentinels carrying a judgment prefix ("*JUDGEDMAIN") are found.
        """
        exact = [w for w in self.words if w.text == text]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise AssertionError(f"sentinel {text!r} is not unique: {exact}")
        hits = [w for w in self.words if text in w.text]
        if len(hits) != 1:
            raise AssertionError(
                f"expected exactly one word for {text!r}, found {len(hits)}: {hits}"
            )
        return hits[0]

    def find_all(self, text):
        return [w for w in self.words if text in w.text]

    def labels(self):
        """Example numbers like (1), (2), (i) in reading order."""
        pat = re.compile(r"^\((\d+|[ivxlc]+|x)\)$")
        return [w.text for w in self.words if pat.match(w.text)]

    def line_of(self, word):
        """All words on the same rendered line as `word`, left to right.

        pdftotext boxes are line-height, and adjacent lines' boxes can touch,
        so edge overlap is too loose.  A word of a different size on the same
        line (an \\exsource, set in \\footnotesize) has a box nested inside
        the body line's box.  Center-containment handles both: two words share
        a line iff either's vertical center lies inside the other's box.
        """
        def center(w):
            return (w.y0 + w.y1) / 2

        def same(w):
            return (word.y0 <= center(w) <= word.y1
                    or w.y0 <= center(word) <= w.y1)

        return sorted((w for w in self.words if same(w)), key=lambda w: w.x0)


def parse_pdf(pdf: Path) -> Page:
    out = subprocess.run(
        ["pdftotext", "-bbox", str(pdf), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    m = re.search(r'<page width="([\d.]+)"', out)
    width = float(m.group(1)) if m else 595.276
    words = []
    for mm in re.finditer(
        r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>',
        out,
    ):
        x0, y0, x1, y1, txt = mm.groups()
        words.append(Word(txt, float(x0), float(y0), float(x1), float(y1)))
    page = Page(words, width)
    page.raw = pdf.read_bytes()
    page.path = pdf
    return page


# ---------------------------------------------------------------------------
# Assertions.  Each returns a list of (ok: bool, description: str).
# ---------------------------------------------------------------------------

def check(cond, desc):
    return (bool(cond), desc)


def a_numbering(p: Page):
    got = p.labels()
    r = [check(got[:2] == ["(1)", "(2)"], f"main examples number (1),(2); got {got[:2]}")]
    # sub-levels: a. b. then roman i. ii.
    letters = [w.text for w in p.words if w.text in ("a.", "b.", "i.", "ii.")]
    r.append(check(letters == ["a.", "b.", "i.", "ii."],
                   f"sub-levels run a,b then i,ii; got {letters}"))
    # custom label does not step the counter: (x) then (3)
    r.append(check("(x)" in got, f"custom label (x) present; got {got}"))
    r.append(check(got[-1] == "(3)",
                   f"counter continues at (3) after custom label; got {got[-1]}"))
    return r


def a_judgment_align(p: Page):
    """The invariant: a judgment mark hangs into the margin and consumes no
    horizontal space in the text block, so text is not displaced.

    Measured on the word AFTER a common leading word, because pdftotext
    merges a hung mark with the text it precedes into a single token whose
    xMin is the mark's, not the text's.
    """
    r = []
    pairs = [
        ("JMAIN", "PMAIN", "main level"),
        ("JSUB", "PSUB", "letter level"),
        ("JROMAN", "PROMAN", "roman level"),
        ("JMANUAL", "PMANUAL", "manual \\jdg"),
    ]
    for judged, plain, where in pairs:
        wj, wp = p.find(judged), p.find(plain)
        r.append(check(abs(wj.x0 - wp.x0) < TOL,
                       f"{where}: judgment does not displace text "
                       f"({wj.x0:.2f} vs {wp.x0:.2f})"))
    # and the mark must actually protrude LEFT of the text block.  pdftotext
    # may merge the mark with the following word ("*Text") or keep it
    # separate (a \\jdg{\\dag}), so compare the leftmost non-label token of
    # the judged line against the plain line's text origin.
    label = re.compile(r"^(\(\w+\)|[a-f]\.|[ivx]+\.)$")

    def text_origin(w):
        toks = [t for t in p.line_of(w) if not label.match(t.text)]
        return min(t.x0 for t in toks)

    for judged, plain, where in pairs:
        lj = text_origin(p.find(judged))
        lp = text_origin(p.find(plain))
        r.append(check(lj < lp - 0.5,
                       f"{where}: mark hangs left of the text block "
                       f"({lj:.2f} vs {lp:.2f})"))
    # default-width guarantee: TWO narrow marks clear the sub-example
    # letter.  pdftotext merges tokens closer than ~2pt, so the letter
    # appearing as its own token with the marks to its right IS the check.
    for judged, level in [("JSUB", "letter"), ("JROMAN", "roman")]:
        line = p.line_of(p.find(judged))
        lab = [w for w in line if re.fullmatch(r"[a-f]\.|[ivx]+\.", w.text)]
        if not lab:
            r.append(check(False,
                           f"{level} level: two marks overlap the label "
                           f"(label and marks merged: {line[0].text!r})"))
            continue
        marks = [w for w in line if w.x0 > lab[0].x1 - 0.1 and "Text" in w.text]
        r.append(check(marks and marks[0].x0 > lab[0].x1,
                       f"{level} level: two marks clear the label "
                       f"(label ends {lab[0].x1:.2f}, marks at "
                       f"{marks[0].x0:.2f})" if marks else
                       f"{level} level: mark token not found right of label"))
    return r


def a_exsource(p: Page):
    r = []
    inline = p.find("SRCINLINE")
    fallback = p.find("SRCFALLBACK")
    # find the right-hand text edge from the long example's own lines
    body_right = max(w.x1 for w in p.words if w.y0 < fallback.y0 - 2)
    line = p.line_of(fallback)
    right_edge = max(w.x1 for w in line)
    r.append(check(right_edge >= body_right - 2.0,
                   f"fallback source is flush right ({right_edge:.1f} vs text edge {body_right:.1f})"))
    # the inline one must sit on the same line as its example text, at the right
    inline_line = p.line_of(inline)
    r.append(check(len(inline_line) > 2,
                   "inline source shares the line with the example text"))
    r.append(check(inline.x0 > p.width / 2,
                   f"inline source sits in the right half ({inline.x0:.1f})"))
    return r


def a_zpop(p: Page):
    r = []
    aaa, bbb = p.find("AAA"), p.find("BBB")
    ccc, ddd = p.find("CCC"), p.find("DDD")
    eee, fff = p.find("EEE"), p.find("FFF")
    ggg = p.find("GGG")
    # AAA/BBB at letter level; CCC/DDD one deeper
    r.append(check(abs(aaa.x0 - bbb.x0) < TOL, "AAA and BBB share the letter level"))
    r.append(check(ccc.x0 > aaa.x0 + 2, "CCC is indented deeper than AAA"))
    r.append(check(abs(ccc.x0 - ddd.x0) < TOL, "CCC and DDD share the roman level"))
    # after one \z., EEE must be back at the LETTER level (the whole point)
    r.append(check(abs(eee.x0 - aaa.x0) < TOL,
                   f"\\z. pops exactly one level: EEE at letter level "
                   f"({eee.x0:.2f} vs {aaa.x0:.2f}, roman was {ccc.x0:.2f})"))
    # and it must be item c.
    letters = [w.text for w in p.words if w.text in ("a.", "b.", "c.")]
    r.append(check("c." in letters, f"the popped item is lettered c.; got {letters}"))
    # the second \z. fires at the LETTER level and therefore ENDS the
    # example: FFF is prose at the OUTER margin, flush with the labels
    margin0 = p.find("(1)").x0
    r.append(check(abs(fff.x0 - margin0) < TOL,
                   f"second \\z. leaves the example (FFF at outer margin: "
                   f"{fff.x0:.2f} vs {margin0:.2f})"))
    # main-level \z. with text on the same line: a CONTINUATION, set flush
    # left at the outer margin (same x as the example labels), not indented
    margin = p.find("(1)").x0
    r.append(check(abs(ggg.x0 - margin) < TOL,
                   f"continuation after \\z. is flush left at the margin "
                   f"({ggg.x0:.2f} vs margin {margin:.2f})"))
    # ... and closed as its own paragraph: JJJ lands on a later line
    jjj = p.find("JJJ")
    r.append(check(jjj.y0 > ggg.y0 + 2,
                   f"continuation is closed as a paragraph "
                   f"(JJJ y {jjj.y0:.1f} vs {ggg.y0:.1f})"))
    # ... and the NEXT source paragraph is indented per class
    r.append(check(jjj.x0 > margin + 5,
                   f"paragraph after the continuation is indented "
                   f"({jjj.x0:.2f} vs margin {margin:.2f})"))
    # \z. followed by a blank line: the next paragraph is ordinary and
    # indented, nothing flush-left is injected
    kkk = p.find("KKK")
    r.append(check(abs(kkk.x0 - jjj.x0) < TOL,
                   f"blank line after \\z. yields an indented paragraph "
                   f"({kkk.x0:.2f} vs {jjj.x0:.2f})"))
    # counter survived
    r.append(check(p.labels() == ["(1)", "(2)", "(3)", "(4)"],
                   f"counter intact across \\z.; got {p.labels()}"))
    return r


def a_gloss(p: Page):
    r = []
    # two-tier: columns x-aligned pairwise
    for top, below in [("AAA", "aaa"), ("BBB", "bbb"), ("CCC", "ccc")]:
        wt, wb = p.find(top), p.find(below)
        r.append(check(abs(wt.x0 - wb.x0) < TOL,
                       f"gloss column {top}/{below} aligned ({wt.x0:.2f} vs {wb.x0:.2f})"))
    # four-tier: all four tiers of column 1 share an x origin
    col1 = [p.find(t) for t in ("TIERONE", "tiertwo", "TIERTHREE", "tierfour")]
    xs = [w.x0 for w in col1]
    r.append(check(max(xs) - min(xs) < TOL,
                   f"four tiers share one column origin (spread {max(xs)-min(xs):.2f}pt)"))
    r.append(check(len({round(w.y0) for w in col1}) == 4,
                   "four tiers occupy four distinct lines"))
    # braced group is ONE column: BRACEDX/BRACEDY on one line, and the tier
    # below starts at BRACEDX's x
    bx, by = p.find("BRACEDX"), p.find("BRACEDY")
    b2 = p.find("bracedtwo")
    r.append(check(abs(bx.y0 - by.y0) < 2.0, "braced group stays on one line"))
    r.append(check(abs(bx.x0 - b2.x0) < TOL,
                   f"braced group is one column ({bx.x0:.2f} vs {b2.x0:.2f})"))
    # tier 4 must be italic: check it rendered (font check is done separately)
    r.append(check(p.find("tierfour").x0 > 0, "tier 4 (custom font) renders"))
    # unequal tiers: the surplus word is set, with nothing under it
    kkk = p.find("KKK")
    below_kkk = [w for w in p.words
                 if abs(w.x0 - kkk.x0) < TOL and w.y0 > kkk.y0 + 2
                 and w.y0 < kkk.y0 + 20]
    r.append(check(len(p.find_all("KKK")) == 1, "unequal tiers: surplus word is set"))
    r.append(check(not below_kkk,
                   f"unequal tiers: cell under the surplus word is empty; found {below_kkk}"))
    return r


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


def a_phantomalign(p: Page):
    """Phantom bracket alignment (opt-in).  A gloss word under a bracketed
    object word is padded so its first real glyph sits under the object
    word's first real glyph.  Each probe pairs object "<marks><STEM>" with
    gloss "<STEM>": when aligned, the two share their trailing STEM glyphs,
    so their RIGHT edges coincide; the column origin is the object token's
    left edge (the mark).  Off, the gloss falls back to the column origin."""
    r = []

    def obj(stem_token):   # object token, e.g. "[Aaa"
        return p.find(stem_token)

    # (1) ON, single bracket: gloss stem ends under object stem (right edges
    # coincide), and its origin is shifted right of the column origin.
    o1, g1 = obj("[Aaa"), p.find("Aaa")
    r.append(check(abs(g1.x1 - o1.x1) < TOL,
                   f"ON: gloss stem ends under object stem "
                   f"(right edges {g1.x1:.2f} vs {o1.x1:.2f})"))
    shift1 = g1.x0 - o1.x0
    r.append(check(shift1 > 1.0,
                   f"ON: gloss is shifted right past the bracket "
                   f"(shift {shift1:.2f}pt)"))

    # (2) ON, three leading marks "*([": right edges still coincide, and the
    # shift is strictly larger than the single-bracket shift.
    o2, g2 = obj("*([Ddd"), p.find("Ddd")
    r.append(check(abs(g2.x1 - o2.x1) < TOL,
                   f"ON: gloss aligns under stem past 3 marks "
                   f"(right edges {g2.x1:.2f} vs {o2.x1:.2f})"))
    shift2 = g2.x0 - o2.x0
    r.append(check(shift2 > shift1 + 1.0,
                   f"ON: three marks shift more than one bracket "
                   f"({shift2:.2f} vs {shift1:.2f})"))

    # (3) ON, \footnotesize gloss tier: the shift equals the full-size
    # bracket shift of (1) -- the phantom is set in the object font, so a
    # smaller gloss tier does not change the padding.
    o3, g3 = obj("[Ccc"), p.find("Ccc")
    shift3 = g3.x0 - o3.x0
    r.append(check(abs(shift3 - shift1) < TOL,
                   f"ON: footnotesize gloss uses the full-size bracket shift "
                   f"({shift3:.2f} vs {shift1:.2f})"))

    # (4) OFF: the gloss stem returns to the column origin (under the mark),
    # so its LEFT edge meets the object token's left edge and its right edge
    # is short of the object stem by the bracket width.
    o4, g4 = obj("[Bbb"), p.find("Bbb")
    r.append(check(abs(g4.x0 - o4.x0) < TOL,
                   f"OFF: gloss sits at the column origin "
                   f"(left edges {g4.x0:.2f} vs {o4.x0:.2f})"))
    r.append(check(o4.x1 - g4.x1 > 1.0,
                   f"OFF: gloss stem is short of the object stem by the "
                   f"bracket width ({g4.x1:.2f} vs {o4.x1:.2f})"))

    # (5) manual \GlossPhantom, automatic alignment still OFF, over a
    # macro-wrapped bracket the auto-scanner cannot see: the gloss stem is
    # nonetheless pushed right so its right edge lands under the object
    # stem's right edge.
    o5, g5 = obj("[Kkk"), p.find("Kkk")
    r.append(check(abs(g5.x1 - o5.x1) < TOL,
                   f"\\GlossPhantom: gloss stem ends under object stem "
                   f"(right edges {g5.x1:.2f} vs {o5.x1:.2f})"))
    r.append(check(g5.x0 > o5.x0 + 1.0,
                   f"\\GlossPhantom: gloss is shifted right past the bracket "
                   f"(shift {g5.x0 - o5.x0:.2f}pt)"))

    # (6) auto ON over a macro-wrapped bracket: no automatic phantom fires, so
    # the gloss stem "Mmm" stays at the column origin, its right edge short of
    # the object stem "Mmm" by the bracket width.  If the character set holds
    # a stray backslash it matches the leading \textbf and pads the gloss,
    # pushing it right (edge no longer short) -- this catches that.
    o6, g6 = obj("[Mmm"), p.find("Mmm")
    r.append(check(o6.x1 - g6.x1 > 2.0,
                   f"auto ignores a macro-wrapped bracket: gloss stem stays "
                   f"short of the object stem ({g6.x1:.2f} vs {o6.x1:.2f})"))
    return r


def a_termination(p: Page):
    r = []
    aaa, bbb, ccc = p.find("AAA"), p.find("BBB"), p.find("CCC")
    ddd, eee, fff = p.find("DDD"), p.find("EEE"), p.find("FFF")
    ggg, hhh, iii = p.find("GGG"), p.find("HHH"), p.find("III")
    r.append(check(abs(aaa.x0 - bbb.x0) < TOL, "blank-line and \\z. examples align"))
    r.append(check(ccc.x0 < bbb.x0 - 2, "prose after \\z. is outdented to text margin"))
    r.append(check(abs(ddd.x0 - bbb.x0) < TOL,
                   "example after \\z.-prose with no blank line is a normal example"))
    r.append(check(eee.x0 > 0, "example terminated by environment boundary renders"))
    r.append(check(fff.x0 > 0, "tabular inside an example does not terminate it"))
    r.append(check(len(p.find_all("b")) >= 1, "tabular content survives"))
    r.append(check(ggg.x0 > 0, "example terminated by group close renders"))
    # forgotten blank line: III must be at MAIN level, i.e. left of HHH (a sub-item)
    r.append(check(iii.x0 < hhh.x0 - 2,
                   f"nested \\ex. is treated as a boundary: III at top level "
                   f"({iii.x0:.1f} < sub-item {hhh.x0:.1f})"))
    return r


def a_refs(p: Page):
    r = []
    txt = " ".join(w.text for w in p.words)
    # pdftotext maps the T1 en-dash to a control byte; accept any non-alnum
    # single character as the range dash.
    norm = re.sub(r"[^\x20-\x7e]", "-", txt)
    r.append(check(re.search(r"RANGE \(1a-+c\)", norm),
                   f"range renders as (1a--c); got {norm[norm.find('RANGE'):][:24]!r}"))
    r.append(check("PLAINREF (1)" in txt, "\\ref gives (1)"))
    r.append(check(re.search(r"PREF 1c\b", txt), "\\pref drops the parentheses"))
    r.append(check("LAST (1)" in txt, "\\Last gives (1)"))
    r.append(check("NEXT (2)" in txt, "\\Next gives (2)"))
    # footnote: roman numbering, and footnote-internal \Last resolves to (ii)
    r.append(check("(i)" in txt and "(ii)" in txt, "footnote examples number (i),(ii)"))
    r.append(check("FNLAST (ii)" in txt, "\\Last in a footnote refers to the footnote series"))
    r.append(check("FNLLAST (i)" in txt, "\\LLast in a footnote refers to the footnote series"))
    return r



def a_glt(p: Page):
    r"""\GlossTransStyle reaches the free translation, and nothing else.

    Each sentinel occurs twice with identical spelling -- once in the
    unstyled example, once in the styled one -- so the two widths are
    directly comparable and any difference is the hook's doing.
    """
    r = []

    def widths(tok):
        ws = [w.x1 - w.x0 for w in p.find_all(tok)]
        if len(ws) != 2:
            raise AssertionError(f"expected {tok} exactly twice, got {len(ws)}")
        return ws

    plain, styled = widths("GLTTRANS")
    # \Large on a 7-glyph sentinel is worth ~15pt; require well above TOL so
    # the check cannot pass on rounding noise
    r.append(check(styled - plain > 5.0,
                   f"\\GlossTransStyle applies to the translation "
                   f"({plain:.2f} -> {styled:.2f})"))
    # the tiers of the gloss ABOVE the \glt must be unaffected: the
    # declaration is issued after the gloss is already set
    for tok, what in (("GLTOBJ", "object tier"), ("GLTGLOSS", "gloss tier")):
        a, b = widths(tok)
        r.append(check(abs(a - b) < TOL,
                       f"{what} unaffected by \\GlossTransStyle "
                       f"({a:.2f} vs {b:.2f})"))
    # and it must not leak past the end of the example: body text before and
    # after the styled example is set identically
    a, b = widths("GLTBODY")
    r.append(check(abs(a - b) < TOL,
                   f"\\GlossTransStyle does not leak out of the example "
                   f"({a:.2f} vs {b:.2f})"))
    return r


def a_cedilla(p: Page):
    r""" \a.-\f. must not clobber the accents \b \c \d outside an example,
    and must still drive sub-examples inside one -- including inside an exe
    batch.  Under pdflatex a clobbered \c makes the utf8 "ç" fail too, so a
    regression here usually shows up as COMPILE FAILED rather than as a
    failing assertion; the positive checks below pin the rest."""
    r = []
    txt = " ".join(w.text for w in p.words)
    # accents survive in a hyperref \section title: this is the case that
    # used to lose the cedilla silently, in the heading AND the bookmark
    r.append(check("TITLEfaçade" in txt,
                   rf"\c in a hyperref section title keeps its accent; "
                   rf"got {txt[:40]!r}"))
    # \a is held globally and must be \protected, or hyperref's \edef over
    # the title runs its peek and the compile dies
    r.append(check("TITLEcafé" in txt,
                   rf"\a' in a hyperref section title survives; got {txt[:60]!r}"))
    # ... and in running text, in all four positions relative to examples:
    # before any example, and after each of the three example syntaxes.
    # "after exe" is the one that breaks if \end{exe} leaks the \begingroup
    # that a "\a." inside the batch opened.
    for tok in ("BEFOREaçb", "BEFOREdirç", "AFTERDOTç", "AFTEREXEç",
                "AFTERXLç"):
        r.append(check(tok in txt, rf"accent intact: {tok} (got {tok[:-1]!r}?)"))
    # The two non-cedilla kernel accents are restored as themselves, not as
    # the letter commands (\b{b} = bar-under, \d{d} = dot-under).  Matched on
    # the base letter only: the engines disagree on how the accent extracts
    # (pdflatex drops the combining mark, xe/lua give U+0332 resp. the
    # precomposed U+1E0D), so the full token is not portable.  A regression
    # here does not reach this check anyway -- a clobbered \b/\d makes
    # \b{b} raise "Use of \b doesn't match its definition" and the compile
    # fails outright.
    r.append(check(any(w.text.startswith("BEFOREbarb") for w in p.words)
                   and any(w.text.startswith("BEFOREdot") for w in p.words),
                   r"\b and \d remain accent commands outside an example"))
    # and the dot letters still work, in BOTH syntaxes.  Two "a."/"b." pairs
    # are expected: one from the \ex. example, one from inside the exe batch.
    letters = [w.text for w in p.words if w.text in ("a.", "b.")]
    r.append(check(letters == ["a.", "b.", "a.", "b.", "a."],
                   rf"\a./\b. label both the dot example and the exe batch, "
                   rf"plus the xlist item; got {letters}"))
    for tok in ("DOTALPHA", "DOTBETA", "EXEALPHA", "EXEBETA", "XLSUB"):
        r.append(check(p.find(tok) is not None, f"sub-example typeset: {tok}"))
    # the exe batch numbered as a batch and the counter kept running
    nums = [w.text for w in p.words if re.fullmatch(r"\(\d+\)", w.text)]
    r.append(check(nums == ["(1)", "(2)", "(3)"],
                   f"one number per top-level example across syntaxes; got {nums}"))
    return r


def a_ua(p: Page):
    """The PDF/UA gate: veraPDF must pass the accessible build outright.

    This is the assertion that catches a structure element opened at the
    wrong moment -- marked content straddling its parent -- which is
    invisible to every geometric and flat-structure check in this file but
    which veraPDF rejects on all three profiles.
    """
    r = []
    verdicts = verapdf_verdicts(p.path)
    if verdicts is None:
        return [(False, "verapdf is not on PATH: the PDF/UA gate cannot run "
                        "(install veraPDF; it is the only authoritative "
                        "oracle for PDF/UA)")]
    r.append(check(len(verdicts) >= 3,
                   f"veraPDF reported on its profiles (got {verdicts})"))
    failed = [name for name, ok in verdicts if not ok]
    r.append(check(not failed,
                   f"veraPDF: compliant on every profile; failed {failed} "
                   f"with {verapdf_failures(p.path)}"
                   if failed else
                   "veraPDF: compliant on every profile"))
    # the document really did typeset, so a compliant-but-empty PDF cannot
    # pass this case by accident
    for tok in ("UAMAIN", "UAALPHA", "UAOBJ", "UATRANS", "UAALTN", "UAALTG",
                "UAEXE", "UALIST"):
        r.append(check(p.find(tok) is not None, f"typeset: {tok}"))
    return r


def a_cedilla_internal(p: Page):
    r"""The accents must work INSIDE an example body, where the sub-example
    letters are live, and on the same line as a letter command.

    A clobbered \c makes "\c c" (and so the utf8 "ç") raise "Use of \c
    doesn't match its definition", which halts the compile -- so a
    regression normally shows up as COMPILE FAILED.  The checks below pin
    that the two meanings really do coexist rather than one winning.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    # accent in a hyperref \section title (the \edef path)
    r.append(check("Façade" in txt,
                   rf"\c survives in a hyperref section title; got {txt[:30]!r}"))
    # accents inside the example body, in every form
    for tok, what in (("François", r"\c c inside an example (utf8 ç)"),
                      ("Ça", r"\c C on the same line as \b."),
                      ("çedille", r"\c{c} braced, inside an example"),
                      ("braçed", r"\c{c} mid-word, inside an example")):
        r.append(check(tok in txt, f"{what}: expected {tok!r} in the output"))
    # \d{d} and \b{b} in the body: matched on the base letter only, because
    # the engines extract the combining mark differently (see a_cedilla)
    r.append(check(any(w.text.startswith("CIdelta") for w in p.words),
                   r"\d and \b accents inside an example do not error"))
    # ... and still after it
    r.append(check("CIafter" in txt, "accents after the example still work"))
    # the letters kept their OTHER meaning: four sub-examples were opened by
    # \a. \b. \c. \d., so all four labels are present
    letters = [w.text for w in p.words if w.text in ("a.", "b.", "c.", "d.")]
    r.append(check(letters == ["a.", "b.", "c.", "d."],
                   rf"\a.-\d. still open sub-examples; got {letters}"))
    for tok in ("CIalpha", "CIbeta", "CIgamma", "CIdelta"):
        r.append(check(p.find(tok) is not None, f"sub-example typeset: {tok}"))
    # one example, so exactly one number
    nums = [w.text for w in p.words if re.fullmatch(r"\(\d+\)", w.text)]
    r.append(check(nums == ["(1)"], f"one example number; got {nums}"))
    return r


def a_cedilla_gb4e(p: Page):
    r"""[gb4e] alone: \a.-\f. do not exist, so \b \c \d must stay accent
    commands EVERYWHERE, including inside exe/xlist whose sub-level openers
    are shared with the [lazy] dot syntax."""
    r = []
    txt = " ".join(w.text for w in p.words)
    for tok in ("GBTITLEfaçade", "GBBEFOREç", "GBINEXEç", "GBINXLç",
                "GBAFTERç"):
        r.append(check(tok in txt, f"accent intact under [gb4e] alone: {tok}"))
    # the environment syntax itself still works in this mode
    r.append(check(p.find("GBEXEMAIN") is not None, "exe item typeset"))
    nums = [w.text for w in p.words if re.fullmatch(r"\(\d+\)", w.text)]
    r.append(check(nums == ["(1)"], f"exe numbers its item; got {nums}"))
    return r


def a_gbfour(p: Page):
    r = []
    # example labels sit at the left margin; the "(1)" inside the Refs
    # line is running text and must be filtered by position
    labw = [w for w in p.words if re.fullmatch(r"\(\d+\)", w.text)]
    margin = min(w.x0 for w in labw)
    got = [w.text for w in labw if abs(w.x0 - margin) < TOL]
    r.append(check(got == ["(1)", "(2)", "(3)", "(4)", "(5)"],
                   f"exe batch numbers each \\ex; dot syntax continues; got {got}"))
    letters = [w.text for w in p.words if w.text in ("a.", "b.", "c.", "d.", "i.")]
    r.append(check(letters == ["a.", "b.", "c.", "i.", "d."],
                   f"xlist letters and nested roman; got {letters}"))
    # bracket judgments must not displace text: judged and plain items align
    for judged, plain, where in [("GBTWO", "GBONE", "main level"),
                                 ("GBSUBB", "GBSUBA", "sub level")]:
        wj, wp = p.find(judged), p.find(plain)
        r.append(check(abs(wj.x0 - wp.x0) < TOL,
                       f"{where}: [judgment] does not displace text "
                       f"({wj.x0:.2f} vs {wp.x0:.2f})"))
    # the arbitrary mark rendered and hangs left of its text: some
    # non-label token on the line ends at/before GBROMAN's left edge
    # (the dagger has no reliable Unicode mapping, so test by position)
    gr = p.find("GBROMAN")
    lab = re.compile(r"^([a-f]\.|[ivx]+\.|\(\d+\))$")
    hung = [w for w in p.line_of(gr)
            if not lab.match(w.text) and w is not gr and w.x1 <= gr.x0 + TOL]
    r.append(check(hung,
                   f"arbitrary bracket mark hangs left of the text; found {hung}"))
    # cross-references resolve across syntaxes
    txt = " ".join(w.text for w in p.words)
    r.append(check("Refs: (1) and (4)." in txt,
                   f"label and \\Last resolve; got {txt[txt.find('Refs'):][:22]!r}"))
    return r


def a_tagged(p: Page):
    """Tagged compile (DocumentMetadata) must survive every construct;
    the compile itself is the real assertion (tagpdf errors halt it)."""
    r = []
    r.append(check(p.find("MAINTEXT") is not None, "main example typeset"))
    r.append(check(p.find("FNEX") is not None, "footnote example typeset"))
    r.append(check(p.find("glossb") is not None, "gloss lines typeset"))
    r.append(check(p.find("EXEITEM") is not None, "exe item typeset"))
    # Label alignment under tagging: the sub-example letter must sit at
    # the main-example text margin, not be re-boxed flush-right by the
    # tagged list code.  This is the regression that made a. drift ~8pt
    # right of the main text.
    a_lbl = p.find("a.")
    maintext = p.find("MAINTEXT")
    r.append(check(abs(a_lbl.x0 - maintext.x0) < 2.0,
                   f"sub-label a. aligns with the main-example text "
                   f"({a_lbl.x0:.1f} vs {maintext.x0:.1f})"))
    # and the judged sibling b. stays put (judgment hangs, no displacement)
    b_lbl = p.find("b.")
    r.append(check(abs(b_lbl.x0 - a_lbl.x0) < 2.0,
                   f"judged sub-label b. is not displaced ({b_lbl.x0:.1f} vs {a_lbl.x0:.1f})"))
    bbb = p.find("BBB")
    aaa = p.find("AAA")
    ccc = p.find("CCC")   # \noindent line: the true text margin
    # AAA (an ordinary indented paragraph) and BBB (the paragraph after
    # the last example) must share the same indented position, right of
    # the margin: the example's "continue the paragraph" state has been
    # cancelled.
    r.append(check(abs(bbb.x0 - aaa.x0) < 2.0 and bbb.x0 > ccc.x0 + 2.0,
                   f"paragraph after the examples is indented "
                   f"({bbb.x0:.1f} = {aaa.x0:.1f} > margin {ccc.x0:.1f})"))
    # --- structure tree: examples are proper ORDERED lists -------------
    els = struct_elems(getattr(p, "raw", b""))
    tags = [s for s, c in els]
    r.append(check(tags.count("list") >= 2,
                   f"nested example lists present (>=2 L elements, got {tags.count('list')})"))
    # The kernel's list-tagging code (latex-lab-block) renamed these from
    # hardcoded PDF tag names to role-mapped symbolic ones at some point
    # between the 2025-11-01 and 2026-06-01 LaTeX releases (LI -> item,
    # Lbl -> itemlabel, LBody -> itembody), with a /RoleMap back to the
    # classic names for AT/viewers. Accept either vocabulary so this
    # doesn't break again on the next kernel either side of that rename
    # ships with.
    for old, new in (("LI", "item"), ("Lbl", "itemlabel"), ("LBody", "itembody")):
        r.append(check(old in tags or new in tags,
                       f"list structure has {old}/{new} elements"))
    ex_lists = [c for s, c in els if s == "list"]
    # "list" is the block code's own class, carried by the abbreviation
    # list (\lpzglist), which is labelled rather than numbered; every
    # EXAMPLE list must carry one of the three ordered classes, and all
    # three levels occur in this file.
    ok_classes = {"lxOLdecimal", "lxOLalpha", "lxOLroman", "list"}
    r.append(check(ex_lists and all(c in ok_classes for c in ex_lists),
                   f"every example list has a valid ordered ListNumbering "
                   f"class; classes={sorted(set(str(c) for c in ex_lists))}"))
    r.append(check({"lxOLdecimal", "lxOLalpha", "lxOLroman"} <= set(ex_lists),
                   f"all three example levels carry their own class; "
                   f"classes={sorted(set(str(c) for c in ex_lists))}"))
    r.append(check(b"/Ordered" not in getattr(p, "raw", b""),
                   "no invalid /ListNumbering /Ordered value is emitted"))
    # objective 3: the judged sub-example's "*" carries a spoken /Alt
    alts = struct_alts(getattr(p, "raw", b""))
    r.append(check("ungrammatical" in alts,
                   f"judgment mark has spoken /Alt (got {alts})"))
    # objective 4: gloss word-bundles are grouped as Span elements
    # (3 gloss columns here); without grouping only the judgment/section
    # Spans remain, so >=4 proves the gloss columns are structured.
    spans = sum(1 for s, c in els if s == "Span")
    r.append(check(spans >= 4,
                   f"gloss columns are grouped as Span elements "
                   f"(got {spans} Spans; expect >=4)"))
    # objective 5: object-tier words carry a /Lang (declared de here)
    langs = struct_langs(getattr(p, "raw", b""))
    r.append(check("de" in langs,
                   f"object-language tier is marked with /Lang (got {sorted(set(langs))})"))
    # ... and the free translation carries its own, declared fr here.  babel's
    # \foreignlanguage does not reach the structure tree on TL2026, so this
    # Span is the only thing that marks a translation whose language differs
    # from the document's.
    r.append(check("fr" in langs,
                   f"free translation is marked with /Lang "
                   f"(got {sorted(set(langs))})"))
    # ... and that Span is CLOSED again.  Leaving it open is spec-valid, so
    # veraPDF passes and every flat check above passes, while the whole rest
    # of the document silently becomes its child -- and would be announced in
    # the translation's language.  Depth is what gives it away.
    depths = struct_label_depths(p.path)
    r.append(check(len(depths) >= 3,
                   f"structure tree exposes the example numbers "
                   f"(got {depths})"))
    r.append(check(len({d for _, d in depths}) == 1,
                   f"no structure element leaks past the example that opened "
                   f"it: top-level example numbers must share one depth, got "
                   f"{depths}"))
    # objective 6: a Leipzig abbreviation carries its /E expansion text
    exps = struct_exps(getattr(p, "raw", b""))
    r.append(check("third person singular past" in exps,
                   f"compound Leipzig abbreviation expands to one joined /E "
                   f"(got {sorted(set(exps))})"))
    r.append(check(any("or a dog" in a or "cat, a dog" in a for a in alts),
                   f"text-mode alt carries a spoken /Alt list "
                   f"(got {[a for a in alts if 'dog' in a]})"))
    # v0.14: \altg embedded in a gloss carries ONE spoken /Alt over the
    # whole paradigm, with simple \lpzg keys expanded from the Leipzig
    # table; and it stays out of math (no Formula element anywhere, which
    # is what broke the pre-0.12 math-mode \altg under PDF/UA-2).
    r.append(check(p.find("ALTGVERB") is not None, "altg example typeset"))
    r.append(check(any("Socke or Tonne" in a for a in alts),
                   f"altg object call carries a spoken /Alt "
                   f"(got {[a for a in alts if 'Socke' in a]})"))
    r.append(check(any("sock.singular or ton.singular" in a for a in alts),
                   f"altg gloss call carries a spoken /Alt with \\lpzg expanded "
                   f"(got {[a for a in alts if 'sock' in a]})"))
    r.append(check("Formula" not in tags,
                   "no Formula element: alternatives stay text-mode"))
    # \lpzglist is a tagged list of its own: its labels must stay flush
    # left.  A short label that does not fill its own \labelwidth box is
    # re-boxed flush RIGHT by the block code -- the same regression that
    # once shifted the sub-example letters -- and the two keys here have
    # different widths, so right-aligning them spreads their origins.
    lst = _band_lines(p, p.find("LPZGLIST").y1,
                      max(w.y1 for w in p.words) + 1)[:2]  # footnote follows
    labels = [l[0].text for l in lst]
    r.append(check(labels == ["pst", "sg"],
                   f"abbreviation list under tagging: {labels} != ['pst', 'sg']"))
    if len(lst) == 2:
        r.append(check(abs(lst[0][0].x0 - lst[1][0].x0) < TOL,
                       f"list labels stay flush left under tagging "
                       f"({lst[0][0].x0:.2f} vs {lst[1][0].x0:.2f})"))
        r.append(check(all(l[0].x1 < l[1].x0 + TOL for l in lst),
                       "no list label overruns its explanation under tagging"))
    return r


def a_legacy(p: Page):
    """[legacy] must reproduce linguex's geometry and conventions."""
    r = []
    txt = " ".join(w.text for w in p.words)
    # sub-sub-examples print as (i), (ii) -- not i., ii.
    r.append(check("(i)" in txt and "i." not in [w.text for w in p.words],
                   "roman sub-sub-examples print as (i), linguex-style"))
    # \firstrefdash and \secondrefdash are both "-"
    r.append(check(re.search(r"PREF 2-a-i\b", txt),
                   f"reference prints 2-a-i; got {txt[txt.find('PREF'):][:14]!r}"))
    # sub-levels are indented by \SubExleftmargin (2em) and
    # \SubSubExleftmargin (2.4em); at 11pt, 22pt and 26.4pt.
    em = 11.0
    main, sub, rom = (p.find("MAINTEXT"), p.find("SUBTEXT"), p.find("ROMANTEXT"))
    d1, d2 = sub.x0 - main.x0, rom.x0 - sub.x0
    r.append(check(abs(d1 - 2.0 * em) < TOL,
                   f"sub-example text indented \\SubExleftmargin=2em ({d1:.2f}pt)"))
    r.append(check(abs(d2 - 2.4 * em) < TOL,
                   f"roman text indented \\SubSubExleftmargin=2.4em ({d2:.2f}pt)"))
    # the number sits in a box padded to the next digit: (1) and (9) put
    # their text at the same x, (10) one digit further right
    nine, ten = p.find("NINETEXT"), p.find("TENTEXT")
    r.append(check(abs(nine.x0 - main.x0) < TOL,
                   f"(1) and (9) share a two-digit label box "
                   f"({main.x0:.2f} vs {nine.x0:.2f})"))
    # how much the box grows at (10) depends on the digit and paren kerning
    # of the font (as it does in linguex); what must hold everywhere is that
    # it never shrinks
    r.append(check(ten.x0 >= nine.x0 - TOL,
                   f"the label box never shrinks as the number grows "
                   f"({ten.x0:.2f} vs {nine.x0:.2f})"))
    return r



# --- PDF structure-tree inspection (uncompressed output only) -------------

def struct_elems(raw: bytes):
    """(/S, /C) pairs for every /StructElem in an uncompressed tagged PDF."""
    import re as _re
    out = []
    for m in _re.finditer(rb"/Type\s*/StructElem(.*?)>>", raw, _re.S):
        b = m.group(1)
        s = _re.search(rb"/S\s*/(\w+)", b)
        c = _re.search(rb"/C\s*/(\w+)", b)
        out.append((s.group(1).decode() if s else None,
                    c.group(1).decode() if c else None))
    return out


def struct_exps(raw: bytes):
    """/E (abbreviation expansion) values on structure elements."""
    import re as _re
    out = []
    for m in _re.finditer(rb"/E\s*(\([^)]*\)|<[0-9A-Fa-f]+>)", raw):
        v = m.group(1)
        if v.startswith(b"<"):
            out.append(bytes.fromhex(v[1:-1].decode())
                       .decode("utf-16-be", "replace").lstrip("\ufeff"))
        else:
            out.append(v[1:-1].decode("latin1"))
    return out


def struct_langs(raw: bytes):
    """/Lang values on structure elements."""
    import re as _re
    return [m.group(1).decode("latin1")
            for m in _re.finditer(rb"/Lang\s*\(([^)]*)\)", raw)]


def verapdf_verdicts(pdf: Path):
    """[(profile name, compliant?)] from veraPDF, or None if it is missing.

    veraPDF is the only authoritative oracle for PDF/UA: a structure tree can
    be well-formed to every check in this file and still be invalid, and the
    reverse -- spec-valid but semantically wrong -- also happens (see
    struct_label_depths).  The two are complementary, not redundant.
    """
    if not shutil.which("verapdf"):
        return None
    out = subprocess.run(["verapdf", str(pdf)],
                         capture_output=True, text=True).stdout
    return [(m.group(1), m.group(2) == "true") for m in re.finditer(
        r'profileName="([^"]*)"[^>]*isCompliant="(true|false)"', out)]


def verapdf_failures(pdf: Path):
    """Failed rule clauses and their messages, for a readable diagnostic."""
    out = subprocess.run(["verapdf", str(pdf)],
                         capture_output=True, text=True).stdout
    seen = []
    for m in re.finditer(
            r'clause="([^"]*)"[^>]*status="failed".*?<errorMessage>([^<]*)',
            out, re.S):
        item = (m.group(1), m.group(2))
        if item not in seen:
            seen.append(item)
    return seen


def struct_label_depths(pdf: Path):
    """(label, nesting depth) for every top-level example number in the tree.

    The raw-bytes helpers here see structure elements but not their PARENTAGE,
    and neither does veraPDF: an inline element left open -- a Span whose
    \\tag_struct_end: never runs -- reparents the entire rest of the document
    underneath itself while staying perfectly spec-valid, so it passes
    validation and every flat check in this file.  What it does change is
    DEPTH, and pdfinfo's indentation is the cheapest faithful view of that.

    Top-level example numbers are siblings, so they must all sit at one
    depth; if any element between them leaks, the ones after it drop a level.
    Footnote examples are numbered in romans and are legitimately nested
    deeper, so the digit-only pattern skips them.
    """
    out = subprocess.run(["pdfinfo", "-struct-text", str(pdf)],
                         capture_output=True, text=True).stdout
    return [(m.group(2), len(m.group(1)))
            for m in re.finditer(r'(?m)^( *)"\((\d+)\)"', out)]


def struct_alts(raw: bytes):
    """Decoded /Alt strings on Span elements (spoken judgment forms)."""
    import re as _re
    alts = []
    for m in _re.finditer(rb"/Alt\s*<([0-9A-Fa-f]+)>", raw):
        alts.append(bytes.fromhex(m.group(1).decode())
                    .decode("utf-16-be", errors="replace").lstrip("\ufeff"))
    for m in _re.finditer(rb"/Alt\s*\(([^)]*)\)", raw):
        alts.append(m.group(1).decode("latin1"))
    return alts


def _band_lines(p: Page, y_top: float, y_bottom: float):
    """The rendered lines of a horizontal band, top to bottom.

    Each line is the words of one baseline, left to right.  Used to read a
    two-column list (label, explanation) off the page.
    """
    band = [w for w in p.words if w.y0 >= y_top - 0.5 and w.y1 <= y_bottom + 0.5]
    ids = {id(w) for w in band}
    seen, out = set(), []
    for w in sorted(band, key=lambda w: (w.y0, w.x0)):
        if id(w) in seen:
            continue
        line = [x for x in p.line_of(w) if id(x) in ids]
        seen.update(id(x) for x in line)
        out.append(line)
    return out


def a_lpzglist(p: Page):
    """\\lpzglist reports exactly the abbreviations the document uses.

    The list under FRONTLIST stands BEFORE every use it reports on, so a
    complete list also proves the .aux round trip; acc is used only inside
    an \\altg stack (where \\lpzg prints plain) and voc only via \\lpzgadd,
    so both entries prove their own recording path.  NOWHERE has no
    expansion and must be dropped without a trace.
    """
    r = []
    lines = _band_lines(p, p.find("FRONTLIST").y1, p.find("(1)").y0)
    labels = [l[0].text for l in lines]
    expected = ["3", "acc", "def", "nom", "obv", "pl", "prs", "pst", "sg", "voc"]
    r.append(check(labels == expected,
                   f"front list is complete and alphabetical: {labels} != {expected}"))
    texts = {l[0].text: " ".join(w.text for w in l[1:]) for l in lines}
    for key, meaning in (("3", "third person"), ("acc", "accusative"),
                         ("obv", "obviative"), ("voc", "vocative")):
        r.append(check(texts.get(key) == meaning,
                       f"{key} is explained as {meaning!r} (got {texts.get(key)!r})"))
    # labels flush left in a column of their own: same origin for all of
    # them (a right-aligned label column would spread them by width), and
    # none of them running into its explanation (\labelwidth is the width
    # of the WIDEST key, not of the first one).
    entries = [l for l in lines if len(l) > 1]
    xs = [l[0].x0 for l in entries]
    starts = [l[1].x0 for l in entries]
    r.append(check(xs and max(xs) - min(xs) < TOL,
                   f"list labels are flush left "
                   f"(spread {max(xs) - min(xs):.2f}pt)" if xs else
                   "list labels are flush left (the list is empty)"))
    r.append(check(entries and all(l[0].x1 < l[1].x0 + TOL for l in entries),
                   "no label overruns its explanation column"))
    r.append(check(starts and max(starts) - min(starts) < TOL,
                   f"explanations share one column "
                   f"(spread {max(starts) - min(starts):.2f}pt)" if starts else
                   "explanations share one column (the list is empty)"))
    # style=inline, sort=false: one run of text (it wraps), in order of
    # first use, with the ignored keys gone
    inline = p.find("INLINELIST")
    custom = p.find("CUSTOMLIST")
    words = []
    for line in _band_lines(p, inline.y0, custom.y1):
        if any(w.text == "CUSTOMLIST" for w in line):
            break            # the inline list ends where the next one starts
        words += [w.text for w in line]
    got = " ".join(words)
    want = ("INLINELIST sg singular; pst past; pl plural; prs present; "
            "acc accusative; obv obviative; voc vocative")
    r.append(check(got == want, f"inline list, order of first use: {got!r} != {want!r}"))
    # a custom entry format replaces the default one entirely
    tail = _band_lines(p, custom.y1, max(w.y1 for w in p.words) + 1)
    r.append(check(bool(tail) and " ".join(w.text for w in tail[0]) == "sg = singular",
                   f"format= drives the entry: {tail[0] if tail else None}"))
    return r


#: Case files that are deliberately NOT assertion-driven: the two smoke
#: tests the Makefile builds under all three engines, whose only assertion
#: is that they compile.  Listed here so that the integrity check below can
#: tell them apart from a case file whose assertions were forgotten.
SMOKE_ONLY = {"linguexx-test", "linguexx-test-gb4e"}

ASSERTIONS = {
    "cedilla": a_cedilla,
    "cedilla-gb4e": a_cedilla_gb4e,
    "cedilla-internal": a_cedilla_internal,
    "legacy": a_legacy,
    "tagged": a_tagged,
    "ua": a_ua,
    "gbfour": a_gbfour,
    "numbering": a_numbering,
    "judgment-align": a_judgment_align,
    "exsource": a_exsource,
    "zpop": a_zpop,
    "gloss": a_gloss,
    "glt": a_glt,
    "lpzglist": a_lpzglist,
    "phantomalign": a_phantomalign,
    "altg": a_altg,
    "termination": a_termination,
    "refs": a_refs,
}


# ---------------------------------------------------------------------------

def discover_cases():
    """Case-file stems present on disk (anything but the _preamble* helpers)."""
    return {p.stem for p in CASES.glob("*.tex") if not p.name.startswith("_")}


def suite_integrity():
    """Cross-check the case files on disk against ASSERTIONS.

    The suite only ever runs what ASSERTIONS lists, so a case file that is
    not listed is silently dead code -- it looks like coverage in the
    directory listing and provides none.  That is not hypothetical: the
    first cedilla.tex was committed without an ASSERTIONS entry and was
    never executed, which is how a silent regression in the sub-example
    letters reached a release.  Report both directions, and the reverse
    problem of a stale KNOWN_XFAIL key, as hard errors.
    """
    problems = []
    on_disk = discover_cases()
    for name in sorted(on_disk - set(ASSERTIONS) - SMOKE_ONLY):
        problems.append(
            f"{name}.tex has no ASSERTIONS entry, so it is never run. "
            f"Add an assertion function, or list it in SMOKE_ONLY if it is "
            f"only meant to compile."
        )
    for name in sorted(set(ASSERTIONS) - on_disk):
        problems.append(f"ASSERTIONS['{name}'] has no {name}.tex in {CASES}.")
    for name in sorted(set(PASSES) - set(ASSERTIONS)):
        problems.append(f"PASSES['{name}'] names no known case.")
    for key in sorted(KNOWN_XFAIL):
        engine, _, name = key.partition("/")
        if engine not in ENGINES:
            problems.append(f"KNOWN_XFAIL key {key!r} names no known engine.")
        elif name not in ASSERTIONS:
            problems.append(f"KNOWN_XFAIL key {key!r} names no known case.")
    return problems


def run_case(name: str, engine: str, verbose: bool):
    """Compile one case under one engine and run its assertions."""
    src = CASES / f"{name}.tex"
    if not src.is_file():
        return [(False, f"MISSING CASE FILE: {src}")]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        shutil.copy(src, tmp)
        for pre in CASES.glob("_preamble*.tex"):
            shutil.copy(pre, tmp)
        shutil.copy(STY, tmp)
        for _ in range(PASSES.get(name, DEFAULT_PASSES)):
            proc = subprocess.run(
                [engine, "-interaction=nonstopmode", "-halt-on-error", src.name],
                cwd=tmp, capture_output=True, text=True,
            )
        if proc.returncode != 0:
            log = (tmp / f"{name}.log").read_text(errors="replace")
            errs = [l for l in log.splitlines() if l.startswith("!")][:3]
            return [(False, f"COMPILE FAILED: {'; '.join(errs) or 'see log'}")]
        pdf = tmp / f"{name}.pdf"
        if not pdf.exists():
            return [(False, "COMPILE produced no PDF")]
        page = parse_pdf(pdf)
        try:
            return ASSERTIONS[name](page)
        except AssertionError as e:
            return [(False, f"ASSERTION SETUP: {e}")]


def main():
    ap = argparse.ArgumentParser(description="linguexx regression suite")
    ap.add_argument("-e", "--engine", action="append", choices=ENGINES,
                    help="restrict to one engine (repeatable)")
    ap.add_argument("-k", "--filter", help="only cases whose name contains this")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print passing assertions too")
    args = ap.parse_args()

    # Deliberately before -k filtering: a filtered run must still notice a
    # case file that nothing runs.
    problems = suite_integrity()
    if problems:
        print("SUITE INTEGRITY:", file=sys.stderr)
        for p in problems:
            print(f"  X {p}", file=sys.stderr)
        return 2

    engines = args.engine or ENGINES
    names = sorted(ASSERTIONS)
    if args.filter:
        names = [n for n in names if args.filter in n]
    if not names:
        print("no cases match", file=sys.stderr)
        return 2

    total = passed = 0
    failed_cases = []
    for engine in engines:
        if not shutil.which(engine):
            print(f"SKIP {engine}: not installed")
            continue
        print(f"\n=== {engine} ===")
        for name in names:
            results = run_case(name, engine, args.verbose)
            ok = sum(1 for good, _ in results if good)
            total += len(results)
            passed += ok
            bad = [d for good, d in results if not good]
            key = f"{engine}/{name}"
            if bad and key in KNOWN_XFAIL:
                status = "XFAIL"
            else:
                status = "PASS" if not bad else "FAIL"
            print(f"  [{status}] {name:16s} {ok}/{len(results)} assertions")
            if args.verbose:
                for good, d in results:
                    if good:
                        print(f"           . {d}")
            for d in bad:
                print(f"           X {d}")
            if bad and key not in KNOWN_XFAIL:
                failed_cases.append(key)

    print(f"\n{passed}/{total} assertions passed across {len(engines)} engine(s).")
    if failed_cases:
        print("FAILED: " + ", ".join(failed_cases))
        return 1
    print("All green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
