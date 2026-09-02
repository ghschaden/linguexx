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
(poppler-utils), qpdf (to resolve a named destination to the page it lands
on, which no poppler tool reports), and veraPDF on PATH as `verapdf` -- the
only authoritative oracle for PDF/UA, used by the `ua` case.
That list is REQUIRED_TOOLS, and it is checked rather than described: the
suite refuses to start if a tool is missing from PATH, unnamed in this
paragraph, or not installed by the CI workflow.  The three used to be
kept in step by hand and were not.

Exit status: 0 iff every assertion passed, 1 on a failing assertion,
2 on a suite-integrity problem (an unwired case file, a missing case file,
a stale KNOWN_XFAIL or PASSES key, a required tool that PATH, this
docstring and the workflow do not agree about) or when no case matches -k.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ENGINES = ["pdflatex", "xelatex", "lualatex"]
# engine/case pairs whose failure is an artifact of the TOOLING rather than
# a defect in the package.  Empty, and worth keeping so.
#
# It held "pdflatex/judgment-align" from the initial commit: pdftotext used
# to merge the sub-example label with the judgment marks that follow it into
# a single token, and a_judgment_align cannot take such a token apart -- it
# reports "label and marks merged" -- although the geometry was right all
# along, which is why xelatex and lualatex always passed.  Poppler 26.07
# emits the label as its own token, so the case now passes on all three
# engines and the entry masked a green result instead of guarding anything.
#
# Removed rather than kept as insurance: an entry that never fires cannot be
# told apart from one that still protects something, which is how this one
# outlived its reason by a whole rewrite of the suite around it.  main() now
# reports that state -- an entry whose case ran and passed is a hard error,
# not a quiet XFAIL -- so the next one cannot rot the same way.  Should
# judgment-align ever fail on pdflatex ALONE with that message, this is the
# reason, and the answer is to measure the marks from ink (cf. brace_bulge)
# rather than to re-add a line that hides the assertion.
KNOWN_XFAIL = set()
# LaTeX passes per case; two is enough for cross-references, which is all
# most cases need.  The `ua` case needs three: its PDF/UA validity does not
# converge until the third run under pdflatex and xelatex (lualatex gets
# there in two), and a not-yet-converged file fails veraPDF on all three
# profiles -- which would look exactly like a tagging regression.
#: Per-pass wall clock for one engine run.  A TeX loop ignores
#: -interaction=nonstopmode and spins forever, so without a cap one bad case
#: hangs the whole suite rather than failing it.
CASE_TIMEOUT = 120
#: Cases that only some engines can run.  Not a way to duck a failure: the
#: entry is for input pdflatex CANNOT REPRESENT AT ALL -- T1 has no slot for
#: a breve-below or a stacked Vietnamese vowel, and inputenc rejects it with
#: "Unicode character ... not set up for use with LaTeX".  Anything pdflatex
#: can typeset belongs in a case that runs everywhere.
ENGINES_FOR = {
    "utf8-unicode": ("xelatex", "lualatex"),
}
DEFAULT_PASSES = 2
PASSES = {"ua": 3, "frontend": 3, "langsci-ua": 3}
#: Cases that must FAIL to compile, mapped to a substring their .log has to
#: contain.  A package error is as much a feature as a rendering is -- it is
#: what a silently wrong construct was turned into -- and without this it
#: would have no guard: delete the check in the .sty and every other case
#: stays green.  These have no assertion function; the raised error is the
#: assertion.
EXPECT_ERROR = {
    "altg-unpaired": "has no partner",
    # The one-syntax-per-example rule, both directions and the stray.  Each
    # of these renders without complaint if its guard is removed, and each
    # renders something the writer did not ask for: a sub-level only the
    # forbidden \z. could close, a level opened inside a body that is still
    # being collected, and a list closed where none was open.
    "langsci-nomix": "inside an \\ea example",
    "langsci-eamix": "written in the other syntax",
    "langsci-strayz": "with no \\ea to close",
    "langsci-legacy": "cannot be combined",
    "langsci-unclosed": "was never closed",
    "langsci-exioutside": "outside an example",
    "langsci-easnest": "inside an example",
    "langsci-nojambox": "Undefined control sequence",
    "langsci-retired": "has never worked",
    "judgment-badarg": "needs one command here",
    "straysub": "no example to attach it to",
    # Not a package error but TeX's own, and deliberately so: a dot-syntax
    # body is collected before it is typeset, so \verb cannot protect
    # anything in it and the "_" of the payload arrives as a subscript.
    # The manual documents that limitation; this pins it, and verb.tex
    # pins the environment syntax where \verb does work.
    "verb-dot": "Missing $ inserted",
    # The third cell of the same matrix, and the same error from the same
    # payload by a different route: \ex[j]{text} reads its body as a macro
    # argument, so the catcodes are fixed before the body is used exactly as
    # a collected one's are.  Separate from verb-dot because the route is:
    # this one sits under exe, where verb.tex shows an unbraced \ex handling
    # \verb fine, so the braced form is the only thing on trial.
    "verb-braced": "Missing $ inserted",
}
#: The external tools the suite runs on, and how CI is expected to provide
#: each one.  ONE list, checked three ways by suite_integrity: present on
#: PATH, named in this module's docstring, and installed by the workflow.
#:
#: It exists because the three drifted apart and only the slowest of them
#: noticed.  qpdf was added for the beamer overlay assertions and went into
#: the docstring and not into the workflow; every local run was green
#: (qpdf happens to be installed on the machine it was written on) and CI
#: died two minutes in on a FileNotFoundError from inside a helper, having
#: compiled everything and asserted almost nothing.  A requirement that
#: lives only in prose is a requirement nothing enforces.
#:
#: Fields: how the workflow provides it, whether its absence should stop
#: the suite before anything runs, and what it is for.
#:   "image"      -- comes with the texlive container; nothing to install
#:   "apt:<pkg>"  -- <pkg> must appear in the workflow's apt line
#:   "step:<name>" -- a workflow step of that name must exist
#: veraPDF is deliberately NOT a startup check: a_ua owns that message, and
#: a startup check here would make that branch unreachable dead code.
REQUIRED_TOOLS = {
    "pdflatex":  ("image", False, "engine"),
    "xelatex":   ("image", False, "engine"),
    "lualatex":  ("image", False, "engine"),
    "pdftotext": ("apt:poppler-utils", True,
                  "word boxes: every geometric assertion reads them"),
    "pdfinfo":   ("apt:poppler-utils", True,
                  "the tagged structure tree"),
    "qpdf":      ("apt:qpdf", True,
                  "resolving a named destination to the page it lands on"),
    "verapdf":   ("step:Install veraPDF", False,
                  "the PDF/UA oracle, used by the `ua` case"),
}
#: The workflow the tools above are checked against.  Absent from a
#: distribution tarball, where there is no CI to disagree with; the check
#: is about this repository, not about the package.
WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
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


def link_targets(raw: bytes):
    """The destination names of every GoTo link in a PDF, repeats kept.

    A link is invisible to pdftotext -- the printed number looks the same
    whether or not it moves -- so the annotations have to be read out of the
    file itself.  They are not lying in the open: hyperref's output puts
    both the annotation and the name tree in compressed object streams, so
    every Flate stream is inflated and the names are matched in the result.
    stdlib zlib only, deliberately: reading a link must not cost the suite
    another external tool.

    Repeats are kept, because two references to the same example are two
    links.  A rule that folded them into one could not tell a reference that
    lost its link from one that acquired a second.
    """
    text = [raw]
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        try:
            text.append(zlib.decompress(raw[start:end]))
        except zlib.error:              # not Flate: a font, an image, XRef
            pass
    joined = b"\n".join(text).decode("latin-1")
    # "/D (name)" is the GoTo action's destination.  "/Dest" is not matched:
    # the parenthesis has to follow the key immediately.
    return re.findall(r"/D\s*\(([^()]*)\)", joined)


def example_targets(raw: bytes):
    """link_targets restricted to the example anchors linguexx names."""
    return [d for d in link_targets(raw)
            if d.startswith(("ExNo.lxex.", "FnExNo.lxfnex."))]


def dest_page(pdf: Path, name: str):
    """The 1-based page a named destination lands on, or None.

    Which page an anchor sits on is the whole question for a beamer frame,
    where the same example is set on every slide and only one of them is the
    slide it becomes visible on.  Nothing in poppler reports it -- pdfinfo
    and pdftotext see pages and text, not the name tree -- so the file is
    normalised with qpdf first, which resolves the object streams the name
    tree and the destinations live in and labels each page object on its way
    past.  Doing it by hand meant either assuming the page objects are
    written in page order or parsing /Kids, and qpdf already knows.
    """
    if not shutil.which("qpdf"):
        # Say so, rather than let a FileNotFoundError out of a helper: a
        # missing tool is a setup problem and has to read like one, the way
        # the `ua` case says what it needs when veraPDF is absent.  This one
        # got out into CI, where the traceback said 'qpdf' and nothing about
        # which assertion wanted it or why.
        raise AssertionError(
            "qpdf is not on PATH: a named destination cannot be resolved to "
            "the page it lands on (no poppler tool reports it), so the "
            "beamer overlay assertions cannot run")
    out = subprocess.run(
        ["qpdf", "--qdf", "--object-streams=disable", str(pdf), "-"],
        capture_output=True,
    ).stdout.decode("latin-1")
    pages = {m.group(2): int(m.group(1)) for m in re.finditer(
        r"%% Page (\d+)\n%% Original object ID: \d+ 0\n(\d+) 0 obj", out)}
    if not pages:
        raise AssertionError("qpdf produced no page markers in " + str(pdf))
    m = re.search(r"\(" + re.escape(name) + r"\)\s*\n?\s*(\d+) 0 R", out)
    if not m:
        return None
    body = re.search(r"\n" + m.group(1) + r" 0 obj\s*(.*?)\nendobj",
                     out, re.S)
    if not body:
        return None
    ref = re.search(r"(\d+) 0 R", " ".join(body.group(1).split()))
    return pages.get(ref.group(1)) if ref else None


def bookmark_titles(out: str):
    r"""The heading strings from hyperref's .out file, decoded.

    Each line is \BOOKMARK [level][open]{anchor}{title}{parent}, and the
    title is a PDF string: UTF-16BE, byte by byte, with everything outside
    a small ASCII range written as a \nnn octal escape.  So "3" arrives as
    \0003 and the whole thing has to be decoded before it can be compared
    to anything a human wrote.
    """
    titles = []
    for line in out.splitlines():
        m = re.search(r"\}\{(.*)\}\{", line)
        if not m:
            continue
        raw, buf, i = m.group(1), bytearray(), 0
        while i < len(raw):
            if raw[i] == "\\" and raw[i + 1:i + 4].isdigit():
                buf.append(int(raw[i + 1:i + 4], 8))
                i += 4
            else:
                buf.append(ord(raw[i]))
                i += 1
        titles.append(bytes(buf).decode("utf-16-be", "replace").lstrip("\ufeff"))
    return titles


def warning_body(log: str, opening: str):
    """One \\PackageWarning from a .log, unwrapped into a single line.

    LaTeX breaks a warning across lines and prefixes the continuations with
    "(linguexx)", so nothing in a message longer than one line can be found
    by a plain substring test.
    """
    start = log.find(opening)
    if start < 0:
        return ""
    lines = []
    for line in log[start:].splitlines():
        if lines and not line.startswith("(linguexx)"):
            break
        lines.append(line.replace("(linguexx)", " "))
    return " ".join(" ".join(lines).split())


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
    # A custom label replaces the number and steps no counter, in the
    # glossed shorthand as well as in \ex.: (x) then (3), (xx) then (4).
    # \exg.[...] used to be unreachable -- the bracket reached the gloss
    # instead of the label peek -- so the run would read (1),(2),(x),(3),(4)
    # with the label printed as the first word of the object line.
    want = ["(1)", "(2)", "(x)", "(3)", "(xx)", "(4)"]
    r.append(check(got == want,
                   f"custom labels replace the number and step nothing, in "
                   f"\\ex. and in \\exg.: {got} != {want}"))
    # ... and a bracket a space separates from \exg. stays the first word
    # of the object line, on both tiers, rather than being eaten as one.
    r.append(check(len(p.find_all("[DP")) == 2,
                   f"a spaced bracket after \\exg. is the object line's "
                   f"first word, not a label; found "
                   f"{[w.text for w in p.find_all('[DP')]}"))
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


def a_verb(p: Page):
    r"""\verb in an example body: the half of the matrix that works.

    The manual documents that \verb cannot work in the dot syntax, whose
    body is COLLECTED before it is typeset, nor in the braced \ex[j]{text}
    form, whose body is a macro argument read the same way -- verb-dot.tex
    pins the first -- but that it works normally under exe/xlist with an
    unbraced \ex, including inside an "\a." written within the batch.  Only
    the environment syntax hands its body straight to TeX, and nothing
    pinned that, so a change routing it through the collector too would
    have made the manual wrong with the whole suite still green.
    """
    r = []
    rows = [("VBEXE", "exe_%$#{}", "unbraced \\ex in exe"),
            ("VBSUB", "sub_%$#{}", "\\a. inside the exe batch"),
            ("VBXL", "xlist_%$#{}", "\\ex inside xlist"),
            ("VBESC", "esc~^\\", "\\verb over ~, ^ and a backslash")]
    # The verbatim text survives character for character, ON the line of its
    # own example: a payload that reached the page from anywhere else --
    # flushed after the batch, say -- would not be on this line.
    for sent, payload, where in rows:
        line = [w.text for w in p.line_of(p.find(sent))]
        r.append(check(line.count(payload) == 1,
                       f"{where}: {payload!r} is set intact in the body "
                       f"(line reads {line})"))
    # ... and it is body text, right of the sentinel rather than in the
    # label; the sub-example one is indented to the letter level, which is
    # what makes it the "\a. inside the batch" case and not a second main one
    for sent, payload, where in rows:
        s = p.find(sent)
        v = [w for w in p.line_of(s) if w.text == payload]
        r.append(check(bool(v) and v[0].x0 > s.x1,
                       f"{where}: the verbatim sits in the body after "
                       f"{sent} ({v[0].x0:.2f} vs {s.x1:.2f})" if v else
                       f"{where}: no verbatim token on the {sent} line"))
    r.append(check(p.find("VBSUB").x0 > p.find("VBEXE").x0 + 2,
                   f"the \\a. body is indented one level deeper "
                   f"({p.find('VBSUB').x0:.2f} vs {p.find('VBEXE').x0:.2f})"))
    # the batch numbers straight through: a \verb body neither swallows the
    # example that follows it nor stops \z. from popping the \a.
    r.append(check(p.labels() == ["(1)", "(2)", "(3)", "(4)", "(5)"],
                   f"the batch numbers through the verbatim bodies; got "
                   f"{p.labels()}"))
    # Set in the monospaced font, proven without naming one: a fixed-advance
    # font makes six i's exactly as wide as six W's.  The \textrm pair is the
    # control -- in the body font the same two strings differ by ~50pt, so
    # the probe is measuring something.
    def width(tok):
        w = p.find(tok)
        return w.x1 - w.x0

    mi, mw = width("MONOiiiiii"), width("MONOWWWWWW")
    ri, rw = width("ROMNiiiiii"), width("ROMNWWWWWW")
    r.append(check(abs(mi - mw) < TOL,
                   f"\\verb sets its text in a fixed-advance font "
                   f"(iiiiii {mi:.2f}pt vs WWWWWW {mw:.2f}pt)"))
    r.append(check(rw - ri > 20.0,
                   f"control: the body font is not fixed-advance, so the "
                   f"check above is not vacuous ({ri:.2f}pt vs {rw:.2f}pt)"))
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
    # \sublabel records the label of the level it sits at: a range over roman
    # sub-sub-examples must END in a roman numeral.  Recording the letter
    # counter for every level instead gave "(2b-i--b)" -- no error, just a
    # wrong reference, and every roman under one letter aliased to it.
    r.append(check(re.search(r"ROMANRANGE \(2b-i-+iii\)", norm),
                   f"roman range ends in the roman numeral, not the enclosing "
                   f"letter; got {norm[norm.find('ROMANRANGE'):][:30]!r}"))
    r.append(check("ROMANREF (2b-iii)" in txt,
                   f"\\ref to a sub-sub-example is unchanged; got "
                   f"{txt[txt.find('ROMANREF'):][:20]!r}"))
    r.append(check(re.search(r"LETTERRANGE \(2b-+b\)", norm),
                   f"the letter level still records its letter; got "
                   f"{norm[norm.find('LETTERRANGE'):][:26]!r}"))
    # footnote: roman numbering, and footnote-internal \Last resolves to (ii)
    r.append(check("(i)" in txt and "(ii)" in txt, "footnote examples number (i),(ii)"))
    r.append(check("FNLAST (ii)" in txt, "\\Last in a footnote refers to the footnote series"))
    r.append(check("FNLLAST (i)" in txt, "\\LLast in a footnote refers to the footnote series"))
    return r


