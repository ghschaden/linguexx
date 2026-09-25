"""The tag tree, and the oracles that read it.

Split out of runtests.py; the content is unchanged.  veraPDF and the
structure checks are COMPLEMENTARY (CLAUDE.md says why neither alone is
enough), and show_pdf_tags_xml is the third reader: it resolves /K the way
a consumer does, which is what catches an /Alt wrapping nothing.
"""

import re
import shutil
import subprocess
from pathlib import Path

from suite.pdf import inflated

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
    for i, ln in enumerate(lines):
        if "org.verapdf." in ln:
            msg = lines[i + 1].strip() if i + 1 < len(lines) else ""
            out.append(msg or ln.strip())
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


def struct_lbl_depths(pdf: Path):
    """struct_label_depths, narrowed to numbers that really are list labels.

    Same question, same meaning of the answer -- an element left open drops
    the depth of everything after it -- but asked of a REAL document rather
    than of a case file.  The pattern above matches any "(N)" string in the
    tree, which is exact for a case (whose prose is written not to contain
    one) and wrong for the manual or ua-demo: a relative reference typeset
    in running text is also the string "(1)", sits at whatever depth its
    paragraph does, and made ua-demo look broken when it was not.  What
    distinguishes a label is its enclosing element, so that is what is
    matched here.

    Lived in the agent harness first, where it was written for exactly this
    file; it is here because the documents phase needs it and an assertion
    belongs with the suite.
    """
    out = subprocess.run(["pdfinfo", "-struct-text", str(pdf)],
                         capture_output=True, text=True,
                         errors="replace").stdout
    stack, found = [], []
    for ln in out.splitlines():
        indent = len(ln) - len(ln.lstrip())
        body = ln.strip()
        m = re.match(r"^([A-Za-z0-9]+) <ID\.[0-9a-f]+>", body)
        if m:
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, m.group(1)))
            continue
        m = re.match(r'^"\((\d+)\)"', body)
        if m and stack and stack[-1][1] == "Lbl":
            found.append((m.group(1), stack[-1][0]))
    return found


def struct_alts(raw: bytes):
    """Decoded /Alt strings on Span elements (spoken judgment forms).

    Read from the INFLATED bytes: in a PDF/UA build the structure elements
    live in compressed object streams, and a search of the raw file returns
    an empty list there -- which reads exactly like a spoken form that never
    reached the document.
    """
    import re as _re
    raw = inflated(raw)
    alts = []
    for m in _re.finditer(rb"/Alt\s*<([0-9A-Fa-f]+)>", raw):
        alts.append(bytes.fromhex(m.group(1).decode())
                    .decode("utf-16-be", errors="replace").lstrip("\ufeff"))
    for m in _re.finditer(rb"/Alt\s*\(([^)]*)\)", raw):
        alts.append(m.group(1).decode("latin1"))
    return alts


def struct_alt_kids(pdf: Path):
    r"""(decoded /Alt, count of marked-content kids) per element carrying one.

    struct_alts() above reads the STRINGS, which is what a spoken form is.
    This reads whether the element carrying one wraps anything, which is a
    different question and had no assertion until 2026-09-17 -- when every
    \altn and \altg stack in a lualatex build turned out to carry a
    well-formed /Alt on an element with an empty /K.

    The kids are counted by their /MCID entries and NOT by looking for
    "/K [": a single kid is written as a bare dictionary rather than a
    one-element array, so a bracket test calls every judgment mark empty.
    It did, in the first version of the measurement that found this, and
    the false positives read exactly like the real ones.
    """
    out = []
    for obj in _qdf(pdf).split("endobj"):
        m = re.search(r"/Alt\s*<([0-9A-Fa-f]+)>", obj)
        if m:
            txt = (bytes.fromhex(m.group(1))
                   .decode("utf-16-be", "replace").lstrip("﻿"))
        else:
            m = re.search(r"/Alt\s*\(([^)]*)\)", obj)
            if not m:
                continue
            txt = m.group(1)
        out.append((txt, len(re.findall(r"/MCID", obj))))
    return out


