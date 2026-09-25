"""The PDF layer of the suite: words, boxes, and the byte-level readers.

Split out of runtests.py, which kept everything in one file; the content is
unchanged.  Nothing here knows what an assertion is -- it turns a PDF into
things a check can be written against, and that is the whole of it.
"""

import re
import shutil
import subprocess
import zlib
from pathlib import Path

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


def inflated(raw: bytes) -> bytes:
    """The PDF's bytes with every Flate stream inflated and appended.

    A tagged build puts almost everything a structure assertion wants --
    link annotations, the name tree, /Alt and /E strings -- into compressed
    object streams, where a search of the raw file finds nothing and reports
    it as an absence rather than as a failure to look.  The original bytes
    are kept in the result so a file with no compression reads the same way.

    stdlib zlib only, deliberately: reading a structure element must not
    cost the suite another external tool.
    """
    out = [raw]
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        try:
            out.append(zlib.decompress(raw[start:end]))
        except zlib.error:              # not Flate: a font, an image, XRef
            pass
    return b"\n".join(out)


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
    joined = inflated(raw).decode("latin-1")
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