def a_relrefs(p: Page):
    r"""A relative reference may name a sub-example: \Last[b] -> (1b).

    The part goes inside the parentheses and is joined by \firstrefdash --
    the hook \theSubExNo uses -- so \Last[b] and \ref to the \sublabel of
    letter b agree; a_legacy pins the other value of that hook.  The failure
    this guards against is silent: with no optional argument declared, the
    bracket group is not an argument at all, it is text, and "(1)[b]" is
    what reaches the page with a clean exit status.
    """
    r = []
    txt = " ".join(w.text for w in p.words)

    def shows(tok, want):
        got = txt[txt.find(tok):][:len(tok) + 12]
        return check(f"{tok} {want}" in txt, f"{tok} prints {want}; got {got!r}")

    # main series: the part lands inside the parentheses, and the bare form
    # is untouched by the machinery that puts it there
    r.append(shows("BARE", "(1)"))
    r.append(shows("SUB", "(1b)"))
    r.append(shows("REF", "(1a)"))          # same example, spelt by \ref
    r.append(shows("PSUB", "1b"))           # \pLast forwards the argument
    r.append(shows("NEXTSUB", "(2c)"))
    r.append(shows("NNEXTSUB", "(3d)"))
    r.append(shows("LLASTSUB", "(1a)"))
    r.append(shows("PNEXTSUB", "3e"))
    r.append(shows("PLLASTSUB", "1f"))

    # footnote series: the part rides on the roman numeral, except for
    # \TextNext, which points at the main series from inside the footnote
    r.append(shows("FNSUB", "(iia)"))
    r.append(shows("FNPSUB", "iia"))
    r.append(shows("FNLL", "(ib)"))
    r.append(shows("FNNEXT", "(iiic)"))
    r.append(shows("TEXTNEXTSUB", "(3a)"))
    r.append(shows("PTEXTNEXTSUB", "3b"))

    # nothing leaks: a sub part set for one reference must not survive into
    # the next, which the bare \Last above would not catch on its own since
    # it comes first.  \ref sits between two parametrised references.
    r.append(check("[b]" not in txt and "[a]" not in txt,
                   "the optional argument is consumed, not typeset as text"))

    # the space TeX's tokenizer ate after the control word is put back
    # (\xspace, as in linguex), and is NOT put back before punctuation --
    # which is what makes it \xspace rather than \space.  Both halves are
    # measured on the joined text, where a missing space shows up as
    # "(1)after" arriving from pdftotext as a single word.
    r.append(shows("XSP", "(1) after"))
    r.append(shows("PXSP", "1 after"))
    r.append(shows("XSPARG", "(1b) after"))
    r.append(shows("XSPNEXT", "(2) after"))
    r.append(shows("XSPCOMMA", "(1), comma"))
    return r


def a_relreflinks(p: Page):
    r"""\Next and \Last are links -- and never links to nothing.

    Two claims, and the second is the one with teeth.  That the references
    move at all is read out of the PDF's link annotations, because nothing
    about a link shows up in the rendering: the number is the same glyphs
    whether or not it is clickable, which is why this was missing for as
    long as it was.

    The second claim is that a reference with no example behind it is not
    linked.  A relative reference names its target by arithmetic, so \LLast
    before example 2 asks for example 0 and \Next after the last one asks
    for one more than there is; a link to a destination that does not exist
    is NOT an error, since the backend substitutes a whole-page destination
    and the click lands somewhere plausible and wrong.  The engines cannot
    be relied on to say so either -- pdftex and luatex warn in two
    phrasings and xdvipdfmx says nothing -- so both halves are asserted
    here: no annotation for the four numbers that name nothing, and one
    linguexx warning that lists exactly those four.

    The .aux is checked too.  It is where the anchors of one run are handed
    to the next, and it is what makes a cold run different from a warm one:
    on the first pass nothing is known, nothing is linked, and the answer
    is a rerun rather than four false reports of a missing example.
    """
    r = []
    txt = " ".join(w.text for w in p.words)

    def shows(tok, want):
        got = txt[txt.find(tok):][:len(tok) + 14]
        return check(f"{tok} {want}" in txt, f"{tok} prints {want}; got {got!r}")

    # The printed numbers first: the formatters were rewritten to take the
    # number as an EXPRESSION (so that the anchor and the printed digits
    # come out of one evaluation), and that must not have moved a digit.
    r.append(shows("RLBEFORE", "(-1) (0) (1)"))
    r.append(shows("RLNEXT", "(2)"))
    r.append(shows("RLLAST", "(1)"))
    r.append(shows("RLNNEXT", "(3)"))
    r.append(shows("RLPART", "(2b)"))
    r.append(shows("RLPTWIN", "2"))
    r.append(shows("RLTEXTNEXT", "(3)"))
    r.append(shows("RLFNLAST", "(ii)"))
    r.append(shows("RLFNNEXT", "(iii)"))
    r.append(shows("RLPAST", "(4)"))

    # The links.  Counted, not merely present: RLBEFORE's \Next and RLLAST
    # both name example 1; RLNEXT, RLPART and the p-twin RLPTWIN all name
    # example 2; RLNNEXT and RLTEXTNEXT both name example 3.  \Next[b]
    # naming example 2 rather than its letter b is a decision, not an
    # oversight (the letter anchors are built from \alph and the printed
    # letter from \Exalph), and the p-twin is here because it suppresses
    # the parentheses, not the reference.
    got = example_targets(p.raw)
    want = {"ExNo.lxex.1": 2, "ExNo.lxex.2": 3, "ExNo.lxex.3": 2,
            "FnExNo.lxfnex.2": 1}
    for name, n in want.items():
        r.append(check(got.count(name) == n,
                       f"{n} link(s) to {name}; got {got.count(name)}"))
    # \TextNext escaping the footnote is the reason the footnote series is
    # here at all: (3) inside the footnote must aim at the MAIN example 3.
    r.append(check(got.count("FnExNo.lxfnex.3") == 0
                   and "ExNo.lxfnex.3" not in got,
                   "\\TextNext links to the main series, not the footnote one"))
    # and nothing else: the four numbers that name no example are the whole
    # point of the case, and an anchor outside this set would mean a link
    # aimed at something the document does not have.
    stray = sorted(set(got) - set(want))
    r.append(check(not stray, f"no link to an example that does not exist; "
                              f"got {stray}"))

    # The engines that do report a substituted destination must not report
    # one.  Vacuous under xelatex, where xdvipdfmx says nothing either way,
    # which is exactly why linguexx does not rely on this.
    log = getattr(p, "log", "")
    for phrase in ("has been referenced but does not exist",
                   "unreferenced destination"):
        r.append(check(phrase not in log, f"no backend warning ({phrase!r})"))

    # One warning, naming exactly the four references that found no target,
    # in document order.  Without it the four are silent: they print the
    # number they always printed, and nothing marks them as unresolved.
    body = warning_body(log, "Package linguexx Warning: No example carries")
    r.append(check(bool(body), "the dangling references are reported at all"))
    listed = []
    if "asks for:" in body:
        tail = body.split("asks for:", 1)[1].split(". The number", 1)[0]
        listed = [item.strip().split(" ")[0] for item in tail.split(",")
                  if "(line" in item or item.strip()]
        listed = [x for x in listed if not x.startswith("(line")]
    r.append(check(listed == ["-1", "0", "iii", "4"],
                   f"the report names -1, 0, iii and 4; got {listed}"))

    # The .aux carries the anchors from one run to the next, guarded by a
    # \providecommand of its own: a document that drops linguexx still has
    # last run's .aux, and reading it must not be an undefined command.
    aux = getattr(p, "aux", "")
    r.append(check(aux.find(r"\providecommand\lx@relref@dest[1]{}") >= 0
                   and aux.find(r"\providecommand\lx@relref@dest[1]{}")
                       < aux.find(r"\lx@relref@dest{ExNo"),
                   "the .aux defines \\lx@relref@dest before using it"))
    for name in ("ExNo.lxex.1", "ExNo.lxex.2", "ExNo.lxex.3",
                 "FnExNo.lxfnex.1", "FnExNo.lxfnex.2"):
        r.append(check(("\\lx@relref@dest{%s}" % name) in aux,
                       f"the .aux records the anchor of {name}"))

    # Cold run: the anchors are not known yet, so nothing is linked and the
    # answer is a rerun -- NOT four reports of examples that do exist.  The
    # warm run must then be quiet, or the message would cry wolf on every
    # document that has converged.
    first = getattr(p, "first_log", "")
    r.append(check("Example anchors out of date" in first,
                   "the first pass asks for a rerun"))
    r.append(check("No example carries" not in first,
                   "the first pass does not report the resolvable references"))
    r.append(check("Example anchors out of date" not in log,
                   "the converged run does not ask for a rerun"))
    return r


def a_relreflinks_beamer(p: Page):
    r"""Relative references under beamer, where nothing anchors them for us.

    beamer sets hyperref's implicit=false -- it anchors its own \labels and
    runs its own navigation -- so there is no destination at
    \refstepcounter.  linguexx used to read that as "impossible here" and
    switch itself off, which left \ref moving and \Last not, in the class
    most linguistics slides are written in.  It now places the destination
    itself, and this asserts that the references reach it.

    The other half is the overlays, and it is the half that leaves no mark
    on the page.  A frame is set once per slide with the example counters
    restored each time, so an example on a two-slide frame comes past twice
    with the same number: unguarded, a duplicate destination that hyperref
    drops, and a duplicate .aux record that the shared-anchor guard would
    read as two examples claiming one name -- refusing, on that ground, to
    link the very examples this case is about.  The .aux is where one
    example seen twice can be told from two examples numbered alike, so
    the .aux is what is counted here.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    aux = getattr(p, "aux", "")
    log = getattr(p, "log", "")

    # The frame really did produce two slides.  Without this the overlay
    # assertions below would pass vacuously on any beamer that collapsed it.
    r.append(check(txt.count("BMTWO") == 2 and txt.count("BMOVERLAY") == 1,
                   f"the second frame really has two slides (BMTWO "
                   f"{txt.count('BMTWO')}x, BMOVERLAY "
                   f"{txt.count('BMOVERLAY')}x)"))

    for tok, want in (("BMREF", "(1)"), ("BMLAST", "(1)"),
                      ("BMNEXT", "(2)"), ("BMLASTTWO", "(2)")):
        r.append(check(f"{tok} {want}" in txt,
                       f"{tok} prints {want}; got "
                       f"{txt[txt.find(tok):][:len(tok) + 12]!r}"))

    # The links exist at all -- the whole point, and invisible on the page.
    got = example_targets(p.raw)
    for name in ("ExNo.lxex.1", "ExNo.lxex.2"):
        r.append(check(name in got, f"the references link to {name}; "
                                    f"targets found: {sorted(set(got))}"))
    # beamer's own anchoring is undisturbed: \ref still reaches the label
    # destination beamer made for it.
    r.append(check("bm:one" in link_targets(p.raw),
                   "\\ref still links to beamer's own label destination"))

    # One example, one record -- on a frame typeset twice.
    for name in ("ExNo.lxex.1", "ExNo.lxex.2"):
        n = aux.count("\\lx@relref@dest{%s}" % name)
        r.append(check(n == 1, f"{name} is recorded once, not once per "
                               f"overlay (got {n})"))

    # An example that first appears on a LATER slide.  \only does not
    # typeset what it excludes, so this one is numbered for the first time
    # on the frame's second pass; a rule that skipped every pass after the
    # first gave it no anchor at all, and the reference naming it was then
    # reported as dangling by the mechanism that had discarded its target.
    r.append(check(txt.count("BMLATE") == 1,
                   f"the deferred example is set on one slide only "
                   f"(BMLATE {txt.count('BMLATE')}x)"))
    n = aux.count("\\lx@relref@dest{ExNo.lxex.5}")
    r.append(check(n == 1, f"the deferred example is recorded once, on the "
                           f"pass where it appears (got {n})"))
    r.append(check("ExNo.lxex.5" in got,
                   "and the reference made before it links to it"))
    r.append(check("BMBEFORE (5)" in txt,
                   f"BMBEFORE prints (5); got "
                   f"{txt[txt.find('BMBEFORE'):][:20]!r}"))

    # \pause: the example is EXECUTED on the frame's first slide -- the
    # counter steps, and an anchor placed there is placed on that slide --
    # while its ink is dropped, so the reader sees it only later.  That gap
    # between executed and visible is why anchoring it where it was first
    # set sent a click to a slide with no example on it, and why no
    # page-based check could see the mistake: on the page, nothing is there.
    # The example appears once, and the assertion is not about the page at
    # all but about where its destination went.
    r.append(check(txt.count("BMPAUSED") == 1,
                   f"the paused example shows on one slide (BMPAUSED "
                   f"{txt.count('BMPAUSED')}x)"))
    shown, paused = (dest_page(p.path, "ExNo.lxex.3"),
                     dest_page(p.path, "ExNo.lxex.4"))
    r.append(check(shown is not None and paused is not None
                   and paused == shown + 1,
                   f"the paused example is anchored one slide after the one "
                   f"above it, where it becomes visible (pages {shown} and "
                   f"{paused})"))

    # ... which is what keeps both warnings away: the engine's, for a
    # destination it had to drop, and linguexx's, for an anchor it would
    # otherwise take to be shared between two examples.
    r.append(check("destination with the same identifier" not in log
                   and "duplicate destination" not in log,
                   "no duplicate-destination warning from the engine"))
    r.append(check("linguexx Warning" not in log,
                   "and no linguexx warning: nothing dangles and nothing "
                   "is shared"))
    return r


def a_relreflinks_beamer_reset(p: Page):
    r"""Two examples numbered alike under beamer are still two examples.

    The companion to relreflinks-beamer.tex, and the case that makes the
    rule per-FRAME rather than per-document.  A document-wide "have I
    placed this name already" set would pass that case and silently link
    this one to the wrong example: the overlay repeat and the reset
    counter produce the same repeated name, and only where the repeat
    happens tells them apart.

    One number carries both halves.  Frame one has two slides, so its
    example comes past twice and must be recorded once; frame two reuses
    the number and must be recorded again.  Three records would mean the
    overlay repeat was recorded; one would mean the reset was swallowed.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    aux = getattr(p, "aux", "")
    log = getattr(p, "log", "")

    r.append(check(txt.count("BRONE") == 2 and txt.count("BROVERLAY") == 1,
                   f"the first frame really has two slides (BRONE "
                   f"{txt.count('BRONE')}x, BROVERLAY "
                   f"{txt.count('BROVERLAY')}x)"))
    n = aux.count("\\lx@relref@dest{ExNo.lxex.1}")
    r.append(check(n == 2, f"the number is recorded twice -- once per "
                           f"example, not once per slide and not once for "
                           f"both examples (got {n})"))
    r.append(check("ExNo.lxex.1" not in example_targets(p.raw),
                   "and the reference to it is not a link"))
    body = warning_body(log, "Package linguexx Warning: More than one example")
    r.append(check("1 (line" in body,
                   f"the shared number is reported; got {body!r}"))
    r.append(check("BRLAST (1)" in txt,
                   f"BRLAST still prints (1); got "
                   f"{txt[txt.find('BRLAST'):][:16]!r}"))
    return r


def a_relreflinks_reset(p: Page):
    r"""A number two examples share is not linked either.

    \theHExNo is built from ExNo alone, so a reset counter makes two
    examples claim one anchor and hyperref keeps only the first
    destination.  That is a defect in the anchors, older than the links: a
    \label on the second example has always led to the first.  What is
    asserted here is the narrower promise the links make -- that linguexx
    adds no wrong jump of its own to a document that has this.  The
    reference prints its number and stays put, and says so in its own
    words, since a reader who gets the report has to be able to tell a
    shared number from a missing one.

    The engines' own duplicate-destination warning is asserted too, on the
    two that emit it.  It is what makes the case honest: if it ever stops
    appearing, the anchors have been mended and the withheld link here is
    a needless one rather than a saved wrong jump.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    r.append(check("RSDUP (1) RSUNIQ (2)" in txt,
                   f"both references print their number; got "
                   f"{txt[txt.find('RSDUP'):][:24]!r}"))
    got = example_targets(p.raw)
    r.append(check("ExNo.lxex.1" not in got,
                   "the number two examples share is not a link"))
    r.append(check(got.count("ExNo.lxex.2") == 1,
                   f"the number one example carries still is "
                   f"(got {got.count('ExNo.lxex.2')})"))
    log = getattr(p, "log", "")
    body = warning_body(log, "Package linguexx Warning: More than one example")
    r.append(check("1 (line" in body,
                   f"the shared number is reported, with its line; got {body!r}"))
    r.append(check("counter was reset" in body,
                   "the report says why, so a shared number is not read as a "
                   "missing one"))
    r.append(check("No example carries" not in log,
                   "and is not ALSO reported as an example that does not exist"))
    # The engine's own report of the destination it had to drop, which is
    # what makes this case honest: if it ever stops appearing, the anchors
    # have been mended and the link withheld above is a needless one rather
    # than a saved wrong jump.  pdftex and luatex say so; xdvipdfmx does
    # not, the collision being resolved downstream, so there is nothing to
    # assert under xelatex and no pretence that there is.
    #
    # Written first as `check(True, ...)` inside `if <the phrase is
    # present>`, which is to say not written at all: a check guarded by its
    # own condition cannot fail, and it sat there reporting a pass while
    # doc/DEFERRED-DECISIONS.md cited it as the thing that would fail loudly
    # when the collision goes.  Same shape as the KNOWN_XFAIL entry that
    # outlived its reason, and the same lesson: a guard that cannot fire is
    # indistinguishable from one that guards nothing.
    if p.engine in ("pdflatex", "lualatex"):
        r.append(check("same identifier" in log or "duplicate destination"
                       in log,
                       f"{p.engine} reports the duplicate destination it had "
                       f"to drop"))
    return r


def a_relreflinks_off(p: Page):
    r"""[norelreflinks]: the references print, and stay put.

    The option is invisible to every other case, all of which take the
    default, so without this one the two \DeclareOption lines could be
    deleted and the suite would stay green.

    Every reference here resolves, which is the point: the claim is not
    that a link is withheld from a reference that has no target -- that is
    relreflinks.tex -- but that one with a perfectly good target does not
    become a link.  \ref sits beside them and must still move, so example 1
    is named twice on the page and may be a link exactly once.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    for tok, want in (("RONEXT", "(2)"), ("ROLAST", "(1)"), ("ROREF", "(1)")):
        r.append(check(f"{tok} {want}" in txt,
                       f"{tok} prints {want}; got "
                       f"{txt[txt.find(tok):][:len(tok) + 14]!r}"))
    got = example_targets(p.raw)
    r.append(check(got.count("ExNo.lxex.1") == 1,
                   f"\\ref still links and \\Last does not (one link to "
                   f"example 1, got {got.count('ExNo.lxex.1')})"))
    r.append(check("ExNo.lxex.2" not in got,
                   "\\Next is not a link"))
    # Nothing is recorded either: with the links off the .aux must not grow
    # a line per example for a mechanism the document has switched off.
    aux = getattr(p, "aux", "")
    r.append(check(r"\lx@relref@dest" not in aux,
                   "no anchors are written to the .aux"))
    r.append(check("linguexx Warning" not in getattr(p, "log", ""),
                   "and nothing is reported"))
    return r