def show_pdf_tags_xml(pdf: Path):
    """The structure tree as show-pdf-tags renders it, parsed.

    show-pdf-tags is the LaTeX team's own tool (TeX Live package
    ``show-pdf-tags``); Ulrike Fischer named it when this package reported
    the empty-/K defect upstream, and it was installed here the whole time
    the defect was going unnoticed.  It is here because it resolves the
    tree the way a consumer does -- following /K whether the kid is a
    marked-content dictionary, an array, or a reference to another element
    -- which the byte-level helpers in this file do not.

    That difference is not theoretical.  The ad-hoc measurement that first
    read these numbers tested for kids with a pattern beginning ``/K [``
    and so counted ``/K [ ]`` -- an EMPTY array -- as an element with a
    kid, reporting a defective ua-demo as clean.  struct_alt_kids() avoids
    that trap by counting /MCID instead, and says so in its own docstring;
    the trap was walked into anyway, by hand, on 2026-09-18.  An oracle
    maintained upstream cannot drift away from tagpdf's output in that way.
    """
    if not shutil.which("show-pdf-tags"):
        raise AssertionError(
            "show-pdf-tags is not on PATH: the structure tree cannot be read "
            "as a consumer resolves it (TeX Live package 'show-pdf-tags')")
    out = subprocess.run(["show-pdf-tags", "--xml", str(pdf)],
                         capture_output=True, text=True, errors="replace")
    if out.returncode != 0 or not out.stdout.strip():
        raise AssertionError(
            f"show-pdf-tags could not read {pdf.name}: "
            f"rc={out.returncode} stderr={out.stderr[:300]!r}")
    import xml.etree.ElementTree as ET
    return ET.fromstring(out.stdout)


def struct_empty_alts(pdf: Path):
    r"""(tag, /Alt) for every element that carries an /Alt and wraps nothing.

    The invariant is document-wide and needs no list of expected strings:
    an /Alt is an author's assertion about how SOME CONTENT is announced,
    so an element carrying one with nothing inside it is self-contradictory
    -- the alternative text has nothing to be an alternative to.  A screen
    reader announces it regardless.

    This is the complement of a_altkids, which enumerates the strings it
    expects; this one catches an element nobody thought to enumerate, which
    is how the 2026-09-17 defect reached a release.  Empty elements in
    GENERAL are not the signal: tagpdf opens a text-unit/text pair at every
    paragraph and a following list or parbox closes it again at once, so
    empty structures are frequent and valid.  Conjoining "empty" with
    "carries an author /Alt" is what makes the condition exact rather than
    a heuristic.

    What counts as content: any child ELEMENT, or any text.  A marked-content
    sequence carrying no text does not, and that distinction is not academic
    -- it is the whole difference between this oracle and struct_alt_kids.
    Pre-fix under pdflatex the ALTKLPZG element wraps three EMPTY marked
    content sequences while the two \lpzg Spans holding "sg" and "pl" sit
    outside it as siblings; counting /MCID entries calls that three kids and
    passes it, and resolving the tree shows an element that announces
    "singular or plural" over nothing.  Generic mode is therefore NOT immune
    to the 2026-09-17 defect where the box contains tagging of its own: it
    places the marked content correctly and still parents a structure
    element created during the fill to whatever was open then.

    Conservative in the other direction: an element holding a child element
    counts as wrapping something even if that child is itself empty.  The
    defect this exists for leaves nothing behind, and a rule that reports
    only what it can justify is worth more here than one that guesses.
    """
    empty = []
    for el in show_pdf_tags_xml(pdf).iter():
        alt = el.get("alt")
        if alt is None:
            continue
        kids = list(el)
        text = (el.text or "") + "".join((k.tail or "") for k in kids)
        if not kids and not text.strip():
            empty.append((el.tag.rsplit("}", 1)[-1], alt))
    return empty