def a_phantommarks(p: Page):
    r"""Which leading marks the aligner recognises, on both consumers.

    Not the geometry -- phantomalign.tex and altn-phantomalign.tex measure
    that, and both do it with marks that always worked.  What neither could
    see is that the two marks the default set NAMED could never match: a
    bare # is a macro parameter character and a bare % opens a comment, so
    \# and \% are the only spellings a document can contain, and the set
    held the bare characters while the peel rejected every control
    sequence.  The package disagreed with itself -- \ex. \#Ceci hung its
    mark, \altn{un nez}{\#le nez} did not -- and nothing failed.

    Each probe pairs a marked alternative with an unmarked one carrying the
    same stem.  Peeled, the mark goes to the gutter and the stems agree on
    their right edge; not peeled, the rows are centred with the mark inside
    one of them and they do not.  Both outcomes are asserted: "recognised"
    and "not recognised" are each other's control, and a peel that simply
    swallowed everything would pass half of this.
    """
    r = []
    txt = " ".join(w.text for w in p.words)

    def spread(stem):
        ws = p.find_all(stem)
        if len(ws) != 2:
            raise AssertionError(f"expected {stem} twice, got {ws}")
        return max(w.x1 for w in ws) - min(w.x1 for w in ws)

    def peeled(stem, what):
        d = spread(stem)
        return check(d < TOL, f"{what}: peeled into the gutter, stems line "
                              f"up (right-edge spread {d:.2f}pt)")

    def kept(stem, what):
        d = spread(stem)
        return check(d > TOL, f"{what}: left where it was typed, stems do "
                              f"not line up (right-edge spread {d:.2f}pt)")

    # the stacks
    r.append(peeled("PSTEMA", r"\# in a stack"))
    r.append(peeled("PSTEMB", r"\% in a stack"))
    # \dag is not a mark until the document says so, and then it is.  The
    # pair is the whole of the claim that the set is CONSULTED rather than
    # every control sequence waved through.
    r.append(kept("PSTEMC", r"\dag before \GlossPhantomChars names it"))
    r.append(peeled("PSTEMD", r"\dag after \GlossPhantomChars names it"))
    # An undelimited head strips braces, so this needs its own test in the
    # peel; without it "{[}stem" peels as "[" + "stem".
    r.append(kept("PSTEME", "a braced ["))
    # the gloss aligner, reading the same set.  \dag is the one that
    # matters: it is ROBUST, and the old f-expansion retrieval turned it
    # into \protect\dag before the peel saw it, so the peel found \protect
    # and no mark.  \# and \% are not robust, which is why the stacks
    # cannot catch that and this probe can.
    r.append(peeled("PMGLHASH", r"\# in a gloss word"))
    r.append(peeled("PMGLDAG", r"\dag in a gloss word"))

    # A peel that swallowed its mark instead of moving it would align the
    # stems just as well, so the marks have to still be on the page: two
    # hashes (stack and gloss), one percent, three daggers (the undeclared
    # stack, the declared one, the gloss).
    for mark, n, what in (("#", 2, "hash"), ("%", 1, "percent"),
                          ("†", 3, "dagger")):
        got = txt.count(mark)
        r.append(check(got == n, f"the {what} marks are printed, not "
                                 f"swallowed ({got} of {n})"))
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
    # \lpzg in a title: on the page, in the bookmark, and without the
    # "Token not allowed in a PDF string" that hyperref emits for a command
    # it has not been told about.  The bookmark has no small caps to lose,
    # so the label is spelt there as it was written.
    r.append(check("TITLEgloss" in txt,
                   rf"\lpzg in a hyperref section title typesets; "
                   rf"got {txt[:60]!r}"))
    titles = [t for t in bookmark_titles(p.out) if "TITLEgloss" in t]
    r.append(check(titles == ["TITLEgloss 3sg.pst"],
                   f"the bookmark carries the abbreviation as written; "
                   f"got {titles}"))
    r.append(check("removing `\\lpzg'" not in p.log,
                   "and hyperref is not left to drop it from the string, "
                   "which is what it does -- \"Token not allowed in a PDF "
                   "string (Unicode): removing `\\lpzg'\" -- for a command "
                   "it has not been told about"))
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

    Not every such defect reaches the verdict, though: some malformed
    nesting is only logged, and a run that logs it still reports compliant.
    So the run is read twice, once for the verdict and once for anything
    veraPDF said while parsing; see verapdf_log_records.
    """
    r = []
    if not shutil.which("verapdf"):
        return [(False, "verapdf is not on PATH: the PDF/UA gate cannot run "
                        "(install veraPDF; it is the only authoritative "
                        "oracle for PDF/UA)")]
    verdicts, failures, raw = verapdf_report(p.path)
    if not verdicts:
        # veraPDF ran but said nothing: a broken install, not a bad PDF.  Say
        # so, with its output, rather than reporting an empty verdict list.
        return [(False, f"veraPDF produced no verdict -- it is on PATH but "
                        f"could not report (broken install? missing JRE?). "
                        f"Its output was: {raw[:400]!r}")]
    r.append(check(len(verdicts) >= 3,
                   f"veraPDF reported on all its profiles (got {verdicts})"))
    failed = [name for name, ok in verdicts if not ok]
    r.append(check(not failed,
                   f"veraPDF: compliant on every profile; failed {failed} "
                   f"with {failures}"
                   if failed else
                   "veraPDF: compliant on every profile"))
    logged = verapdf_log_records(raw)
    r.append(check(not logged,
                   f"veraPDF parsed the file without complaint; it logged "
                   f"{len(logged)} record(s): {logged[:3]}"
                   if logged else
                   "veraPDF parsed the file without complaint"))
    # the document really did typeset, so a compliant-but-empty PDF cannot
    # pass this case by accident
    for tok in ("UAMAIN", "UAALPHA", "UAOBJ", "UATRANS", "UAALTN", "UAALTG",
                "UAEXE", "UALIST", "UAREL", "UAZTRANS", "UAZAFTER", "UAMOD"):
        r.append(check(p.find(tok) is not None, f"typeset: {tok}"))
    # The modified abbreviation reads back as it was written.  Where the
    # font has no bold small caps the glyphs on the page are capitals, so
    # what is read here is the /ActualText of the made caps and nothing
    # else -- and that is not decoration: it is what a screen reader
    # announces and what copy-and-paste yields.  Taken from the whole line
    # rather than from one word, because made caps are set at a size of
    # their own and pdftotext -bbox splits a word at the size change (its
    # plain output joins the pieces again, with no space between them).
    mod = "".join(w.text for w in p.line_of(p.find("UAMOD")))
    r.append(check("m.pl" in mod,
                   f"the modified abbreviation extracts as written: {mod!r}"))
    return r


def a_customise(p: Page):
    r"""The numbering parameters at NON-default values, and the relative
    reference commands no other case calls.

    [legacy] exercises some of these, but only at linguex's values; nothing
    checked that setting them yourself works, so a change that broke
    customisation while leaving both shipped modes intact would have passed
    the whole suite.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    # \SubExLBr/RBr and \SubSubExLBr/RBr drive the printed sub-labels
    labels = [w.text for w in p.words
              if w.text in ("(a)", "(b)", "[i]", "[ii]")]
    r.append(check(labels == ["(a)", "(b)", "[i]", "[ii]"],
                   f"\\SubEx*Br and \\SubSubEx*Br drive the labels; "
                   f"got {labels}"))
    # \firstrefdash between number and letter, \secondrefdash before the roman
    r.append(check("CREF (1:b)" in txt,
                   f"\\firstrefdash in a reference; got "
                   f"{txt[txt.find('CREF'):][:12]!r}"))
    r.append(check("CROMAN (1:b/ii)" in txt,
                   f"\\secondrefdash in a reference; got "
                   f"{txt[txt.find('CROMAN '):][:16]!r}"))
    r.append(check("CPREF 1:b" in txt, "\\pref drops the parentheses"))
    # \rangedash, and \sublabel recording the right level in a custom setup
    r.append(check("CRANGE (1:atob)" in txt,
                   f"\\rangedash closes a letter range; got "
                   f"{txt[txt.find('CRANGE'):][:18]!r}"))
    r.append(check("CROMANRANGE (1:b/itoii)" in txt,
                   f"a roman range ends in the roman numeral; got "
                   f"{txt[txt.find('CROMANRANGE'):][:26]!r}"))
    r.append(check("CREFRANGE (1)to(1)" in txt,
                   f"\\Refrange spans two whole examples; got "
                   f"{txt[txt.find('CREFRANGE'):][:20]!r}"))
    # the relative references, parenthesised and not
    for sent, want in (("CNEXT", "(3)"), ("CNNEXT", "(4)"),
                       ("CLAST", "(2)"), ("CLLAST", "(1)"),
                       ("CPNEXT", "3"), ("CPNNEXT", "4"),
                       ("CPLAST", "2"), ("CPLLAST", "1")):
        r.append(check(f"{sent} {want}" in txt,
                       f"{sent} gives {want}; got "
                       f"{txt[txt.find(sent + ' '):][:14]!r}"))
    # \TextNext escapes a footnote to the main series
    r.append(check("CTEXTNEXT (4)" in txt and "CPTEXTNEXT 4" in txt,
                   "\\TextNext/\\pTextNext reach the main series from a "
                   "footnote"))
    return r


def a_judgments(p: Page):
    r"""\DeclareJudgment and \SetJudgmentSpoken, including their tagging.

    The spoken phrase becomes the /Alt of the Span wrapping the mark, which
    is invisible in the rendering, so the /Alt strings are the real subject
    here; the geometry checks only confirm a declared mark behaves like a
    built-in one.
    """
    r = []
    alts = struct_alts(getattr(p, "raw", b""))
    r.append(check("marginal for me" in alts,
                   f"\\DeclareJudgment[spoken=] reaches the /Alt "
                   f"(got {sorted(set(alts))})"))
    r.append(check("starred and ungrammatical" in alts,
                   f"\\SetJudgmentSpoken overrides a built-in spoken form "
                   f"(got {sorted(set(alts))})"))
    # the override replaced the default rather than sitting beside it
    r.append(check("ungrammatical" not in alts,
                   f"the overridden default is gone (got {sorted(set(alts))})"))
    # a declared mark hangs like any other: it must not displace the text
    for tok in ("JDGCUSTOM", "JDGSTAR", "JDGPLAIN"):
        r.append(check(p.find(tok) is not None, f"typeset: {tok}"))
    plain = p.find("JDGPLAIN")
    for tok in ("JDGCUSTOM", "JDGSTAR"):
        w = p.find(tok)
        r.append(check(abs(w.x0 - plain.x0) < TOL,
                       f"{tok}: a declared mark hangs and does not displace "
                       f"the text ({w.x0:.2f} vs {plain.x0:.2f})"))
    return r


def _nfc(s):
    """Compose combining sequences, so an engine that emits "a + combining
    macron" compares equal to one that emits the precomposed character."""
    import unicodedata
    return unicodedata.normalize("NFC", s)


def _utf8_positions(p: Page, prefix, expect):
    """Assert the accented payload that follows each position sentinel.

    Shared by the two UTF-8 cases, which differ only in their repertoire.
    `expect` maps a sentinel to the word that must follow it -- the point
    being that the text has to survive the machinery of each position, not
    merely that the file compiled.
    """
    # \glt sets its line inside quotes, which pdftotext glues to the first
    # and last word of it ("‘U8TRANS", "tükörfúrógép’"), so neither the
    # sentinel nor the payload can be matched whole.
    quotes = "‘’“”`'"
    r = []
    words = p.words
    for sent, want in expect.items():
        hits = [i for i, w in enumerate(words) if sent in w.text]
        if len(hits) != 1:
            r.append((False, f"{sent}: expected once, found {len(hits)}"))
            continue
        i = hits[0]
        got = (_nfc(words[i + 1].text).strip(quotes)
               if i + 1 < len(words) else "<end>")
        r.append(check(got == _nfc(want),
                       f"{prefix} {sent}: {want!r} survives (got {got!r})"))
    return r


def a_utf8(p: Page):
    r"""Literal UTF-8 in every example position, all three engines.

    The "ç" bug lived here: under pdflatex inputenc expands an accented
    character into an accent command plus its argument, so raw UTF-8 in an
    example body is a different input from the \c c the other cases write.
    Compiling at all is half the assertion -- a clobbered accent command is
    a hard error, not a wrong glyph -- and the payload checks are the other
    half, since a mangled multi-byte character would still compile.
    """
    r = _utf8_positions(p, "utf8", {
        "U8SUBA":  "façade",          # \c   cedilla
        "U8SUBB":  "příliš",          # \v   caron
        "U8ROM":   "zażółć",          # \. \l \'
        "U8JUDGE": "Ünsinn",          # after a judgment mark
        "U8OBJ":   "smørrebrød",      # \o   object tier
        "U8GLOSS": "þjóðólfur",       # \th \dh  gloss tier
        "U8TRANS": "tükörfúrógép",    # \" \'  free translation
        "U8ALTGT": "šuppiluliuma",    # \v   after an \altg paradigm
    })
    txt = _nfc(" ".join(w.text for w in p.words))
    # running text, the baseline that always worked
    r.append(check("façade příliš zażółć" in txt,
                   "accents in running text before any example"))
    # the alternatives are collected token by token of their own
    for tok in ("çağrı", "tükör", "fúró", "příliš", "zażółć"):
        r.append(check(tok in txt, f"\\altn/\\altg alternative survives: {tok}"))
    # \exsource sets its argument in a box of its own
    r.append(check("(Þjóðólfur" in txt, "\\exsource argument survives"))
    # the breadth line and the two mis-extracting scripts are compile-only
    # here; their text is asserted in utf8-unicode.tex
    for sent in ("U8MAIN", "U8XTR"):
        r.append(check(p.find(sent) is not None, f"typeset: {sent}"))
    return r


def a_utf8_unicode(p: Page):
    r"""The repertoire pdflatex cannot represent: Hittite, Semitic,
    Vietnamese, IPA -- and the two scripts pdflatex typesets but
    mis-extracts, whose text can only be checked on a Unicode engine."""
    r = _utf8_positions(p, "utf8-unicode", {
        "UUSUBA":  "ḫattušili",   # breve-below, Hittite
        "UUSUBB":  "ʾarṣu",       # modifier half-ring, Semitic
        "UUROM":   "tiếng",       # stacked diacritics, Vietnamese
        "UUJUDGE": "ʿaraḏ",       # ayin + macron-below, after a judgment
        "UUOBJ":   "ḫattušili",   # object tier
        "UUGLOSS": "Hattusili",   # gloss tier
        "UUTRANS": "ʾarṣu",       # free translation
        "UUXTR":   "kṛṣṇaḥ",      # dot-below: correct only here
    })
    txt = _nfc(" ".join(w.text for w in p.words))
    # comma-below, the other script pdflatex mis-extracts ("gimen , u")
    r.append(check("ģimeņu" in txt,
                   "Latvian comma-below extracts correctly on a Unicode engine"))
    r.append(check("ẓāhir" in txt, "Semitic emphatic in the object tier"))
    for tok in ("ḫattuša", "ʾarṣu", "ḫatti", "tiếng"):
        r.append(check(tok in txt, f"alternative survives: {tok}"))
    r.append(check(p.find("UUMAIN") is not None, "typeset: UUMAIN"))
    return r


def a_hypanchors(p: Page):
    r"""hyperref anchors for footnote sub-examples must not collide with
    main-text ones.

    \theSubExNo branches on \if@noftnote and \theHSubExNo did not, so a
    sub-example "a" in a footnote and one under main example 1 both claimed
    the anchor "lxex.1.a".  hyperref keeps the FIRST destination of a name
    and drops the rest, so \ref to the footnote sub-example linked to the
    main-text one.  The printed numbers stayed correct throughout -- which
    is why the whole suite passed over it -- so the anchors themselves are
    the subject here, read off the .aux.
    """
    r = []
    aux = getattr(p, "aux", "")
    txt = " ".join(w.text for w in p.words)

    def anchor(label):
        m = re.search(r"\\newlabel\{" + re.escape(label)
                      + r"\}\{.*?\}\{[^{}]*\}\{[^{}]*\}\{([^{}]*)\}",
                      aux, re.S)
        return m.group(1) if m else None

    got = {k: anchor(k) for k in
           ("h:mainsub", "h:fnsub", "h:mainrom", "h:fnrom")}
    r.append(check(all(got.values()),
                   f"every \\label recorded an anchor in the .aux (got {got})"))
    # the letter level, and the roman level under it
    r.append(check(got["h:mainsub"] != got["h:fnsub"],
                   f"footnote and main-text sub-example have distinct anchors "
                   f"({got['h:fnsub']} vs {got['h:mainsub']})"))
    r.append(check(got["h:mainrom"] != got["h:fnrom"],
                   f"footnote and main-text roman sub-sub-example have "
                   f"distinct anchors ({got['h:fnrom']} vs {got['h:mainrom']})"))
    # and the footnote ones are on the footnote series, like \theHFnExNo --
    # merely being distinct could still be an anchor built from the wrong
    # counter
    r.append(check((got["h:fnsub"] or "").startswith("SubExNo.lxfnex."),
                   f"footnote sub-example anchors use the footnote series "
                   f"({got['h:fnsub']})"))
    r.append(check((got["h:fnrom"] or "").startswith("SubSubExNo.lxfnex."),
                   f"footnote roman anchors use the footnote series "
                   f"({got['h:fnrom']})"))
    r.append(check((got["h:mainsub"] or "").startswith("SubExNo.lxex."),
                   f"main-text sub-example anchors are unchanged "
                   f"({got['h:mainsub']})"))
    # the engines that DO report a duplicate destination must not report one
    # (pdflatex: "destination with the same identifier"; lualatex:
    # "ignoring duplicate destination with the name").  Vacuous under
    # xelatex, where the collision is resolved downstream by xdvipdfmx.
    log = getattr(p, "log", "")
    for phrase in ("same identifier", "duplicate destination"):
        r.append(check(phrase not in log,
                       f"no duplicate-destination warning ({phrase!r})"))
    # the printed numbers were always right and must stay right
    for sent, want in (("HAREFSUB", "(1a)"), ("HAREFFNSUB", "(ia)"),
                       ("HAREFROM", "(1a-i)"), ("HAREFFNROM", "(ia-i)")):
        r.append(check(f"{sent} {want}" in txt,
                       f"{sent} still prints {want}; got "
                       f"{txt[txt.find(sent):][:20]!r}"))
    return r


def a_cleveref(p: Page):
    r"""\cref on an example: bare numbers, and cleveref's list/range handling.

    Without linguexx's declarations cleveref has no name for the example
    counters and prints "?? (1)".
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    r.append(check("??" not in txt, f"no unknown-type marker; got {txt[-90:]!r}"))
    for sent, want in (("CVSINGLE", "(1)"), ("CVSUB", "(1a)"),
                       ("CVROMAN", "(1b-i)"), ("CVCAP", "(1)"),
                       ("CVFNREF", "(i)"), ("CVPLAIN", "(1a)")):
        r.append(check(f"{sent} {want}" in txt,
                       f"{sent} is {want}; got {txt[txt.find(sent):][:18]!r}"))
    # what \cref adds over \ref: lists and ranges
    r.append(check("CVMULTI (1) and (2)" in txt,
                   f"\\cref over two labels; got "
                   f"{txt[txt.find('CVMULTI'):][:26]!r}"))
    r.append(check("CVRANGE (1a) and (1b)" in txt,
                   f"\\cref over two sub-examples; got "
                   f"{txt[txt.find('CVRANGE'):][:28]!r}"))
    # \crefrange is the other combining form and reaches the empty
    # \crefname declarations by the range route rather than the list one,
    # so the \cref lists above did not cover it: a name leaking through
    # would print "example (1a) to example (1b)".
    r.append(check("CVCREFRANGE (1a) to (1b)" in txt,
                   f"\\crefrange over two sub-examples; got "
                   f"{txt[txt.find('CVCREFRANGE'):][:31]!r}"))
    r.append(check("CVCREFRANGEMAIN (1) to (2)" in txt,
                   f"\\crefrange over two whole examples; got "
                   f"{txt[txt.find('CVCREFRANGEMAIN'):][:33]!r}"))
    # ... and why linguexx's own \refrange is not redundant with it:
    # cleveref spells both endpoints out, \refrange compresses the shared
    # "(1" prefix to "(1a--b)".  pdftotext maps the T1 en-dash to a control
    # byte, so normalise as a_refs does.
    norm = re.sub(r"[^\x20-\x7e]", "-", txt)
    r.append(check(re.search(r"CVREFRANGE \(1a-+b\)", norm),
                   f"\\refrange compresses the shared prefix; got "
                   f"{norm[norm.find('CVREFRANGE'):][:24]!r}"))
    r.append(check("CVREFRANGE (1a) to (1b)" not in txt,
                   "\\refrange is not cleveref's spelling of the same range: "
                   "the two forms are distinct and neither replaces the other"))
    return r


def a_cleveref_named(p: Page):
    r"""A \crefname the document sets itself must win.

    linguexx declares its defaults \AtBeginDocument, which runs after the
    preamble, so without the guard it would silently overwrite the author's
    choice -- and the failure would be invisible except to someone who knew
    what they had asked for.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    r.append(check("CVSINGLE example (1)" in txt,
                   f"the document's \\crefname survives; got "
                   f"{txt[txt.find('CVSINGLE'):][:26]!r}"))
    r.append(check("CVMULTI examples (1) and (2)" in txt,
                   f"...including its plural; got "
                   f"{txt[txt.find('CVMULTI'):][:34]!r}"))
    r.append(check("CVCAP Example (1)" in txt,
                   f"...and its capitalised form; got "
                   f"{txt[txt.find('CVCAP'):][:22]!r}"))
    # a counter it did NOT name keeps the bare linguexx default
    r.append(check("CVSUB (1a)" in txt,
                   f"a counter it did not name stays bare; got "
                   f"{txt[txt.find('CVSUB'):][:16]!r}"))
    return r


def a_babel_fr(p: Page):
    r"""French babel: active ? as a judgment mark, and \og...\fg.

    Two independent hazards in one language.  babel makes ? ! : ; ACTIVE for
    French spacing, and ? is one of linguexx's judgment marks -- that works
    only because the scanner uses \peek_charcode, which ignores catcode, so
    switching it to \peek_catcode or \peek_meaning would look like a tidy-up
    and silently stop judgments working in French.  And \fg is babel's
    closing guillemet, which linguexx used to destroy in either load order.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    # the guillemets survive: BOTH marks, the closing one being the casualty
    r.append(check("«" in txt and "»" in txt,
                   f"\\og...\\fg keeps both guillemets; got "
                   f"{txt[txt.find('FRGUIL'):][:34]!r}"))
    # judgments hang and do not displace the text, exactly as elsewhere --
    # but here every ? in the source is an active character
    base = p.find("FRPLAIN").x0
    for sent in ("FRQ", "FRQQ", "FRQS", "FRST"):
        w = p.find(sent)
        r.append(check(abs(w.x0 - base) < TOL,
                       f"{sent}: active-? judgment does not displace the text "
                       f"({w.x0:.2f} vs {base:.2f})"))

    def mark_x(sent):
        """Leftmost non-label token on the sentinel's line: the hung mark."""
        w = p.find(sent)
        lab = re.compile(r"^([a-f]\.|\(\d+\))$")
        toks = [t for t in p.line_of(w)
                if not lab.match(t.text) and not t.text.startswith(sent)]
        return min((t.x0 for t in toks), default=None)

    for sent in ("FRQ", "FRQQ", "FRQS", "FRST"):
        x = mark_x(sent)
        r.append(check(x is not None and x < base - 0.5,
                       f"{sent}: the mark hangs left of the text ({x})"))
    # a two-character mark is collected across TWO active tokens, so it is
    # wider and hangs further out than a one-character one
    r.append(check(mark_x("FRQQ") < mark_x("FRQ") - 0.5,
                   f"?? is collected whole and hangs further left than ? "
                   f"({mark_x('FRQQ')} vs {mark_x('FRQ')})"))
    # a sentence-final ? is French punctuation, not a judgment: the scanner
    # only looks at the start of an example
    r.append(check("FRFINAL" in txt and txt.rstrip().endswith("?")
                   or "correcte ?" in txt,
                   f"a sentence-final ? stays punctuation; got "
                   f"{txt[txt.find('FRFINAL'):][:44]!r}"))
    return r


def a_babel_fr_order(p: Page):
    r"""babel BEFORE linguexx: the order in which a clobber sticks.

    \AtBeginDocument hooks run in registration order, so with linguexx
    loaded second its hook has the last word on \fg -- and claiming the dot
    shorthands unconditionally then overwrote babel's closing guillemet with
    no error at all.  With linguexx first, babel re-establishes \fg
    afterwards and hides the whole problem, which is why both orders are
    here.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    r.append(check("«" in txt and "»" in txt,
                   f"\\og...\\fg keeps both guillemets with babel loaded "
                   f"first; got {txt[txt.find('FRQGUIL'):][:36]!r}"))
    base = p.find("FRQPLAIN").x0
    w = p.find("FRQMARK")
    r.append(check(abs(w.x0 - base) < TOL,
                   f"judgments still work in this order "
                   f"({w.x0:.2f} vs {base:.2f})"))
    return r


def a_babel_de(p: Page):
    r"""German babel: the active " shorthand inside linguexx constructs.

    linguexx never peeks for ", but an example body is COLLECTED token by
    token before being typeset, and the collector appends with an expanding
    variant -- so an active character could have been expanded away from the
    context babel expects, in the body, a gloss tier or an \altn stack, each
    of which walks its input separately.
    """
    r = []
    txt = _nfc(" ".join(w.text for w in p.words))
    for tok, where in (("Höhle", 'main example ("o)'),
                       ("Zuckerguss", 'sub-example ("-)'),
                       ("süß", 'sub-example ("u and "s)'),
                       ("groß", "gloss tier"),
                       ("Fußball", "\\altn alternative")):
        r.append(check(tok in txt, f'babel " shorthand survives in the '
                                   f'{where}: {tok}'))
    for sent in ("DEMAIN", "DESUB", "DEOBJ", "DEGLOSS", "DEALT"):
        r.append(check(p.find(sent) is not None, f"typeset: {sent}"))
    return r


def a_lpzgsetup(p: Page):
    r"""\lpzglistsetup, \lpzglisttitle and \lpzglistentry.

    tests/lpzglist.tex drives everything through per-list \lpzglist[...]
    keys; this pins the document-wide half -- the settings that apply to
    every list, and the two commands the manual says to redefine wholesale
    -- and that a per-list key beats them without disturbing the rest.
    """
    r = []
    txt = " ".join(w.text for w in p.words)

    def n(tok):
        return len(p.find_all(tok))

    # \lpzglisttitle, redefined wholesale, heads all three lists
    r.append(check(n("LSTITLEMARK") == 3,
                   f"redefined \\lpzglisttitle heads every list "
                   f"(got {n('LSTITLEMARK')} of 3)"))
    # the document-wide title reaches the plain list; a per-list title beats
    # it; and the third list has its own again
    for tok, what in (("LSSETUPTITLE", "\\lpzglistsetup sets the title"),
                      ("LSOVERTITLE", "a per-list title overrides the setup"),
                      ("LSSTYLETITLE", "and again for the third list")):
        r.append(check(tok in txt, f"{what} ({tok})"))
    # \lpzglistentry, redefined wholesale, formats the entries of both lists
    # that do not override it: two abbreviations x two lists
    r.append(check(n("LSENTRY") == 4,
                   f"redefined \\lpzglistentry formats every non-overriding "
                   f"list (got {n('LSENTRY')} of 4)"))
    # format= is the one-shot form and takes precedence for its own list only
    r.append(check(n("LSFMT") == 2,
                   f"format= overrides the wholesale \\lpzglistentry for one "
                   f"list (got {n('LSFMT')} of 2)"))
    # sort=true from the setup: alphabetical, not the order of first use
    # (pst is used first, prs second)
    r.append(check(txt.find("prs=present") < txt.find("pst=past"),
                   "sort=true from \\lpzglistsetup orders the entries"))
    # style=inline from the setup: the two entries of the plain list sit on
    # one line ...
    e = p.find_all("LSENTRY")
    r.append(check(len(e) >= 2 and e[1] in p.line_of(e[0]),
                   "style=inline from \\lpzglistsetup keeps entries on one "
                   "line"))
    # ... while the list that overrides style=list puts them on their own
    f = p.find_all("LSFMT")
    r.append(check(len(f) == 2 and f[1] not in p.line_of(f[0]),
                   "a per-list style=list overrides the inline setup"))
    return r


def a_lpzgcheck(p: Page):
    r"""\lpzgcheck reports on abbreviations in a document with no \lpzglist.

    Asserted on the .log, because a warning is the whole output here.  Note
    this case has no \lpzglist at all: before \lpzgcheck existed, an
    unexplained key in such a document was reported nowhere.
    """
    r = []
    log = getattr(p, "log", "")
    # the typo IS reported, by default, with no \lpzglist anywhere
    r.append(check("No expansion known for pres" in log,
                   "an unexplained key is reported without \\lpzglist"))
    # ... and reported once, not once per use
    r.append(check(log.count("No expansion known for pres") == 1,
                   f"reported once, not per use (got "
                   f"{log.count('No expansion known for pres')})"))
    # an exempted key is not reported
    r.append(check("proj" not in log.split("No expansion known for")[-1][:80],
                   "an ignore={} key is not reported"))
    # `unused' is opt-in: this file declares zzz and never uses it, and does
    # NOT ask for the check, so it must stay quiet
    r.append(check("never used" not in log,
                   "declared-but-unused is opt-in and stays quiet by default"))
    # a trailing period (\lpzg{sg.}) splits off an EMPTY segment, which was
    # recorded as a used key and then reported -- "No expansion known for ."
    # -- naming a key the author cannot find in the source.  Blank segments
    # are now skipped, so the ONLY key reported here is the real typo.
    # The check names all its keys in ONE message ("... for pres and ."), so
    # the whole clause has to be read, not the first word of it: an empty
    # key shows up as a dangling "and ." at the end.
    m = re.search(r"No expansion known for ([^\n]*)", log)
    reported = m.group(1).strip().rstrip(".").strip() if m else None
    r.append(check(reported == "pres",
                   f"only the real typo is reported, no empty key; the check "
                   f"named {reported!r}"))
    # ... and skipping the blank segment must not lose the real one beside
    # it: sg is still recorded, exactly once, in the .aux
    used = re.findall(r"\\lx@lpzg@used\{([^{}]*)\}", getattr(p, "aux", ""))
    r.append(check(used.count("sg") == 1,
                   f"sg is still recorded once from \\lpzg{{sg.}}; got {used}"))
    r.append(check("" not in used,
                   f"no empty key is written to the .aux; got {used}"))
    # the document still typeset
    for tok in ("LPZGBODY", "LPZGTRANS"):
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
    r.append(check(got == ["(1)", "(2)", "(3)", "(4)", "(5)", "(6)", "(7)"],
                   f"exe batch numbers each \\ex; dot syntax continues; got {got}"))
    letters = [w.text for w in p.words if w.text in ("a.", "b.", "c.", "d.", "i.")]
    r.append(check(letters == ["a.", "b.", "c.", "i.", "d.", "a."],
                   f"xlist letters and nested roman; got {letters}"))
    # \z. inside an exe batch pops the sub-level that "\a." opened, so the
    # following \ex is a MAIN-level example again.  Both halves matter: the
    # \z. used to be a hard package error ("\z. outside an example", because
    # only the dot syntax sets \lx@inexample), and with it omitted the next
    # \ex was silently demoted to sub-item "b." -- so the number sequence
    # above and the x-position here are each the assertion for one half.
    five, six, zsub = p.find("GBFIVE"), p.find("GBSIX"), p.find("GBZSUB")
    r.append(check(zsub.x0 > five.x0 + 2,
                   f"\\a. inside exe opens a sub-level ({zsub.x0:.2f} vs "
                   f"{five.x0:.2f})"))
    r.append(check(abs(six.x0 - five.x0) < TOL,
                   f"\\ex after \\z. is back at the exe main level "
                   f"({six.x0:.2f} vs {five.x0:.2f}, sub-level was "
                   f"{zsub.x0:.2f})"))
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


def _qdf(pdf: Path):
    """The PDF normalised by qpdf, as text.

    Object streams hold the structure tree, and neither poppler tool
    unpacks them: pdfinfo -struct-text prints element names but drops the
    attribute CLASSES an element points at with /C, which is exactly what
    the list-numbering assertions are about.
    """
    if not shutil.which("qpdf"):
        raise AssertionError(
            "qpdf is not on PATH: the structure tree's attribute classes "
            "cannot be read (no poppler tool unpacks them)")
    return subprocess.run(
        ["qpdf", "--qdf", "--object-streams=disable", str(pdf), "-"],
        capture_output=True).stdout.decode("latin-1")


def struct_ol_classes(pdf: Path):
    """How many list elements point at each of this package's /ListNumbering
    attribute classes.

    The class is what a screen reader announces, and the printed label is
    what the page shows.  Nothing makes them agree except the code that
    sets both, so a list labelled "A." whose class says LowerRoman is
    well-formed PDF, passes veraPDF, and is false -- invisible to every
    other check in this file.  Counting the /C references is the only way
    to see it; the ClassMap alone is not enough, because a class is written
    there whether or not anything uses it.
    """
    from collections import Counter
    return Counter(re.findall(r"/C\s*/(lxOL[a-z]+)", _qdf(pdf)))


def struct_has_formula(pdf: Path):
    """True if the structure tree contains a Formula element.

    \\altn, \\altg and (under [langsci]) \\exp and \\atcenter are written in
    text mode precisely so that none appears: a Formula in a PDF/UA-2
    document needs an /Alt or a MathML association, and the 0.12 rewrite of
    \\altg exists because of it.  Upstream langsci-gb4e writes both of the
    latter two in math mode.
    """
    return bool(re.search(r"/S\s*/Formula", _qdf(pdf)))


def a_langsci(p: Page):
    r"""[langsci] alone: \ea ... \z with the dot syntax not loaded.

    What is on trial is that the depth comes off the NESTING and nothing
    else.  \ea is one command at every level -- it opens a top-level
    example, a letter level or a roman level depending only on what is
    already open -- so a dispatch that is off by one produces a page that
    is entirely plausible and entirely wrong, with the sub-examples of the
    second example hanging off the first.  Hence the positions below rather
    than a token list: every level is measured against its own parent and
    against its own sibling.
    """
    r = []
    labw = [w for w in p.words if re.fullmatch(r"\(\d+\)", w.text)]
    margin = min(w.x0 for w in labw)
    got = [w.text for w in labw if abs(w.x0 - margin) < TOL]
    r.append(check(got == ["(1)", "(2)", "(3)", "(4)", "(5)", "(6)", "(7)"],
                   f"one counter across every shape the front-end has; "
                   f"got {got}"))
    letters = [w.text for w in p.words if w.text in ("a.", "b.", "c.", "i.")]
    r.append(check(letters == ["a.", "b.", "i.", "c.", "a.", "b."],
                   f"letters, a nested roman, and the \\eal list; "
                   f"got {letters}"))
    # --- the nesting itself ---------------------------------------------
    two, three = p.find("LSTWO"), p.find("LSTHREE")
    suba, subb, subc = p.find("LSSUBA"), p.find("LSSUBB"), p.find("LSSUBC")
    roman = p.find("LSROMANA")
    r.append(check(suba.x0 > two.x0 + 2,
                   f"a nested opener deepens ({suba.x0:.2f} vs {two.x0:.2f})"))
    r.append(check(roman.x0 > suba.x0 + 2,
                   f"a second nesting reaches the romans "
                   f"({roman.x0:.2f} vs {suba.x0:.2f})"))
    r.append(check(abs(subc.x0 - suba.x0) < TOL,
                   f"the closer returns to the letters, it does not leave "
                   f"the roman level open ({subc.x0:.2f} vs {suba.x0:.2f})"))
    r.append(check(abs(three.x0 - two.x0) < TOL,
                   f"and again to the main level, where a further \\ex is a "
                   f"top-level example ({three.x0:.2f} vs {two.x0:.2f}, "
                   f"letters were at {suba.x0:.2f})"))
    # --- the bracket judgment, at a level the front-end opened ----------
    r.append(check(abs(subb.x0 - suba.x0) < TOL,
                   f"[judgment] does not displace the text "
                   f"({subb.x0:.2f} vs {suba.x0:.2f})"))
    lab = re.compile(r"^([a-f]\.|[ivx]+\.|\(\d+\))$")
    hung = [w for w in p.line_of(subb)
            if not lab.match(w.text) and w is not subb and w.x1 <= subb.x0 + TOL]
    r.append(check(hung, f"the mark hangs left of the text; found {hung}"))
    # --- \eal: a head with no text, and the letters under it ------------
    lsla, lslb = p.find("LSLA"), p.find("LSLB")
    r.append(check(abs(lsla.x0 - suba.x0) < TOL,
                   f"\\eal opens the SAME letter level as a nested opener "
                   f"({lsla.x0:.2f} vs {suba.x0:.2f})"))
    r.append(check(abs(lslb.x0 - lsla.x0) < TOL,
                   f"and its second item stays there "
                   f"({lslb.x0:.2f} vs {lsla.x0:.2f})"))
    # The head takes no text, so its number shares a line with the first
    # letter.  This is the half of \eal that a token list cannot see: give
    # the head an item it does not deserve and the letters move down a line.
    r.append(check(any(w.text == "(4)" for w in p.line_of(lsla)),
                   f"the \\eal head number sits on its first letter's line; "
                   f"that line is {[w.text for w in p.line_of(lsla)][:4]}"))
    # --- the four-tier gloss the option brings ---------------------------
    tiers = [p.find(t) for t in ("LSGOBJ", "LSGONE", "LSGTWO", "LSGTRI")]
    r.append(check(all(abs(t.x0 - tiers[0].x0) < TOL for t in tiers),
                   f"\\gllll aligns four tiers in one column; got "
                   f"{[round(t.x0, 2) for t in tiers]}"))
    r.append(check([t.y0 for t in tiers] == sorted(t.y0 for t in tiers),
                   f"and stacks them in order; got "
                   f"{[round(t.y0, 1) for t in tiers]}"))
    # --- justification: the one deliberate difference from langsci -------
    # Justified, every line but the last ends exactly at the right margin;
    # ragged, none of them does.  Measured against the margin the JUSTIFIED
    # example establishes, so the check needs no page geometry of its own.
    just = _band_lines(p, p.find("LSJUST").y0 - 1, p.find("LSRAG").y0 - 1)
    rag = _band_lines(p, p.find("LSRAG").y0 - 1, p.find("LSREFS").y0 - 1)
    edges = lambda lines: [max(w.x1 for w in line) for line in lines]
    je, re_ = edges(just), edges(rag)
    r.append(check(len(je) >= 2 and len(re_) >= 2,
                   f"both justification examples wrapped ({len(je)} and "
                   f"{len(re_)} lines)"))
    if len(je) >= 2 and len(re_) >= 2:
        margin = max(je[:-1])
        r.append(check(all(abs(e - margin) < TOL for e in je[:-1]),
                       f"the default is justified: every full line reaches "
                       f"the margin; got {[round(e, 1) for e in je]}"))
        # Not "no ragged line reaches the margin": a ragged line can break
        # flush by accident, and one in this very example does.  What
        # separates the settings is that the justified lines are all the
        # SAME length and the ragged ones are not.
        r.append(check(min(re_[:-1]) < margin - 2,
                       f"\\ExRaggedRight: the full lines no longer all end "
                       f"at the margin ({[round(e, 1) for e in re_]} against "
                       f"{margin:.1f})"))
    txt = " ".join(w.text for w in p.words)
    # Both reference flavours on one line.  [langsci] leaves \ref bare, as
    # langsci-gb4e does -- an author there writes "(\ref{ex:x})" or \xref --
    # while \Last is this package's own and parenthesises whatever the
    # flavour.  Asserted together, because a change that took the
    # parentheses off both would look right in either half alone.
    r.append(check("LSREFS 1 and (7)." in txt,
                   f"\\ref is bare under [langsci] and \\Last is not; got "
                   f"{txt[txt.find('LSREFS'):][:24]!r}"))
    return r


def a_langsci_mixed(p: Page):
    r"""[lazy,langsci]: the migration case, both syntaxes in one document.

    The property that makes an example-at-a-time migration possible is that
    converting one example changes nothing around it, and that is what is
    measured: one counter through all three syntaxes, and a converted
    example whose sub-levels land exactly where the unconverted example's
    did.  A front-end with its own counter or its own geometry would pass
    every other case in this suite and fail here.

    It also pins the two carve-outs from the one-syntax-per-example rule --
    \a. inside an exe batch (the [lazy,gb4e] promise, which [langsci] must
    not have narrowed) and a footnote holding an example written the other
    way.  Both are asserted from the page, because both fail silently: the
    first by demoting the next example to a sub-item, the second by
    refusing to compile at all.
    """
    r = []
    labw = [w for w in p.words if re.fullmatch(r"\(\d+\)", w.text)]
    margin = min(w.x0 for w in labw)
    got = [w.text for w in labw if abs(w.x0 - margin) < TOL]
    r.append(check(got == ["(1)", "(2)", "(3)", "(4)", "(5)"],
                   f"one counter runs through the dot syntax, the front-end "
                   f"and an exe batch; got {got}"))
    # --- a converted example has the geometry of an unconverted one ------
    dot, ea = p.find("MXDOT"), p.find("MXEA")
    dota, dotb = p.find("MXDOTA"), p.find("MXDOTB")
    eaa, eab = p.find("MXEAA"), p.find("MXEAB")
    r.append(check(abs(ea.x0 - dot.x0) < TOL,
                   f"main level, both syntaxes ({ea.x0:.2f} vs {dot.x0:.2f})"))
    r.append(check(abs(eaa.x0 - dota.x0) < TOL,
                   f"letter level, both syntaxes: converting an example does "
                   f"not move it ({eaa.x0:.2f} vs {dota.x0:.2f})"))
    r.append(check(abs(eab.x0 - dotb.x0) < TOL,
                   f"and its second sub-example likewise "
                   f"({eab.x0:.2f} vs {dotb.x0:.2f})"))
    r.append(check(eaa.x0 > ea.x0 + 2,
                   f"the converted example really has a sub-level "
                   f"({eaa.x0:.2f} vs {ea.x0:.2f})"))
    # --- carve-out 1: \a. ... \z. inside an exe batch, untouched ---------
    exe, exea, exeb = p.find("MXEXE"), p.find("MXEXEA"), p.find("MXEXEB")
    r.append(check(exea.x0 > exe.x0 + 2,
                   f"\\a. still opens a sub-level inside exe "
                   f"({exea.x0:.2f} vs {exe.x0:.2f})"))
    r.append(check(abs(exeb.x0 - exe.x0) < TOL,
                   f"and \\z. still closes it, so the next \\ex is a "
                   f"top-level example and not sub-item b. "
                   f"({exeb.x0:.2f} vs {exe.x0:.2f}, sub-level was "
                   f"{exea.x0:.2f})"))
    # --- carve-out 2: a footnote holds an example of the other syntax ----
    # It compiles at all only because the footnote boundary clears the
    # "an example is open" flags; and the number proves it went onto the
    # footnote series rather than the main one.
    r.append(check(p.find("MXFNEX") is not None,
                   "a dot-syntax example inside a footnote of a converted "
                   "example typesets"))
    fnlab = [w.text for w in p.words if re.fullmatch(r"\(i+\)", w.text)]
    r.append(check(fnlab == ["(i)"],
                   f"and is numbered on the footnote series; got {fnlab}"))
    txt = " ".join(w.text for w in p.words)
    # Bare, both of them: the reference flavour is the DOCUMENT's, not the
    # example's, so an example written in the dot syntax references the
    # same way as one written with \ea.  \Last keeps its parentheses (see
    # a_langsci), which is what makes the line worth reading.
    r.append(check("Refs: 1, 2 and (5)." in txt,
                   f"references resolve across the syntaxes; got "
                   f"{txt[txt.find('Refs'):][:26]!r}"))
    return r


def _langsci_widths(p: Page):
    """(two-digit x, three-digit x, four-digit x, item penalty) off the page.

    Shared by the two option cases, which carry the same sentinels on
    purpose: neither is an assertion by itself.  With the option code
    deleted, langsci-options still shows an unwidened box and a kernel
    penalty -- exactly what it asserts -- so what is being checked is that
    the two cases DIFFER, and that only holds if one function reads both.
    """
    xs = tuple(p.find(t).x0 for t in ("WSMALL", "WBIG", "WHUGE"))
    m = re.search(r"(-\d+)", " ".join(
        w.text for w in p.line_of(p.find("WPENALTY"))))
    return xs + (m.group(1) if m else None,)


def a_langsci_exewidth(p: Page):
    r"""autoexewidth on, and the kernel's item penalty."""
    r = []
    small, big, huge, pen = _langsci_widths(p)
    r.append(check(huge > small + 1,
                   f"autoexewidth widens the label box for a four-digit "
                   f"number ({huge:.2f} vs {small:.2f})"))
    # It must widen and never narrow.  The default box is already wider than
    # "(235)", so an \exewidth that simply set the sample moved a three-digit
    # document's text LEFT of a two-digit one's -- which is what this line
    # catches and what the first implementation did.
    r.append(check(abs(big - small) < TOL,
                   f"and does not NARROW it for a three-digit one "
                   f"({big:.2f} vs {small:.2f})"))
    r.append(check(pen == "-51",
                   f"without [lowerpenalty] the item penalty is the "
                   f"kernel's; got {pen}"))
    return r


def a_langsci_options(p: Page):
    r"""[manualexewidth] and [lowerpenalty]: the same two knobs, given."""
    r = []
    small, big, huge, pen = _langsci_widths(p)
    r.append(check(abs(huge - small) < TOL and abs(big - small) < TOL,
                   f"[manualexewidth] leaves the label box alone at every "
                   f"width ({small:.2f}, {big:.2f}, {huge:.2f})"))
    r.append(check(pen == "-1000",
                   f"[lowerpenalty] lowers the item penalty, so a batch may "
                   f"break across a page; got {pen}"))
    return r


def a_langsci_lists(p: Page):
    r"""The sub-level numbering variants.

    Each variant is asserted by the label its item actually prints, read off
    the line rather than from a token list, because what makes a variant
    wrong is that it prints the numbering of a DIFFERENT variant -- a page
    that looks entirely plausible until it is compared with the source.

    xlistabr and qlist are not among them: neither has ever worked upstream,
    so [langsci] refuses them by name rather than invent a behaviour, and
    langsci-retired.tex is where that is asserted.
    """
    r = []

    def label_of(tok):
        """The leftmost word on the sentinel's line, when it is left of it."""
        w = p.find(tok)
        line = p.line_of(w)
        left = [t for t in line if t.x1 <= w.x0 + TOL]
        return left[0].text if left else None

    want = [("LLDEFAULT", "a."), ("LLALPH", "a."), ("LLROMAN", "i."),
            ("LLARABIC", "1."), ("LLUPALPH", "A."), ("LLUPROMAN", "I.")]
    got = [(tok, label_of(tok)) for tok, _ in want]
    r.append(check(got == want,
                   f"each numbering variant prints its own numbering; "
                   f"got {got}"))
    # One label box for every level, whatever the numbering: the variants
    # must not move the text they label.
    xs = [p.find(tok).x0 for tok, _ in want]
    r.append(check(max(xs) - min(xs) < TOL,
                   f"a variant does not move the text it labels; got "
                   f"{[round(x, 2) for x in xs]}"))
    # A variant is set in the environment's OWN group.  Set anywhere wider
    # and the plain xlist after five of them would still be numbering in
    # upper roman -- and would keep doing so for the rest of the document.
    r.append(check(label_of("LLAGAIN") == "a.",
                   f"a variant does not leak into the next list; the plain "
                   f"xlist after five of them prints "
                   f"{label_of('LLAGAIN')!r}"))
    return r


def a_langsci_names(p: Page):
    r"""Every name langsci-gb4e defines is still defined here.

    Twenty-five of them are provided and two -- xlistabr and qlist -- are
    defined to complain, neither having ever worked upstream.  What the
    provided ones do is asserted elsewhere; what this case catches is a name
    that has gone missing, which a ported document meets as "Undefined
    control sequence" with nothing to say the name was ever a langsci-gb4e
    one.  The case prints NAMEOK for each name that exists and
    NAMEBAD-<name> for each that does not.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    bad = re.findall(r"NAMEBAD-\S+", txt)
    ok = txt.count("NAMEOK")
    r.append(check(not bad, f"every langsci-gb4e name is defined; missing {bad}"))
    r.append(check(ok == 27,
                   f"all 27 names checked; the page shows {ok}"))
    return r


def a_langsci_refs(p: Page):
    r"""The reference flavour [langsci] selects, and what does not follow it.

    Bare \ref is langsci-gb4e's convention and parenthesised \ref is
    linguex's; the option picks the one that matches the syntax the
    document is written in, so a ported "(\ref{ex:x})" stops printing
    "((1))".

    Every number the PACKAGE prints stays parenthesised -- the label, \Next
    and \Last, \xref, \xxref, \Refrange -- and that is asserted on the same
    page, because the tempting one-line version of this change (drop the
    parentheses from \theExNo) takes the example's own label with it and
    would pass a case that only read \ref.
    """
    r = []
    txt = " ".join(w.text for w in p.words)

    def between(start, end):
        i, j = txt.find(start), txt.find(end)
        return txt[i + len(start):j].split() if 0 <= i < j else None

    # --- \ref is bare, at all three levels and on the footnote series ----
    r.append(check(between("LRREF ", " LRREFEND") == ["1", "2a", "2b-i"],
                   f"\\ref is bare at every level; got "
                   f"{between('LRREF ', ' LRREFEND')}"))
    r.append(check(between("LRREFFN ", " LRREFFNEND") == ["i"],
                   f"and on the footnote series; got "
                   f"{between('LRREFFN ', ' LRREFFNEND')}"))
    # --- the printed labels keep theirs ----------------------------------
    # Read off the LABEL COLUMN, not off the page: the parenthesised
    # references in the prose match the same pattern, and it is the label
    # that a change to \theExNo would silently strip.
    numbered = [w for w in p.words if re.fullmatch(r"\((\d+|i+)\)", w.text)]
    margin = min(w.x0 for w in numbered)
    labels = [w.text for w in numbered if abs(w.x0 - margin) < TOL]
    r.append(check(labels == ["(1)", "(2)", "(3)", "(4)", "(i)"],
                   f"the example numbers are still parenthesised; got "
                   f"{labels}"))
    # --- and so does everything the package prints itself ----------------
    dash = r"[-–—]+"
    for name, pat in [("\\xref", r"LRXREF \(1\)"),
                      ("\\xxref", r"LRXXREF \(1" + dash + r"2a\)"),
                      ("\\Refrange", r"LRRANGE \(1\)" + dash + r"\(2a\)"),
                      ("\\Next and \\Last", r"LRREL \(3\) \(2\)")]:
        sentinel = pat.split()[0]
        r.append(check(re.search(pat, txt) is not None,
                       f"{name} parenthesises whatever the flavour; the page "
                       f"has {txt[txt.find(sentinel):][:26]!r}"))
    # --- both switches, in both directions -------------------------------
    r.append(check(between("LRREFPAREN ", " LRREFPARENEND") == ["(3)"],
                   f"\\ExParenRefs puts the parentheses back; got "
                   f"{between('LRREFPAREN ', ' LRREFPARENEND')}"))
    r.append(check(between("LRREFBARE ", " LRREFBAREEND") == ["4"],
                   f"\\ExBareRefs takes them off again; got "
                   f"{between('LRREFBARE ', ' LRREFBAREEND')}"))
    return r


def a_langsci_hole(p: Page):
    r"""No empty line after an example whose last line is full.

    hyperref hangs the destination off \refstepcounter, and in horizontal
    mode that is a zero-width box added to the line being built -- so a
    counter stepped before the previous item's paragraph is closed leaves
    the NEXT example's anchor at the end of the PREVIOUS example's last
    line, behind the space that ended the source line.  On a full line the
    breaker takes that space and gives the anchor a line of its own, and
    the example is followed by a hole nothing in the source accounts for.

    Measured as two gaps rather than one distance, so the rule does not
    have to know a baselineskip: the middle item of each group is overfull
    by construction, and it must sit as far from its successor as from its
    predecessor.  With the anchor misplaced the second gap is twice the
    first, which is what the hole is.

    All three levels are checked because each steps its own counter in its
    own core.
    """
    r = []
    for level in ("MAIN", "SUB", "ROMAN"):
        one, two, three = (p.find("HOLE" + level + n).y0
                           for n in ("ONE", "TWO", "THREE"))
        before, after = two - one, three - two
        r.append(check(abs(after - before) < TOL,
                       f"{level.lower()}: the full item is followed by one "
                       f"line, not two ({after:.2f} after vs {before:.2f} "
                       f"before)"))
    return r


def a_langsci_ellipsis(p: Page):
    r"""An item may open with a literal ellipsis; \ex must not eat it.

    \ex peeks with \@ifnextchar, which skips spaces, so "\ex ... text" and
    "\ex. text" reach the peek identically and prose is taken for syntax.
    langsci-gb4e's \ex never peeked, and the continuation-style example
    this case is taken from (EISS 15, Fusco et al.) relies on that.

    Three assertions for one bug, because the peek damages three things
    and a fix confined to any one of them is not a fix:

    - the dots.  The peek consumes one, so ".." is rendered where the
      source wrote "...".
    - the level.  What follows the eaten dot is handed to the dot syntax,
      which opens a level of its own instead of adding an item to the
      one \ea opened: the sub-item becomes example (2).
    - the letters.  With the item promoted, the \ea group has a single
      lettered member, so "b." is absent from the page entirely.

    \ea, which opens a level and does not peek for a period, carries the
    same leading ellipsis as the control: ELLIPSUBA passing while
    ELLIPSUBB fails is the signature of this bug rather than of a
    document that simply mis-set its dots.
    """
    r = []
    got = p.labels()
    r.append(check(got == ["(1)"],
                   f"the \\ea example is one example; got {got}"))
    letters = [w.text for w in p.words if w.text in ("a.", "b.")]
    r.append(check(letters == ["a.", "b."],
                   f"both sub-items are lettered members of it; got "
                   f"{letters}"))
    for tok, label in (("ELLIPSUBA", "a."), ("ELLIPSUBB", "b.")):
        line = p.line_of(p.find(tok))
        texts = [w.text for w in line]
        r.append(check(texts[:2] == [label, "..."],
                       f"{tok}: the item opens with its letter and an "
                       f"intact ellipsis; got {texts[:2]}"))
    return r


def a_langsci_extra(p: Page):
    r"""The item variants, the box and reference helpers, \jambox, and the
    free translation's offset.

    \exp carries two of this package's invariants at once, and both are
    asserted elsewhere as well as here: it must not enter math mode (see
    a_langsci_ua, which checks the tree for a Formula element), and it must
    leave the LaTeX kernel's math operator alone -- upstream overwrites it,
    so a paper that writes both \exp{ex:5} and $\exp(x)$ loses the second.
    The last line of the case is the operator.
    """
    r = []

    def label_of(tok):
        w = p.find(tok)
        left = [t for t in p.line_of(w) if t.x1 <= w.x0 + TOL]
        return left[0].text if left else None

    host = p.find("LEHOST")
    r.append(check(label_of("LEEXI") == "ident",
                   f"\\exi labels an item with what it is given; got "
                   f"{label_of('LEEXI')!r}"))
    r.append(check(label_of("LEEXR") == "(1)",
                   f"\\exr labels it with another example's number; got "
                   f"{label_of('LEEXR')!r}"))
    # \exp's label is "(1" + a raised prime + ")", so pdftotext splits it;
    # the prime sits on a line of its own.  What matters is that the number
    # is there, parenthesised, and that something was raised beside it.
    r.append(check((label_of("LEEXP") or "").startswith("(1"),
                   f"\\exp labels it with the number too; got "
                   f"{label_of('LEEXP')!r}"))
    r.append(check(label_of("LESN") is None,
                   f"\\sn labels it with nothing at all; got "
                   f"{label_of('LESN')!r}"))
    # ...and none of the four moved the text, which is the point of a label
    # box: \exi's label is wider than the box and hangs out to the left.
    xs = {tok: p.find(tok).x0
          for tok in ("LEHOST", "LEEXI", "LEEXR", "LEEXP", "LESN")}
    r.append(check(max(xs.values()) - min(xs.values()) < TOL,
                   f"a custom label does not move the text; got "
                   f"{ {k: round(v, 2) for k, v in xs.items()} }"))
    # a judgment still hangs, on a plain item and on a custom-labelled one
    for tok in ("LEJUDGED", "LEJUDGEDEXI"):
        jw = p.find(tok)
        r.append(check(abs(jw.x0 - host.x0) < TOL,
                       f"{tok}: [judgment] still does not displace the text "
                       f"({jw.x0:.2f} vs {host.x0:.2f})"))
    # A custom label steps NO counter.  Five items in this batch carry one,
    # so if any of them stepped ExNo the numbers below would run to (8)
    # instead of (3) -- which is the only place the page shows it, the
    # labels themselves being whatever they were handed.
    # Read off the two items that DO step it rather than by collecting every
    # number at the margin: \exr's label is itself "(1)", set in the label
    # column, and nothing about its shape says it is a reference.
    nums = (label_of("LEJUDGED"), label_of("LEJAM"))
    r.append(check(nums == ("(2)", "(3)"),
                   f"\\exi, \\exr, \\exp and \\sn step no counter: the two "
                   f"items after them are {nums}, not (7) and (8)"))
    # ...and \exp's prime really is there: a prime that vanished would leave
    # every assertion above untouched.  Asserted by PRESENCE in the label
    # column and not by its raised position, because the engines disagree
    # about where it is -- pdflatex extracts the raised mark as a word of its
    # own on a line of its own, xelatex and lualatex fold it into the single
    # word "(1'\u0029".  Either way it is in the column left of the text.
    w0 = p.find("LEEXP")
    mid = (w0.y0 + w0.y1) / 2
    near = [w for w in p.words
            if w.x1 <= w0.x0 + TOL and abs((w.y0 + w.y1) / 2 - mid) < 12]
    blob = "".join(w.text for w in near)
    r.append(check(any(c in blob for c in ("'", "&apos;", "\u2032")),
                   f"\\exp sets a prime beside the number; the label column "
                   f"holds {[w.text for w in near]!r}"))
    # --- \jambox: the note starts \jamwidth from the right margin --------
    jam = p.find("(Greek)")
    body = p.find("LEJAM")
    r.append(check(any(w is jam for w in p.line_of(body)),
                   "\\jambox keeps its note on the example's line"))
    margin = max(w.x1 for w in p.words)
    r.append(check(abs((margin - jam.x0) - 144.54) < 1.5,
                   f"\\jambox starts \\jamwidth (2in) from the right margin; "
                   f"got {margin - jam.x0:.2f}pt"))
    # --- references -------------------------------------------------------
    txt = " ".join(w.text for w in p.words)
    r.append(check("LEXREF (1) and LEXXREF (1" in txt,
                   f"\\xref and \\xxref resolve; got "
                   f"{txt[txt.find('LEXREF'):][:34]!r}"))
    # --- \attop and \atcenter --------------------------------------------
    # Same two-line box, two alignments.  \attop puts its FIRST line on the
    # example's baseline; \atcenter straddles it.  Asserted against each
    # other, so neither can pass by sitting where the other should.
    top_base, cen_base = p.find("LEATTOP"), p.find("LEACBASE")
    ata, atb = p.find("LEATA"), p.find("LEATB")
    aca, acb = p.find("LEACA"), p.find("LEACB")
    r.append(check(abs(ata.y0 - top_base.y0) < 2.0 and atb.y0 > top_base.y0,
                   f"\\attop aligns its first line with the baseline "
                   f"({ata.y0:.1f} vs {top_base.y0:.1f}, second at "
                   f"{atb.y0:.1f})"))
    r.append(check(aca.y0 < cen_base.y0 < acb.y0,
                   f"\\atcenter straddles the baseline ({aca.y0:.1f} < "
                   f"{cen_base.y0:.1f} < {acb.y0:.1f})"))
    # --- \gltoffset -------------------------------------------------------
    with_off = p.find("LEGTRANS").y0 - p.find("LEGGLOSS").y0
    without = p.find("LEGTRANS2").y0 - p.find("LEGGLOSS2").y0
    r.append(check(with_off - without > 1.0,
                   f"\\gltoffset opens a gap above the free translation, "
                   f"and \\nogltOffset closes it ({with_off:.2f} vs "
                   f"{without:.2f})"))
    # --- the kernel's math operator survives ------------------------------
    r.append(check("exp(x)" in txt,
                   "the kernel's \\exp still typesets the math operator; "
                   "upstream overwrites it"))
    return r


def a_langsci_ua(p: Page):
    r"""The PDF/UA gate for the \ea front-end, asserted two ways.

    \ea opens an example, its list and its first item in one command, and
    \z closes a level whose group was opened somewhere else entirely --
    a shape in which an element is easy to open at the wrong moment or to
    leave unclosed.  Neither shows on the page, and neither oracle sees
    both: marked content straddling its parent fails veraPDF while passing
    every geometric assertion here, and an element never closed is
    spec-valid, so veraPDF passes it while the rest of the document becomes
    its child.  That one is caught only by the depths.
    """
    r = []
    if not shutil.which("verapdf"):
        r.append((False, "verapdf is not on PATH: the PDF/UA gate for the "
                         "langsci front-end cannot run"))
    else:
        verdicts, failures, raw = verapdf_report(p.path)
        if not verdicts:
            r.append((False, f"veraPDF produced no verdict (broken install?); "
                             f"its output was {raw[:300]!r}"))
        else:
            failed = [name for name, ok in verdicts if not ok]
            r.append(check(not failed,
                           f"veraPDF: the \\ea front-end produces valid "
                           f"PDF/UA; failed {failed} with {failures}"
                           if failed else
                           "veraPDF: the \\ea front-end produces valid PDF/UA"))
            logged = verapdf_log_records(raw)
            r.append(check(not logged,
                           f"veraPDF parsed it without complaint; it logged "
                           f"{len(logged)} record(s): {logged[:3]}"
                           if logged else
                           "veraPDF parsed it without complaint"))
    depths = struct_label_depths(p.path)
    levels = {d for _, d in depths}
    r.append(check(len(depths) >= 5 and len(levels) == 1,
                   f"every top-level example number sits at one depth; "
                   f"got {depths}"))
    # The numbering variants announce what they print.  langsci-lists.tex
    # asserts the printed half; this is the other half, and it is the half
    # no rendering shows -- a list labelled "A." whose class says LowerRoman
    # is well-formed PDF and passes veraPDF.
    classes = struct_ol_classes(p.path)
    for cls, printed in [("lxOLupperalpha", "A."), ("lxOLupperroman", "I."),
                         ("lxOLdecimal", "(1)"), ("lxOLalpha", "a."),
                         ("lxOLroman", "i.")]:
        r.append(check(classes.get(cls, 0) >= 1,
                       f"a list printing {printed} carries /ListNumbering "
                       f"{cls}; the tree has {dict(classes)}"))
    # \exp and \atcenter are written in text mode on purpose -- upstream has
    # both in math.  A Formula element in a PDF/UA-2 document needs an /Alt
    # or a MathML association, and this package has neither to give: the
    # 0.12 rewrite of \altg exists because of exactly this.
    r.append(check(not struct_has_formula(p.path),
                   "no Formula element in the tree: \\exp's prime and "
                   "\\atcenter are text, not math"))
    # a compliant but empty PDF must not pass this case by accident
    for tok in ("UALSMAIN", "UALSALPHA", "UALSROMAN", "UALSLISTA",
                "UALSOBJ", "UALSTRANS", "UALSDOT", "UALSREL"):
        r.append(check(p.find(tok) is not None, f"typeset: {tok}"))
    return r


def a_frontend(p: Page):
    r"""The public API is SUFFICIENT: a syntax front-end built out of
    \lx_... names alone produces the same geometry and the same structure
    tree as the package's own syntaxes.

    The case compiling at all is the first half of the assertion -- it uses
    no internal, so a name that stops being public breaks it outright.  The
    second half is that the API's promises hold, which is what everything
    below measures.  Both front-end shapes are covered: \pex brings its own
    list, the pexe environment holds several examples in one.
    """
    r = []
    # --- numbering: one counter across both shapes ----------------------
    labw = [w for w in p.words if re.fullmatch(r"\(\w+\)", w.text)]
    margin = min(w.x0 for w in labw)
    got = [w.text for w in labw if abs(w.x0 - margin) < TOL]
    r.append(check(
        got == ["(1)", "(2)", "(3)", "(4)", "(fex)",
                "(5)", "(6)", "(7)", "(8)", "(9)"],
        f"self-contained and batch examples share one counter, and the "
        f"custom label does not step it; got {got}"))
    # --- judgments hang, whatever supplied them -------------------------
    plain = p.find("FEPLAIN")
    for tok, how in [("FEJUDGED", "scanned from the input"),
                     ("FEARGJUDGE", "set with \\lx_judgment_set:n"),
                     ("FEBATCHJ", "set with \\lx_item_judged:n")]:
        w = p.find(tok)
        r.append(check(abs(w.x0 - plain.x0) < TOL,
                       f"judgment {how} does not displace the text "
                       f"({w.x0:.2f} vs {plain.x0:.2f})"))
    label = re.compile(r"^(\(\w+\)|[a-f]\.|[ivx]+\.)$")
    for tok in ("FEJUDGED", "FEARGJUDGE", "FEBATCHJ"):
        w = p.find(tok)
        marks = [t for t in p.line_of(w)
                 if not label.match(t.text) and t is not w and t.x1 <= w.x0 + TOL]
        r.append(check(marks, f"{tok}: the mark hangs left of the text block"))
    # --- sub-levels: \lx_sub_push: deepens, \lx_sub_next: does not ------
    host, suba, subb = p.find("FESUBHOST"), p.find("FESUBA"), p.find("FESUBB")
    roman = p.find("FEROMANA")
    r.append(check(suba.x0 > host.x0 + 2,
                   f"\\lx_sub_push: opens a deeper level "
                   f"({suba.x0:.2f} vs {host.x0:.2f})"))
    r.append(check(abs(subb.x0 - suba.x0) < TOL,
                   f"\\lx_sub_next: stays at its level "
                   f"({subb.x0:.2f} vs {suba.x0:.2f})"))
    r.append(check(roman.x0 > suba.x0 + 2,
                   f"a second \\lx_sub_push: opens the roman level "
                   f"({roman.x0:.2f} vs {suba.x0:.2f})"))
    # The letters of the SECOND sub-level example must restart at a.  One
    # such example cannot show this; two can.  Note that the package resets
    # SubExNo in BOTH \lx@example@begin and the sub-list opener, so removing
    # either alone changes nothing and only removing both makes this fail --
    # the redundancy is real, and this assertion is what would catch its
    # last remaining half going away.
    letters = [w.text for w in p.words if w.text in ("a.", "b.", "c.", "d.", "i.")]
    r.append(check(letters == ["a.", "b.", "i.", "a.", "b."],
                   f"sub-levels are lettered then romanised, and restart at a. "
                   f"in the next example; got {letters}"))
    # --- the batch shares one list --------------------------------------
    one, two = p.find("FEBATCHONE"), p.find("FEBATCHTWO")
    r.append(check(abs(one.x0 - two.x0) < TOL and abs(one.x0 - plain.x0) < TOL,
                   f"batch items sit at the ordinary example text margin "
                   f"({one.x0:.2f}, {two.x0:.2f} vs {plain.x0:.2f})"))
    # --- \lx_example_end: cancelled the paragraph continuation ----------
    # The paragraph after an example must be a NEW, indented one.  This is
    # the half of the lifecycle that is invisible in the numbers: if
    # \lx_example_end: did not cancel @endpe, FEPARA would start flush at
    # the margin instead of indented.
    para, mgn = p.find("FEPARA"), p.find("FEMARGIN")
    r.append(check(para.x0 > mgn.x0 + 2,
                   f"the paragraph after an example is indented "
                   f"({para.x0:.2f} vs margin {mgn.x0:.2f})"))
    # --- structure tree --------------------------------------------------
    els = struct_elems(getattr(p, "raw", b""))
    tags = [s for s, c in els]
    nlist = tags.count("list") + tags.count("L")
    r.append(check(nlist >= 2,
                   f"the front-end's lists reach the structure tree "
                   f"(>=2 list elements, got {nlist})"))
    # ...carrying a VALID /ListNumbering class per level.  A front-end gets
    # these from the list funnel without asking, which is the whole reason
    # the funnel is the API rather than \begin{list}.  "Ordered" is the
    # value that must never appear: it is not in PDF's enumeration and is
    # what routing through the block code's enumerate class would produce.
    classes = [c for s, c in els if s in ("list", "L")]
    r.append(check(classes.count("lxOLdecimal") >= 2,
                   f"main-level lists carry /ListNumbering /Decimal; "
                   f"got {classes}"))
    r.append(check(classes.count("lxOLalpha") >= 2 and "lxOLroman" in classes,
                   f"sub-levels carry /LowerAlpha and /LowerRoman; "
                   f"got {classes}"))
    r.append(check("Ordered" not in classes,
                   f"no list carries the invalid /Ordered; got {classes}"))
    # --- and the whole thing is valid PDF/UA ----------------------------
    # The structure checks above and veraPDF are complementary: an element
    # opened at the wrong moment passes every check in this function and
    # fails veraPDF, and an element never closed does the reverse.
    if not shutil.which("verapdf"):
        r.append((False, "verapdf is not on PATH: the PDF/UA gate for the "
                         "front-end API cannot run"))
    else:
        verdicts, failures, raw = verapdf_report(p.path)
        if not verdicts:
            r.append((False, f"veraPDF produced no verdict (broken install?); "
                             f"its output was {raw[:300]!r}"))
        else:
            failed = [name for name, ok in verdicts if not ok]
            r.append(check(not failed,
                           f"veraPDF: a front-end built on the public API "
                           f"produces valid PDF/UA; failed {failed} with "
                           f"{failures}" if failed else
                           "veraPDF: a front-end built on the public API "
                           "produces valid PDF/UA"))
            # ...and it must not have COMPLAINED either (see
            # verapdf_log_records for why the verdict is not sufficient).
            # It matters twice over here: the API hands the Span helpers
            # out for front-ends to use, so their misuse has to be caught
            # by something.
            logged = verapdf_log_records(raw)
            r.append(check(not logged,
                           f"veraPDF parsed the front-end's output without "
                           f"complaint; it logged {len(logged)} record(s): "
                           f"{logged[:3]}"
                           if logged else
                           "veraPDF parsed the front-end's output without "
                           "complaint"))
    # Every top-level number must sit at ONE depth: an element the API let a
    # front-end leave open would reparent the rest of the document and show
    # up here as a drop, while remaining spec-valid (see struct_label_depths).
    depths = struct_label_depths(p.path)
    levels = {d for _, d in depths}
    r.append(check(len(depths) >= 8 and len(levels) == 1,
                   f"every top-level example number sits at one depth; "
                   f"got {depths}"))
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
    # \altn's spoken /Alt expands \lpzg from the Leipzig table, the
    # behaviour \altg already had.  Before the two builders were unified,
    # \altn spoke the printed abbreviation ("PL") instead of the word.
    r.append(check(any("a plural of cats" in a for a in alts),
                   f"\\altn /Alt expands a Leipzig key (got "
                   f"{[a for a in alts if 'cats' in a]})"))
    # ... and only in the SPOKEN form: the printed stack still shows the
    # small-cap abbreviation, on the row it belongs to, and it keeps its
    # own /E.  \altn does not flatten \lpzg inside the stack the way
    # \altg does, and unifying the two /Alt builders must not change that.
    cats = p.find("cats")
    pl_row = [w for w in p.words if w.text == "pl" and abs(w.y0 - cats.y0) < 2.0]
    r.append(check(len(pl_row) == 1,
                   f"\\altn stack still prints the abbreviation on its own "
                   f"row (got {pl_row})"))
    # Two "plural" /E entries, not one: the abbreviation in the stack and
    # the label of the \lpzglist entry it produced.  Counting is what makes
    # this a real check -- \lpzglist alone accounts for the first, so
    # membership would pass even with the stack's Span flattened away.
    r.append(check(exps.count("plural") == 2,
                   f"\\lpzg inside an \\altn stack keeps its own /E "
                   f"(expected 2 'plural' entries, got {exps.count('plural')} "
                   f"in {sorted(exps)})"))
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
    # "pl" is there because \lpzg inside an \altn stack counts as used like
    # any other -- the stack prints it plain but still records it.
    lst = _band_lines(p, p.find("LPZGLIST").y1,
                      max(w.y1 for w in p.words) + 1)[:3]  # footnote follows
    labels = [l[0].text for l in lst]
    r.append(check(labels == ["pl", "pst", "sg"],
                   f"abbreviation list under tagging: {labels} != "
                   f"['pl', 'pst', 'sg']"))
    if len(lst) == 3:
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
    # a relative reference with a sub part goes through the same hook, so
    # \Last[a] is "(2-a)" here and "(1b)" in a_relrefs; hard-wiring either
    # spelling into the formatter breaks one case or the other
    r.append(check(re.search(r"LEGREL \(2-a\)", txt),
                   f"\\Last[a] prints (2-a) under [legacy]; got "
                   f"{txt[txt.find('LEGREL'):][:16]!r}"))
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


def a_legacy_gb4e(p: Page):
    r"""[legacy,gb4e]: linguex's geometry reached through gb4e's syntax.

    The two option groups are orthogonal and each is covered on its own
    (a_legacy, a_gbfour), but the combination is not the conjunction of the
    two cases: exe/xlist open the sub-levels through their own code path,
    which then picks up the LEGACY geometry hooks, and the bracket judgment
    hangs into a gap legacy sizes differently (\JdgSep=0pt, and the whole
    2em sub margin is the label box).  Nothing pinned that.
    """
    r = []
    txt = " ".join(w.text for w in p.words)
    label = re.compile(r"^(\(\w+\)|[a-f]\.|[ivx]+\.)$")

    # --- linguex geometry, measured as in a_legacy: the sub-levels are
    # indented by \SubExleftmargin (2em) and \SubSubExleftmargin (2.4em),
    # here off xlist rather than off the dot syntax.
    em = 11.0
    main, sub, rom = p.find("LGONE"), p.find("LGSUBC"), p.find("LGROMAN")
    d1, d2 = sub.x0 - main.x0, rom.x0 - sub.x0
    r.append(check(abs(d1 - 2.0 * em) < TOL,
                   f"xlist text indented \\SubExleftmargin=2em ({d1:.2f}pt)"))
    r.append(check(abs(d2 - 2.4 * em) < TOL,
                   f"nested xlist text indented \\SubSubExleftmargin=2.4em "
                   f"({d2:.2f}pt)"))
    # legacy sets the sub label flush left inside that margin, with no
    # \labelsep: the letter starts exactly at the text margin of the level
    # above.  A non-zero labelsep in the legacy sub geometry would push it
    # left of that margin instead.
    lets = [w for w in p.words if w.text in ("a.", "b.", "c.")]
    r.append(check(len(lets) == 3 and all(abs(w.x0 - main.x0) < TOL for w in lets),
                   f"xlist letters sit flush at the main text margin "
                   f"({[round(w.x0, 2) for w in lets]} vs {main.x0:.2f})"))
    # the roman label is looked up defensively: under a mutation that drops
    # legacy's \SubSubEx*Br the token is "i." and does not exist at all, and
    # that must be a failing assertion, not a setup crash.
    romlab = [w for w in p.words if w.text == "(i)"]
    r.append(check(romlab and abs(romlab[0].x0 - sub.x0) < TOL,
                   f"the roman label sits flush at the letter text margin "
                   f"({romlab[0].x0:.2f} vs {sub.x0:.2f})" if romlab else
                   "the roman label (i) is not in the output at all"))

    # --- linguex conventions on gb4e input: letters a.-c., and a roman
    # sub-sub-example printed "(i)" (\SubSubEx*Br), not "i."
    letters = [w.text for w in p.words if re.fullmatch(r"[a-f]\.|[ivx]+\.", w.text)]
    r.append(check(letters == ["a.", "b.", "c."],
                   f"xlist letters run a.,b.,c. with no roman 'i.'; got {letters}"))
    r.append(check(romlab and "i." not in letters,
                   f"the nested xlist prints (i), linguex-style; got {letters}"))

    # --- the bracket judgment hangs: it must not displace the text, and it
    # must actually protrude left of the text block.  Measured on the word
    # AFTER a shared leading word, because legacy's \JdgSep=0pt guarantees
    # pdftotext merges the mark with the word it precedes.
    for judged, plain, where in (("LGJMAIN", "LGPMAIN", "exe main level"),
                                 ("LGJSUB", "LGPSUB", "xlist letter level")):
        wj, wp = p.find(judged), p.find(plain)
        r.append(check(abs(wj.x0 - wp.x0) < TOL,
                       f"{where}: [judgment] does not displace text "
                       f"({wj.x0:.2f} vs {wp.x0:.2f})"))
        lj = min(t.x0 for t in p.line_of(wj) if not label.match(t.text))
        lp = min(t.x0 for t in p.line_of(wp) if not label.match(t.text))
        r.append(check(lj < lp - 0.5,
                       f"{where}: the mark hangs left of the text block "
                       f"({lj:.2f} vs {lp:.2f})"))
    # legacy's sub label box is the full 2em margin, so TWO marks still
    # clear the letter: "b." survives as its own token (pdftotext merges
    # tokens closer than ~2pt) with the marks to its right.
    bl = [w for w in p.words if w.text == "b."]
    marks = [w for w in p.line_of(p.find("LGJSUB")) if w.text.startswith("??")]
    r.append(check(len(bl) == 1 and marks and marks[0].x0 > bl[0].x1,
                   f"two marks clear the letter in the legacy sub label box "
                   f"(letter ends {bl[0].x1:.2f}, marks at "
                   f"{marks[0].x0:.2f})" if bl and marks else
                   "two marks overlap the letter: label and marks merged"))

    # --- numbering and cross-referencing across the batch
    labw = [w for w in p.words if re.fullmatch(r"\(\d+\)", w.text)]
    margin = min(w.x0 for w in labw)
    got = [w.text for w in labw if abs(w.x0 - margin) < TOL]
    r.append(check(got == ["(1)", "(2)", "(3)", "(4)"],
                   f"the exe batch numbers each \\ex, xlist items excluded; "
                   f"got {got}"))
    r.append(check("LGREFS (1) and (4)." in txt,
                   f"\\label and \\Last resolve across the batch; got "
                   f"{txt[txt.find('LGREFS'):][:24]!r}"))
    return r



# --- Rendered ink (for what has no text layer at all) ----------------------

def _render_gray(pdf: Path, dpi: int):
    """The first page as (pixels, width, height): one byte per pixel, 0 = black.

    Everything else in this file reads the TEXT layer, which is blind to
    vector ink -- and a drawn brace is nothing but vector ink.  pdftoppm is
    already a hard requirement of the suite, and its raw PGM needs no image
    library to read.
    """
    out = subprocess.run(
        ["pdftoppm", "-gray", "-r", str(dpi), "-f", "1", "-l", "1", str(pdf)],
        capture_output=True, check=True,
    ).stdout
    # P5 header: magic, width, height, maxval, one whitespace byte, then data
    fields, pos = [], 2
    while len(fields) < 3:
        while out[pos:pos + 1].isspace():
            pos += 1
        if out[pos:pos + 1] == b"#":                    # comment to end of line
            pos = out.index(b"\n", pos) + 1
            continue
        end = pos
        while not out[end:end + 1].isspace():
            end += 1
        fields.append(int(out[pos:end]))
        pos = end
    w, h, _maxval = fields
    return out[pos + 1:], w, h


def brace_bulge(pdf: Path, x0, x1, y0, y1, dpi=300):
    """Which way the brace inside the given box (PDF points) curls.

    A brace decoration is not symmetric top-to-bottom about a vertical
    line: its middle tip protrudes to one side and its two ends to the
    other.  Which side the tip takes is the whole difference between "{"
    and "}", and it is invisible to any check that only measures where the
    ink IS -- the mirrored-brace bug of v0.13 sat at the right coordinates.

    Returns tip_x - ends_x in pixels: NEGATIVE for an opening "{" (tip to
    the left), POSITIVE for a closing "}".  Raises if the box holds no ink,
    which means the caller's coordinates missed the brace.
    """
    px, w, h = _render_gray(pdf, dpi)
    s = dpi / 72.0
    cx0, cx1 = max(0, int(x0 * s)), min(w, int(x1 * s) + 1)
    cy0, cy1 = max(0, int(y0 * s)), min(h, int(y1 * s) + 1)

    def centroid(y):
        base = y * w
        # a generous threshold on purpose: the brace is a hairline, thinner
        # than a pixel at any sane resolution, so most of it survives only
        # as anti-aliasing and a strict cut-off would drop the curve
        dark = [x for x in range(cx0, cx1) if px[base + x] < 224]
        return sum(dark) / len(dark) if dark else None

    rows = {y: c for y in range(cy0, cy1) if (c := centroid(y)) is not None}
    if not rows:
        raise AssertionError(
            f"no ink in the brace box ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
    # A brace is TALLER than the text it braces -- the callers' band comes
    # from the row glyphs -- and its ENDS are exactly the part that sticks
    # out.  Cutting them off leaves the tip measured against the middle of
    # the curve rather than against the ends, which shrinks the very
    # difference this is looking for.  So follow the ink out of the band,
    # which stops by itself in the blank space above and below.
    for step, limit in ((-1, 0), (1, h - 1)):
        y = (min(rows) if step < 0 else max(rows)) + step
        while y != limit and (c := centroid(y)) is not None:
            rows[y] = c
            y += step
    ys = sorted(rows)
    if len(ys) < 8:
        raise AssertionError(f"only {len(ys)} inked rows: no brace here")
    # Measured against the ENDS rather than against the shaft, and by the
    # extreme rather than by an average over a band: a brace spends most of
    # its height on the shaft, so any mean is dominated by it and the
    # curl -- the whole signal -- is averaged away to a couple of pixels.
    ends = (rows[ys[0]] + rows[ys[1]] + rows[ys[-2]] + rows[ys[-1]]) / 4
    return max((rows[y] for y in ys), key=lambda c: abs(c - ends)) - ends


def glyph_ink(pdf: Path, w, dpi=600):
    r"""(ink height in pt, ink area in pt^2) of the glyphs inside word `w`.

    A word box is line-height and says nothing about the letters in it, so
    neither the SIZE nor the WEIGHT of a glyph shows up in the text layer:
    a bold lowercase "m" and a small-cap "M" occupy the same box and
    extract as the same word.  Both are exactly what \lpzg's modified
    labels are about, and both are plain in the rendered ink -- the height
    tells small caps from lowercase, the area tells bold from medium.

    Measured against a hard threshold rather than brace_bulge's generous
    one: a glyph is solid ink, not a hairline, and counting anti-aliasing
    would make the area depend on the resolution.
    """
    px, width, height = _render_gray(pdf, dpi)
    s = dpi / 72.0
    x0, x1 = max(0, int(w.x0 * s)), min(width, int(w.x1 * s) + 1)
    y0, y1 = max(0, int(w.y0 * s)), min(height, int(w.y1 * s) + 1)
    rows, dark = [], 0
    for y in range(y0, y1):
        base = y * width
        n = sum(1 for x in range(x0, x1) if px[base + x] < 128)
        if n:
            rows.append(y)
            dark += n
    if not rows:
        raise AssertionError(f"no ink in the box of {w!r}")
    return (max(rows) - min(rows) + 1) / s, dark / (s * s)


def stroke_width(pdf: Path, x0, x1, y0, y1, dpi=1200):
    """The typical horizontal ink run in a box, in points.

    For a brace's shaft -- which is near vertical over the stretch this is
    handed -- that run IS the stroke width, and a stroke width is the one
    thing a brace has that neither its position nor its curl records.  The
    median row is taken rather than the mean: the band may catch a row or
    two of the corner, where the curve turns and the horizontal run is
    longer than the pen.

    At 1200dpi one pixel is 0.06pt, so a pen of 0.4pt and one of 1.2pt are
    twenty pixels apart -- far outside anything anti-aliasing moves.
    """
    px, width, height = _render_gray(pdf, dpi)
    s = dpi / 72.0
    cx0, cx1 = max(0, int(x0 * s)), min(width, int(x1 * s) + 1)
    runs = []
    for y in range(max(0, int(y0 * s)), min(height, int(y1 * s) + 1)):
        base = y * width
        dark = [x for x in range(cx0, cx1) if px[base + x] < 160]
        if dark:
            runs.append((dark[-1] - dark[0] + 1) / s)
    if not runs:
        raise AssertionError(
            f"no ink in ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
    runs.sort()
    return runs[len(runs) // 2]


def ink_bbox(pdf: Path, x0, y0, x1, y1, dpi=600, threshold=200):
    """(left, top, right, bottom) in PDF points of the ink inside a box.

    Where glyph_ink asks how big and how heavy a glyph is, this asks where
    it is -- and asks it of ink rather than of a text-layer box, so that a
    drawn brace and a period can be compared with each other at all.  The
    threshold sits between brace_bulge's generous 224 (a hairline survives
    mostly as anti-aliasing) and glyph_ink's strict 128: both things
    measured here have a solid core, and the edge pixels either way move
    the answer by less than the tolerances that read it.
    """
    px, width, height = _render_gray(pdf, dpi)
    s = dpi / 72.0
    cx0, cx1 = max(0, int(x0 * s)), min(width, int(x1 * s) + 1)
    cy0, cy1 = max(0, int(y0 * s)), min(height, int(y1 * s) + 1)
    xs, ys = [], []
    for y in range(cy0, cy1):
        base = y * width
        row = [x for x in range(cx0, cx1) if px[base + x] < threshold]
        if row:
            ys.append(y)
            xs += (row[0], row[-1])
    if not ys:
        raise AssertionError(
            f"no ink in ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
    return min(xs) / s, min(ys) / s, max(xs) / s, max(ys) / s


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


def verapdf_report(pdf: Path):
    """(verdicts, failures, raw) from one veraPDF run.

    veraPDF is the only authoritative oracle for PDF/UA: a structure tree can
    be well-formed to every check in this file and still be invalid, and the
    reverse -- spec-valid but semantically wrong -- also happens (see
    struct_label_depths).  The two are complementary, not redundant.

    `verdicts` is [(profile name, compliant?)] and is EMPTY when veraPDF could
    not report at all.  That case needs the raw output to be diagnosable: the
    launcher is a shell script that exits 0 even when it cannot start the JVM
    ("Error: JAVA_HOME is not defined correctly"), so a broken install is not
    an error status but a silent empty report.
    """
    proc = subprocess.run(["verapdf", str(pdf)], capture_output=True, text=True)
    raw = (proc.stdout + proc.stderr).strip()
    verdicts = [(m.group(1), m.group(2) == "true") for m in re.finditer(
        r'profileName="([^"]*)"[^>]*isCompliant="(true|false)"', raw)]
    failures = []
    for m in re.finditer(
            r'clause="([^"]*)"[^>]*status="failed".*?<errorMessage>([^<]*)',
            raw, re.S):
        item = (m.group(1), m.group(2))
        if item not in failures:
            failures.append(item)
    return verdicts, failures, raw


def verapdf_log_records(raw: str):
    """Everything veraPDF LOGGED during one run, as opposed to reported.

    The compliance verdict is not sufficient on its own.  Unwinding the
    tagged-Span idiom in the wrong order -- \\tag_struct_end: before the
    \\tag_mc_end: that belongs to it -- opens one marked-content sequence
    inside another, and veraPDF 1.30 logs that ("Nested MCID - 8") while
    still returning isCompliant="true" on all three profiles.  A malformed
    content stream that every profile accepts is exactly the kind of defect
    this suite exists to see, so the log is read as well as the verdict.

    Why any record rather than that one message: veraPDF is SILENT on a
    clean run -- measured, not assumed, at zero records for the ua and
    frontend cases under all three engines -- so "it said something" is a
    usable signal in itself, and one that survives the message being
    reworded.  It also catches the neighbours of the defect above (an
    unmatched EMC, a bad operator), which a fixed substring would not.

    Matching is on the logger's class name, which java.util.logging prints
    on the first line of every record.  The message line is localised (this
    machine says WARNUNG) and its text is prose; the class name is neither.

    A benign future warning would fail this.  That is the intended cost:
    the answer is to look at what veraPDF started saying and narrow this
    deliberately, not to drop the check.

    Returned as the MESSAGE of each record, which is its second line: the
    class name is what makes the record findable, but "Nested MCID - 8" is
    what makes it diagnosable, and a failure report full of the former
    would say only that something happened.
    """
    lines = raw.splitlines()
    out = []
    for i, l in enumerate(lines):
        if "org.verapdf." in l:
            msg = lines[i + 1].strip() if i + 1 < len(lines) else ""
            out.append(msg or l.strip())
    return out


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
    # errors="replace": a PDF/UA build carries UTF-16 strings, and pdfinfo
    # passes their bytes through, so a strict decode raises here rather than
    # reporting on the tree.  The pattern below only ever matches ASCII.
    out = subprocess.run(["pdfinfo", "-struct-text", str(pdf)],
                         capture_output=True, text=True,
                         errors="replace").stdout
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

    "fem" with an accent is the key that is not ASCII.  A key is stored
    and compared as a string, and under pdflatex a string is BYTES: the
    entry used to be typeset one byte at a time, so the list printed a key
    the document does not contain (and, being consistent about it,
    reserved a label column that wide as well).  It is declared as the
    character and exempted from the CUSTOMLIST as an accent command, so
    the two spellings have to reach the same key for that list to come out
    with one entry.
    """
    r = []
    lines = _band_lines(p, p.find("FRONTLIST").y1, p.find("(1)").y0)
    labels = [l[0].text for l in lines]
    expected = ["3", "acc", "def", "f\u00e9m", "nom", "obv", "pl", "prs",
                "pst", "sg", "voc"]
    r.append(check(labels == expected,
                   f"front list is complete and alphabetical: {labels} != {expected}"))
    texts = {l[0].text: " ".join(w.text for w in l[1:]) for l in lines}
    for key, meaning in (("3", "third person"), ("acc", "accusative"),
                         ("obv", "obviative"), ("voc", "vocative"),
                         ("f\u00e9m", "f\u00e9minin")):
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
            "acc accusative; obv obviative; f\u00e9m f\u00e9minin; "
            "voc vocative")
    r.append(check(got == want, f"inline list, order of first use: {got!r} != {want!r}"))
    # a custom entry format replaces the default one entirely
    tail = _band_lines(p, custom.y1, max(w.y1 for w in p.words) + 1)
    r.append(check(bool(tail) and " ".join(w.text for w in tail[0]) == "sg = singular",
                   f"format= drives the entry: {tail[0] if tail else None}"))
    return r


def a_lpzg_mod(p: Page):
    r"""A modifier inside \lpzg adds to the small caps; \altg keeps its dot.

    Both halves are invisible to the text layer.  The first is measured
    from the ink of two labels set side by side, \lpzg{m} and
    \lpzg{\textbf{m}}: the modified one must be exactly as TALL (the small
    caps survived the modifier) and carry distinctly more ink (the
    modifier survived the small caps).  Latin Modern has no bold small
    caps in any encoding, so before the per-leaf decision was made xelatex
    and lualatex dropped the shape and set a bold lowercase "m" -- same
    word, same box, 14% shorter.  pdflatex's cmr has the shape and takes
    the unchanged \textsc path, which is the same assertion from the other
    side and the reason it is not engine-specific.

    The second is a coordinate: a period glued to the object call of an
    \altg used to be set where it stands, immediately after the object
    stack -- inside the braces, in the gutter between the object column
    and the gloss column.  It belongs to the paradigm as a whole, so it is
    set after the closing brace and on the object line.
    """
    r = []
    line = p.line_of(p.find("MODPLAIN"))
    texts = [w.text for w in line]
    plain = line[texts.index("MODPLAIN") + 1]
    bold = line[texts.index("MODBOLD") + 1]
    hp, ap = glyph_ink(p.path, plain)
    hb, ab = glyph_ink(p.path, bold)
    r.append(check(abs(hb - hp) < 0.35,
                   f"the modified label keeps the small caps: it is "
                   f"{hb:.2f}pt tall, the plain one {hp:.2f}pt"))
    r.append(check(ab > 1.2 * ap,
                   f"and gains the boldface: {ab:.2f} against {ap:.2f} "
                   f"square points of ink"))
    # ... and the unmodified label is untouched by any of this: a real
    # small-caps font keeps the letters it was given, so the text layer
    # still hands out "m".  This is what pins the decision to the fonts
    # that need it -- caps made where a real shape exists would look the
    # same on the page and extract as "M".
    r.append(check(plain.text == "m",
                   f"the plain label is set in the font's own small caps "
                   f"and extracts as written; got {plain.text!r}"))
    # the label is parsed through its markup, not as markup: \textbf{m}
    # used to reach the Leipzig table verbatim, and be reported as a key
    # with no expansion (and listed under that name by \lpzglist).
    r.append(check("No expansion known for" not in p.log,
                   "the markup is off the label before the table sees it: "
                   + warning_body(p.log, "Package linguexx Warning: No "
                                         "expansion known for")))
    # the period of the second example
    dot = p.find(".")
    gloss = p.find("dotaltb")
    top = min(p.find("DOTALTA").y0, p.find("DOTALTB").y0) - 6
    bottom = max(p.find("DOTALTA").y1, p.find("DOTALTB").y1) + 6
    r.append(check(dot.x0 > gloss.x1,
                   f"the period is set past the paradigm, not inside it "
                   f"({dot.x0:.1f} against a gloss column ending at "
                   f"{gloss.x1:.1f})"))
    # Level with the middle of the CLOSING BRACE, which is the one thing in
    # the neighbourhood that belongs to both tiers -- so the two are
    # compared to each other, ink to ink: the brace has no text layer at
    # all, and the period's box is line-height and says nothing about where
    # the dot inside it sits.  On the object line, which is where this
    # started, the two centres are a good half line apart.
    brace = ink_bbox(p.path, gloss.x1 + 0.5, top, dot.x0, bottom)
    ink = ink_bbox(p.path, dot.x0, top, dot.x1 + 0.5, bottom)
    mid_brace = (brace[1] + brace[3]) / 2
    mid_dot = (ink[1] + ink[3]) / 2
    r.append(check(abs(mid_dot - mid_brace) < 0.35,
                   f"the period is level with the middle of the closing "
                   f"brace ({mid_dot:.2f} vs {mid_brace:.2f})"))
    # ... and clear of its tip.  The tip is what points at the punctuation
    # and it reaches the edge of the brace's own box, so a period set flush
    # against it reads as a blob on the end of the brace.
    r.append(check(ink[0] - brace[2] > 0.8,
                   f"and clear of the brace's tip "
                   f"({ink[0] - brace[2]:.2f}pt of daylight)"))
    return r


#: Case files that are deliberately NOT assertion-driven: the two smoke
#: tests the Makefile builds under all three engines, whose only assertion
#: is that they compile.  Listed here so that the integrity check below can
#: tell them apart from a case file whose assertions were forgotten.
SMOKE_ONLY = {"linguexx-test", "linguexx-test-gb4e"}

ASSERTIONS = {
    "customise": a_customise,
    "cleveref": a_cleveref,
    "cleveref-named": a_cleveref_named,
    "hypanchors": a_hypanchors,
    "cedilla": a_cedilla,
    "cedilla-gb4e": a_cedilla_gb4e,
    "cedilla-internal": a_cedilla_internal,
    "legacy": a_legacy,
    "legacy-gb4e": a_legacy_gb4e,
    "tagged": a_tagged,
    "frontend": a_frontend,
    "ua": a_ua,
    "utf8": a_utf8,
    "utf8-unicode": a_utf8_unicode,
    "gbfour": a_gbfour,
    "langsci": a_langsci,
    "langsci-mixed": a_langsci_mixed,
    "langsci-ua": a_langsci_ua,
    "langsci-lists": a_langsci_lists,
    "langsci-names": a_langsci_names,
    "langsci-refs": a_langsci_refs,
    "langsci-hole": a_langsci_hole,
    "langsci-extra": a_langsci_extra,
    "langsci-ellipsis": a_langsci_ellipsis,
    "langsci-exewidth": a_langsci_exewidth,
    "langsci-options": a_langsci_options,
    "numbering": a_numbering,
    "judgment-align": a_judgment_align,
    "judgments": a_judgments,
    "exsource": a_exsource,
    "zpop": a_zpop,
    "gloss": a_gloss,
    "glt": a_glt,
    "lpzgcheck": a_lpzgcheck,
    "lpzg-mod": a_lpzg_mod,
    "lpzglist": a_lpzglist,
    "lpzgsetup": a_lpzgsetup,
    "phantomalign": a_phantomalign,
    "phantommarks": a_phantommarks,
    "altg": a_altg,
    "altn": a_altn,
    "altn-phantomalign": a_altn_phantomalign,
    "altg-phantomalign": a_altg_phantomalign,
    "alttuck": a_alttuck,
    "babel-de": a_babel_de,
    "babel-fr": a_babel_fr,
    "babel-fr-order": a_babel_fr_order,
    "termination": a_termination,
    "verb": a_verb,
    "refs": a_refs,
    "relrefs": a_relrefs,
    "relreflinks": a_relreflinks,
    "relreflinks-off": a_relreflinks_off,
    "relreflinks-reset": a_relreflinks_reset,
    "relreflinks-beamer": a_relreflinks_beamer,
    "relreflinks-beamer-reset": a_relreflinks_beamer_reset,
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
    letters reached a release.  Report both directions, and a KNOWN_XFAIL
    key that names no such engine or case, as hard errors.

    The OTHER way a KNOWN_XFAIL key goes stale -- naming a real case that
    now passes -- cannot be checked here, because nothing has run yet.
    main() checks it after the run.
    """
    problems = []
    on_disk = discover_cases()
    known = set(ASSERTIONS) | set(EXPECT_ERROR)
    for name in sorted(set(ASSERTIONS) & set(EXPECT_ERROR)):
        problems.append(
            f"{name} is in both ASSERTIONS and EXPECT_ERROR; a case either "
            f"compiles and is asserted on, or fails with a known error.")
    for name in sorted(on_disk - known - SMOKE_ONLY):
        problems.append(
            f"{name}.tex has no ASSERTIONS entry, so it is never run. "
            f"Add an assertion function, or list it in SMOKE_ONLY if it is "
            f"only meant to compile."
        )
    for name in sorted(known - on_disk):
        problems.append(f"'{name}' is registered but has no {name}.tex in {CASES}.")
    for name in sorted(set(PASSES) - known):
        problems.append(f"PASSES['{name}'] names no known case.")
    for name in sorted(set(ENGINES_FOR) - known):
        problems.append(f"ENGINES_FOR['{name}'] names no known case.")
    for name, engs in sorted(ENGINES_FOR.items()):
        for e in engs:
            if e not in ENGINES:
                problems.append(
                    f"ENGINES_FOR['{name}'] names no known engine: {e!r}.")
    for key in sorted(KNOWN_XFAIL):
        engine, _, name = key.partition("/")
        if engine not in ENGINES:
            problems.append(f"KNOWN_XFAIL key {key!r} names no known engine.")
        elif name not in known:
            problems.append(f"KNOWN_XFAIL key {key!r} names no known case.")
    problems.extend(tooling_integrity())
    return problems


def tooling_integrity():
    """Cross-check REQUIRED_TOOLS against PATH, the docstring and the workflow.

    Three places have to agree about what the suite needs, and they had
    already drifted once: qpdf reached the docstring and not the workflow,
    so every local run passed and CI failed on a FileNotFoundError two
    minutes in.  The list in REQUIRED_TOOLS is now the only statement of the
    requirement, and this checks that the other two match it.

    The docstring half is not pedantry.  It is what a person reads before
    running the suite, and it is the only one of the three a reader of the
    file can see.
    """
    problems = []
    for tool, (provided, at_startup, why) in REQUIRED_TOOLS.items():
        if at_startup and not shutil.which(tool):
            problems.append(
                f"{tool} is not on PATH; the suite needs it for {why}.")
        if tool not in (__doc__ or ""):
            problems.append(
                f"{tool} is in REQUIRED_TOOLS but this module's docstring "
                f"does not name it, so nobody reading the file learns they "
                f"need it.")
    if not WORKFLOW.exists():
        return problems
    workflow = WORKFLOW.read_text(errors="replace")
    # What is searched is the apt-get command's own argument list, and not
    # the file.  Searching the file passes a workflow that installs nothing:
    # this one both installs qpdf and SAYS why, in a comment and in a step
    # name, so a whole-file test finds the word three times over and two of
    # them are prose.  Verified the only way worth trusting -- by deleting
    # qpdf from the apt line and watching the first two versions of this
    # check stay green.
    joined = re.sub(r"\\\n\s*", " ", workflow)   # undo the line continuations
    apt = set()
    for m in re.finditer(r"apt-get\s+install[^\n]*", joined):
        apt.update(m.group(0).split())
    for tool, (provided, at_startup, why) in REQUIRED_TOOLS.items():
        kind, _, value = provided.partition(":")
        if kind == "image":
            continue                    # the container brings it
        if kind == "apt":
            ok = value in apt
            what = f"install the package {value!r}"
        else:
            ok = f"- name: {value}" in workflow
            what = f"run a step named {value!r}"
        if not ok:
            problems.append(
                f"{tool} is required ({why}) but {WORKFLOW.name} does not "
                f"{what}; CI would then fail on a machine that happens not "
                f"to have it, long after the compile that hides why.")
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
        first_log = ""
        for npass in range(PASSES.get(name, DEFAULT_PASSES)):
            try:
                proc = subprocess.run(
                    [engine, "-interaction=nonstopmode", "-halt-on-error",
                     src.name],
                    cwd=tmp, capture_output=True, text=True,
                    timeout=CASE_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                # A TeX loop does not stop for -interaction=nonstopmode: it
                # spins with nothing in the log, and without this the whole
                # suite hangs instead of reporting.  This is a real failure
                # mode, not a hypothetical -- an unguarded \DeclareJudgment
                # argument redefines \% and loops forever.
                return [(False, f"TIMED OUT after {CASE_TIMEOUT}s: the engine "
                                f"did not stop (a TeX loop ignores "
                                f"nonstopmode)")]
            # The COLD run's log, kept because some of what the package
            # reports can only be said on it.  A mechanism that hands the
            # anchors of one run to the next has nothing to go on when the
            # .aux is empty, and what it must do there -- ask for a rerun,
            # rather than report every reference as unresolved -- is invisible
            # in the converged log the assertions otherwise see.
            if npass == 0:
                cold = tmp / f"{name}.log"
                first_log = cold.read_text(errors="replace") if cold.exists() \
                    else ""
        # Cases whose point IS the error: the compile is meant to stop, so
        # check the message before treating a non-zero status as a failure.
        if name in EXPECT_ERROR:
            want = EXPECT_ERROR[name]
            log = (tmp / f"{name}.log").read_text(errors="replace")
            if want not in log:
                errs = [l for l in log.splitlines() if l.startswith("!")][:3]
                return [(False, f"expected the error {want!r}; got "
                                f"{'; '.join(errs) or 'a clean compile'}")]
            return [(True, f"raises its error: {want!r}")]
        if proc.returncode != 0:
            log = (tmp / f"{name}.log").read_text(errors="replace")
            errs = [l for l in log.splitlines() if l.startswith("!")][:3]
            return [(False, f"COMPILE FAILED: {'; '.join(errs) or 'see log'}")]
        pdf = tmp / f"{name}.pdf"
        if not pdf.exists():
            return [(False, "COMPILE produced no PDF")]
        page = parse_pdf(pdf)
        # Warnings never reach the PDF, so a case that is about what the
        # package REPORTS needs the log as well as the rendering.
        page.log = (tmp / f"{name}.log").read_text(errors="replace")
        page.first_log = first_log
        # ... and a case about hyperref ANCHORS needs the .aux: the anchor a
        # \label stores is invisible in the rendering (the printed number is
        # right even when the anchor is wrong), and the engines disagree on
        # whether a duplicate destination is even reported -- pdflatex and
        # lualatex warn, xelatex says nothing at all, because the collision
        # is resolved by xdvipdfmx and not by the format.  The .aux is the
        # one record all three write identically.
        aux = tmp / f"{name}.aux"
        page.aux = aux.read_text(errors="replace") if aux.exists() else ""
        # ... and a case about a PDF BOOKMARK needs hyperref's .out, for the
        # same reason: a bookmark is not on the page, it is not in the text
        # layer, and in the PDF it sits inside a compressed object stream.
        # The .out is what hyperref writes it from, in one line per heading.
        out = tmp / f"{name}.out"
        page.out = out.read_text(errors="replace") if out.exists() else ""
        # ... and a case about what an ENGINE reports needs to know which
        # one it is.  The three do not agree about a duplicate destination:
        # pdftex and luatex warn, xdvipdfmx says nothing, and an assertion
        # that cannot name the engine can only shrug at the difference.
        page.engine = engine
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
    names = sorted(set(ASSERTIONS) | set(EXPECT_ERROR))
    if args.filter:
        names = [n for n in names if args.filter in n]
    if not names:
        print("no cases match", file=sys.stderr)
        return 2

    total = passed = 0
    failed_cases = []
    # A KNOWN_XFAIL entry is a claim that a pair still fails.  Track which
    # pairs this run actually observed and which of them bore the claim out,
    # so an entry that has quietly started passing can be reported instead of
    # silently swallowing a green result (see the KNOWN_XFAIL comment).
    # `exercised` is what makes that safe under -k, -e, ENGINES_FOR and a
    # missing engine: without it, every entry a filtered run never reached
    # would be indistinguishable from one that no longer fires.
    exercised = set()
    fired = set()
    for engine in engines:
        if not shutil.which(engine):
            print(f"SKIP {engine}: not installed")
            continue
        print(f"\n=== {engine} ===")
        for name in names:
            if engine not in ENGINES_FOR.get(name, ENGINES):
                continue
            results = run_case(name, engine, args.verbose)
            ok = sum(1 for good, _ in results if good)
            total += len(results)
            passed += ok
            bad = [d for good, d in results if not good]
            key = f"{engine}/{name}"
            exercised.add(key)
            if bad and key in KNOWN_XFAIL:
                status = "XFAIL"
                fired.add(key)
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
    stale = sorted((KNOWN_XFAIL & exercised) - fired)
    if stale:
        print("STALE KNOWN_XFAIL: these ran and PASSED, so the entry no "
              "longer excuses anything and hides the assertion instead:",
              file=sys.stderr)
        for key in stale:
            print(f"  X {key}", file=sys.stderr)
    if failed_cases:
        # A real failure outranks a stale entry: it is the thing to look at
        # first, and the stale list is printed above either way.
        print("FAILED: " + ", ".join(failed_cases))
        return 1
    if stale:
        return 2
    print("All green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
