r"""Tagging, PDF/UA, annotations and the \lpzg list interface.

Split out of runtests.py; the assertion bodies are unchanged.  Each
function takes a parsed Page and returns a list of (ok, description) pairs
built with check(), which is the whole protocol.
"""

import re
import shutil
import subprocess

from suite.check import check, warning_body
from suite.geometry import (
    glyph_ink, ink_bbox,
)
from suite.pdf import (
    _band_lines,
    TOL, Page,
)
from suite.structure import (
    struct_alts, struct_elems,
    struct_empty_alts, struct_exps, struct_label_depths,
    struct_langs, verapdf_log_records,
    verapdf_report,
)

def a_exannot(p: Page):
    r"""The annotation column: ONE column, whatever the depth or the length.

    Both halves fail silently, which is why they are measured here rather
    than looked at.  A column derived from \linewidth drifts one indent step
    per nesting level, and a drifting column looks entirely deliberate on
    the page.  A column whose filler glue can SHRINK -- \jambox's can -- is
    pushed right by any example long enough to reach it, with no overfull
    warning and no error: measured on \jambox, four sub-examples of
    increasing length came out aligned to 0.01pt at a 3cm and a 7cm gutter
    and at 212.6 / 212.6 / 234.1 / 288.9pt at 11cm, which is the regime a
    column set NEAR the examples lives in.
    """
    r = []
    ann = {t: p.find(f"[{t}]") for t in ("XP", "CP", "TP", "DP", "VP", "WP")}
    col = ann["XP"].x0
    for tag, w in sorted(ann.items()):
        r.append(check(abs(w.x0 - col) < TOL,
                       f"[{tag}] is in the column ({w.x0:.2f} vs {col:.2f})"))
    # ... and the examples really are at three different depths, or the
    # assertions above would hold for a column that drifts with nothing to
    # drift over.
    top = p.find("ANNTOP").x0
    sub = p.find("ANNSUB").x0
    deep = p.find("ANNDEEP").x0
    r.append(check(sub > top + TOL and deep > sub + TOL,
                   f"the annotated examples sit at three different depths "
                   f"({top:.2f} / {sub:.2f} / {deep:.2f}), so one column "
                   f"across them is a real claim"))
    # an example that reaches the column takes the break instead of pushing
    long_ex = p.find("ANNLONG")
    r.append(check(ann["VP"] not in p.line_of(long_ex),
                   f"an example that reaches the column moves its annotation "
                   f"to the NEXT line rather than moving the column "
                   f"(annotation at y {ann['VP'].y0:.2f}, example line "
                   f"{long_ex.y0:.2f})"))
    # An annotation whose argument contains SPACES.  \gll splits the object
    # line on spaces, so one left in place until then is torn into gloss
    # COLUMNS -- and what that looks like is a line break in the gloss, not
    # a broken annotation, which is how it was reported.  Asking for the
    # whole phrase as one word is the assertion: the pieces would be
    # separate words with gloss cells under them.
    spc = [w for w in p.words if w.text == "(cf."]
    r.append(check(len(spc) == 1,
                   f"an annotation with spaces in its argument survives as "
                   f"one thing (found {len(spc)} '(cf.')"))
    if spc:
        r.append(check(abs(spc[0].x0 - col) < TOL,
                       f"... in the column ({spc[0].x0:.2f} vs {col:.2f})"))
        r.append(check(spc[0] in p.line_of(p.find("SPCOBJ")),
                       "... on the object line"))
        r.append(check(spc[0] not in p.line_of(p.find("SPCTIER")),
                       "... and not on the gloss tier"))
    # The gloss tier is where a torn annotation shows: each piece would have
    # become a column of the grid and picked up a cell under it.  The tier
    # must read exactly its own four words -- the annotation's pieces sit on
    # the object line either way (that is where the annotation belongs), so
    # the object line cannot tell the two apart and the tier can.
    tier = [w.text for w in p.line_of(p.find("SPCTIER"))]
    r.append(check(tier == ["SPCTIER", "le", "mon", "livre"],
                   f"the annotation's pieces did not become gloss columns "
                   f"with cells of their own (the gloss tier reads {tier})"))
    # ... and the gloss after it, which asked for no annotation, must not
    # inherit one.  The lift stashes the annotation in a token list; left
    # uncleared it is re-emitted by the next gloss, in the right column and
    # the right font, against an example that never asked for it.
    none_line = [w.text for w in p.line_of(p.find("SPCNONE"))]
    r.append(check(not [t for t in none_line
                        if t.startswith("(voir") or t == "mien"],
                   f"a gloss with no annotation does not inherit the "
                   f"previous one's (its object line reads {none_line})"))
    # An annotation too wide for the object line moves ITSELF down; it must
    # not make room by breaking the GRID.  The gloss is \raggedright, so
    # every break there has badness zero and the penalty decides: a free
    # breakpoint between columns beat \exannot's own \penalty50 and the
    # object line came apart between two words.  Reported from a class deck.
    #
    # Whether it triggers is a WINDOW, not a threshold, and the window is as
    # wide as the LAST gloss column -- hence the long braced one in the
    # case.  An earlier version of this check used a short last column, sat
    # outside the window, and passed with the penalty taken out.
    for obj in ("BRKB", "BRKC"):
        line = [w.text for w in p.line_of(p.find(obj))]
        for word in ("il", "mio", "libro"):
            r.append(check(word in line,
                           f"{obj}: the gloss keeps '{word}' on the object "
                           f"line rather than breaking the grid to make room "
                           f"for the annotation (line reads {line})"))
    # \exannot GLUED to the last object word, in both spellings of a glossed
    # sub-example.  find() is exact-match-first, so asking for "(italien)"
    # is itself the assertion that the annotation reached the page WHOLE:
    # when the split lost the braces off its argument, the mandatory
    # argument was the single token "(" and the page carried "(" in the
    # column with "italien)" flung to the right margin -- no error, no
    # warning, and every column assertion in this file still passing,
    # because "(" was in the column.
    glued = [w for w in p.words if w.text == "(italien)"]
    r.append(check(len(glued) == 2,
                   f"a glued annotation reaches the page whole, in both "
                   f"spellings (found {len(glued)} '(italien)', and "
                   f"{len([w for w in p.words if w.text == '('])} bare '(')"))
    for w in glued:
        r.append(check(abs(w.x0 - col) < TOL,
                       f"a glued annotation is in the column "
                       f"({w.x0:.2f} vs {col:.2f})"))
    for obj, tier in (("GLUEA", "GLUEATIER"), ("GLUEB", "GLUEBTIER")):
        o = p.find(obj)
        hits = [w for w in glued if w in p.line_of(o)]
        r.append(check(len(hits) == 1,
                       f"{obj}'s glued annotation is on its object line"))
        r.append(check(not [w for w in glued if w in p.line_of(p.find(tier))],
                       f"... and not on {tier}"))
    # A braced object item immediately before a glued annotation keeps its
    # braces' effect: {ganz kurzes} stays ONE column over {very short}.
    # Losing them at the split makes two words of it and pulls every gloss
    # after it out from under its object word.
    for a, b in (("ganz", "very"), ("GOBJ", "GGLOSS")):
        wa, wb = p.find(a), p.find(b)
        r.append(check(abs(wa.x0 - wb.x0) < TOL,
                       f"a braced object item before a glued annotation is "
                       f"still one column ({a} {wa.x0:.2f} / {b} "
                       f"{wb.x0:.2f})"))
    geb = p.find("(gebraucht)")
    gluec = p.find("GLUEC")
    r.append(check(abs(geb.x0 - col) < TOL,
                   f"and its annotation is in the column "
                   f"({geb.x0:.2f} vs {col:.2f})"))
    r.append(check(geb in p.line_of(gluec),
                   f"... on the object line (annotation y "
                   f"{geb.y0:.2f}-{geb.y1:.2f}, object {gluec.y0:.2f}-"
                   f"{gluec.y1:.2f})"))
    # \exannot ends its paragraph; a blank line ends a dot-syntax example.
    # If the \par did the second job as well, ANNUNDER would have no example
    # to attach to (the case would not compile) or would take a number of its
    # own -- so the labels are read off the page as well.
    r.append(check(abs(p.find("[HP]").x0 - col) < TOL
                   and abs(p.find("[IP]").x0 - col) < TOL,
                   "an annotated head and the sub-example under it share "
                   "the column"))
    # \ExAnnotFit is off here, and off must mean off: no positions recorded,
    # no .aux traffic, no rerun warning.  A round trip that ran for everyone
    # would show up as neither a wrong column nor an error -- only as a
    # document that has to be compiled twice for no reason anybody can see.
    # The three \providecommand lines go into every .aux whether or not the
    # fitting is asked for -- that is what leaves no ordering to get wrong
    # under \include, see the .sty -- but a RECORD is written only when it is.
    aux = getattr(p, "aux", "")
    r.append(check("\\lxannotL{" not in aux and "\\lxannotUsed{" not in aux,
                   "without \\ExAnnotFit no positions are recorded"))
    r.append(check("Annotation columns" not in p.log,
                   "... and no rerun is asked for"))
    labels = p.labels()
    r.append(check(labels[:4] == ["(1)", "(2)", "(3)", "(4)"],
                   f"\\exannot's \\par does not close its example: four "
                   f"numbered examples, not five (got {labels})"))
    # \ExAnnotSep is a LEAST gap.  ANNTIGHT ends .4em short of its own
    # column (\settowidth, so the margin is .4em on every engine), and its
    # annotation must therefore wrap rather than crowd in.  Shrink in that
    # gap would keep it on the line -- still in the column, because the
    # fixed-width box holds that regardless -- and nearer the text than
    # \ExAnnotSep allows.  This example is the only thing in the suite that
    # tells the two apart, which is why it sets a column of its own.
    tight = p.find("ANNTIGHT")
    r.append(check(p.find("[QP]") not in p.line_of(tight),
                   f"an example that ends inside \\ExAnnotSep of the column "
                   f"wraps rather than crowding the annotation "
                   f"(annotation at y {p.find('[QP]').y0:.2f}, example "
                   f"{tight.y0:.2f})"))
    # a gloss annotation is level with the OBJECT tier, not with the gloss
    obj = p.find("ANNGLOSS")
    tier2 = p.find("ANNGLOSSTIER")
    r.append(check(tier2 not in p.line_of(obj),
                   "object and gloss tiers are separate rendered lines "
                   "(without which the two checks below are one check)"))
    r.append(check(ann["WP"] in p.line_of(obj),
                   f"the gloss annotation sits on the object line "
                   f"(y {ann['WP'].y0:.2f} vs object {obj.y0:.2f})"))
    r.append(check(ann["WP"] not in p.line_of(tier2),
                   f"the gloss annotation is not on the gloss tier "
                   f"(y {ann['WP'].y0:.2f} vs gloss {tier2.y0:.2f})"))
    return r


def a_exannot_ua(p: Page):
    r"""\exannot's spoken form, and where its Span sits in the tree.

    The /Alt is the whole subject: it changes nothing on the page, so a
    spoken form that never reaches the file, or one attached to the wrong
    element, is invisible to every geometric check in this suite.  The
    printed text is asserted alongside it, because /Alt is chosen precisely
    for leaving it alone -- /ActualText would announce the phrase and take
    the brackets out of copy-and-paste with it.
    """
    r = []
    alts = struct_alts(getattr(p, "raw", b""))
    r.append(check(alts.count("complementizer phrase") == 1,
                   f"\\SetAnnotSpoken reaches the /Alt exactly once "
                   f"(got {sorted(alts)})"))
    r.append(check(alts.count("tense phrase") == 1,
                   f"\\exannot's optional argument reaches the /Alt "
                   f"(got {sorted(alts)})"))
    r.append(check(alts.count("complementizer phrase in a gloss") == 1,
                   f"a gloss annotation carries its spoken form too "
                   f"(got {sorted(alts)})"))
    # the page still says what the author wrote
    for tok in ("[CP]", "[TP]", "[ZP]", "[CPG]"):
        r.append(check(p.find(tok) is not None, f"printed as written: {tok}"))
    out = subprocess.run(["pdfinfo", "-struct-text", str(p.path)],
                         capture_output=True, text=True,
                         errors="replace").stdout
    # An annotation with no spoken form registered gets NO Span: an /Alt
    # equal to the text it replaces is noise, and a Span emitted
    # unconditionally passes veraPDF while making the tree worse.  It
    # staying inside its paragraph's own text run is what says so.
    # Matched with the spaces taken out: xdvipdfmx writes the run without
    # them ("ANNPLAINnospokenformatall[ZP]") where the other two engines
    # keep them, and the subject here is which ELEMENT the text is in, not
    # how the backend spaced it.
    runs = [t.replace(" ", "")
            for t in re.findall(r'(?m)^\s*"(.*)"\s*$', out)]
    plain = [t for t in runs if "ANNPLAIN" in t]
    r.append(check(plain and "[ZP]" in plain[0],
                   f"an annotation with no spoken form stays plain text, "
                   f"with no Span of its own (its run reads {plain[:1]})"))

    def depth(tok):
        m = re.search(r'(?m)^( *)"%s"' % re.escape(tok), out)
        return len(m.group(1)) if m else None

    r.append(check(depth("[CPG]") is not None
                   and depth("[CPG]") == depth("ANNGLOSS"),
                   f"the gloss annotation is a Span BESIDE the word bundles "
                   f"rather than inside the last one -- it labels the "
                   f"example, not the word it follows "
                   f"(depths {depth('[CPG]')} vs {depth('ANNGLOSS')})"))
    return r


def a_exannot_fit(p: Page):
    r"""\ExAnnotFit: the column measured from the examples, per example.

    Everything here fails silently.  A column in the wrong place looks like
    a column somebody chose, and the two ways of getting it wrong -- one
    column for the whole document, and a column that ignores how wide the
    annotations are -- both produce pages that a reader would not question.
    """
    r = []
    ann = {n: p.find(f"[P{n}]") for n in (1, 2, 3, 4, 5, 7, 8)}
    wide = p.find("[an")
    b1 = ann[1].x0
    b2 = ann[3].x0
    b3 = ann[5].x0
    # each block is one column ...
    r.append(check(abs(ann[2].x0 - b1) < TOL,
                   f"block 1 is one column ({ann[1].x0:.2f}, {ann[2].x0:.2f})"))
    r.append(check(abs(ann[4].x0 - b2) < TOL,
                   f"block 2 is one column ({ann[3].x0:.2f}, {ann[4].x0:.2f})"))
    r.append(check(abs(ann[7].x0 - b3) < TOL and abs(wide.x0 - b3) < TOL,
                   f"block 3 is one column, the wide annotation included "
                   f"({ann[5].x0:.2f}, {wide.x0:.2f}, {ann[7].x0:.2f})"))
    # ... and the blocks are NOT one column between them.  Block 2's
    # examples are much shorter, so its column sits well left of block 1's;
    # a document-wide fit would put both at one x.
    r.append(check(b2 < b1 - 20,
                   f"the fit is per example, not per document: a block of "
                   f"short examples gets its own column "
                   f"({b2:.2f} vs {b1:.2f})"))
    # Block 3 repeats block 1's examples and differs only in carrying one
    # annotation too wide for block 1's column.  Its column must therefore
    # be strictly left of block 1's -- which is the widest-annotation term
    # doing the work, since the examples are identical.
    r.append(check(b3 < b1 - TOL,
                   f"the widest annotation of a block moves that block's "
                   f"column: identical examples, column at {b3:.2f} rather "
                   f"than block 1's {b1:.2f}"))
    # A fitted column is one every annotation of its block FITS on: each
    # shares a rendered line with its own example, none has wrapped.  This
    # is what tells the column from any other tidy column -- fit to the
    # shortest example instead of the longest and the page still shows one
    # column per block, clear of the margin, with the long examples'
    # annotations quietly a line lower.
    for tag, sentinel in ((1, "FITLONG"), (2, "FITLONGB"),
                          (3, "FITSHORT"), (4, "FITSHORTB"),
                          (7, "FITWIDEC")):
        ex = p.find(sentinel)
        r.append(check(ann[tag] in p.line_of(ex),
                       f"[P{tag}] fits on {sentinel}'s own line "
                       f"(annotation y {ann[tag].y0:.2f}, example "
                       f"{ex.y0:.2f})"))
    r.append(check(wide in p.line_of(p.find("FITWIDEB")),
                   "the wide annotation fits on its own example's line"))
    # The one that does NOT fit, and must not: block 3's widest annotation
    # pulled the column left of where its LONGEST example ends, so that
    # example's annotation has nowhere to go but the next line.  What must
    # survive is the column, not the line -- [P5] is already asserted to be
    # in it above.  Pinned rather than left out, because the alternative a
    # future version might reach for is to let the column go back right for
    # that one example, which is the out-of-line label again.
    r.append(check(ann[5] not in p.line_of(p.find("FITWIDE")),
                   f"the example the column had to move past keeps its "
                   f"annotation in the column and loses the line "
                   f"(annotation y {ann[5].y0:.2f}, example "
                   f"{p.find('FITWIDE').y0:.2f})"))
    # ... and it stays inside the text block.  The edge comes from the prose
    # paragraph, never from the words of an annotation: an annotation that
    # overflows its box is the rightmost ink on the page, so an edge taken
    # from "the rightmost ink" is the overflow measuring itself.
    body_right = max(w.x1 for w in p.line_of(p.find("FITRULE")))
    r.append(check(wide.x1 <= body_right + TOL,
                   f"the wide annotation stays within the text block "
                   f"({wide.x1:.2f} vs the right edge {body_right:.2f})"))
    # the gloss annotation is fitted too, and on the object line
    gl = p.find("FITGLOSS")
    r.append(check(ann[8] in p.line_of(gl),
                   "a fitted gloss annotation is still on the object line"))
    r.append(check(p.find("FITGLOSSTIER") not in p.line_of(gl),
                   "object and gloss tiers are separate lines"))
    # The rerun warning tells "not measured yet" from "settled".  The cold
    # run has no measurements and must say so; the second must not, or every
    # two-run build is told to run a third time for nothing.
    r.append(check("Annotation columns are not settled" in p.first_log,
                   "the first run asks for a rerun"))
    r.append(check("Annotation columns are not settled" not in p.log,
                   "the second run does not: its page is already right"))
    # the .aux must be readable by a document that has dropped the package
    aux = getattr(p, "aux", "")
    for name, nargs in (("lxannotL", 3), ("lxannotR", 2), ("lxannotUsed", 3)):
        decl = "\\providecommand\\%s[%d]{}" % (name, nargs)
        r.append(check(0 <= aux.find(decl) < aux.find("\\%s{" % name),
                       f"the .aux declares \\{name} before using it"))
    return r


def a_exannot_fitbody(p: Page):
    r"""\ExAnnotFit switched on in the BODY, and off again by grouping.

    The .aux assertions are the point.  A declaration that hangs on
    \AtBeginDocument alone is already too late for this spelling, and what
    it leaves behind is a file full of records that nothing declares --
    which breaks the NEXT compile, if the package is taken out, and shows
    nothing at all on this one's page.
    """
    r = []
    aux = getattr(p, "aux", "")
    for name, nargs in (("lxannotL", 3), ("lxannotR", 2), ("lxannotUsed", 3)):
        decl = "\\providecommand\\%s[%d]{}" % (name, nargs)
        r.append(check(0 <= aux.find(decl) < aux.find("\\%s{" % name),
                       f"a body-level \\\\ExAnnotFit still declares "
                       f"\\\\{name} in the .aux, before using it"))
    # the fitting really did take effect from there ...
    fitted = p.find("[Q1]").x0
    plain = p.find("[Q3]").x0
    r.append(check(abs(p.find("[Q2]").x0 - fitted) < TOL,
                   f"the fitted block is one column "
                   f"({fitted:.2f}, {p.find('[Q2]').x0:.2f})"))
    r.append(check(abs(p.find("[Q4]").x0 - plain) < TOL,
                   f"the unfitted block is one column too "
                   f"({plain:.2f}, {p.find('[Q4]').x0:.2f})"))
    # ... and \ExAnnotFit respects grouping: the block after the group is
    # back at \ExAnnotColumn, which for these examples is well right of a
    # fitted column.
    r.append(check(fitted < plain - TOL,
                   f"\\\\ExAnnotFit ends with its group: the fitted block is "
                   f"at {fitted:.2f}, the one after it back at "
                   f"\\\\ExAnnotColumn ({plain:.2f})"))
    r.append(check("Annotation columns are not settled" not in p.log,
                   "the second run is settled"))
    return r


def a_exannot_beamer(p: Page):
    r"""\exannot in a beamer deck, which is where it was reported from.

    A frame is typeset once per overlay slide with the counters restored,
    so an annotated example that spans slides is measured and recorded
    once per slide under one group key.  Taking the minimum again over a
    reading the previous slide already contributed has to be idempotent,
    and the page is where that shows: the annotation of BEAMOVER appears
    on both slides and both must be at one x.
    """
    r = []
    # the fitted column of an example that spans slides is one column
    xp = p.find_all("[XP]")
    r.append(check(len(xp) == 2,
                   f"the overlaid example is set on both slides "
                   f"(found {len(xp)} of its annotation)"))
    if len(xp) == 2:
        r.append(check(abs(xp[0].x0 - xp[1].x0) < TOL,
                       f"and its annotation is at one x on both, so "
                       f"recording a slide twice does not move the column "
                       f"({xp[0].x0:.2f} vs {xp[1].x0:.2f})"))
    # the glued spelling, whole and in its block's column, on the object row
    glued = [w for w in p.words if w.text == "(italien)"]
    r.append(check(len(glued) == 1,
                   f"the glued annotation reaches the slide whole "
                   f"(found {len(glued)})"))
    if glued:
        obj = p.find("BEAMGL")
        r.append(check(glued[0] in p.line_of(obj),
                       "... on the object line of its gloss"))
        r.append(check(glued[0] not in p.line_of(p.find("BEAMGLTIER")),
                       "... and not on the gloss tier"))
    # the first frame's two blocks are each one column, and not the same
    # column: beamer changes the font, not the arithmetic
    a, b = p.find("[CP]"), p.find("[TP]")
    r.append(check(abs(a.x0 - b.x0) < TOL,
                   f"the first block is one column ({a.x0:.2f}, {b.x0:.2f})"))
    if glued:
        r.append(check(abs(glued[0].x0 - a.x0) > TOL,
                       f"and the glossed block gets its own "
                       f"({glued[0].x0:.2f} vs {a.x0:.2f})"))
    r.append(check("Annotation columns are not settled" not in p.log,
                   "the second run is settled"))
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
    # veraPDF cannot see this one: an /Alt that is present and well-formed
    # satisfies every profile however little it wraps, because /K is
    # optional in ISO 32000-1 (Table 323).  Asked here as well as in
    # altkids because this case is the whole tagging gate, and the
    # invariant needs no list of expected strings to hold.
    orphans = struct_empty_alts(p.path)
    r.append(check(not orphans,
                   f"every /Alt in the tree wraps content; these wrap "
                   f"nothing: {orphans}"))
    # the document really did typeset, so a compliant-but-empty PDF cannot
    # pass this case by accident
    for tok in ("UAMAIN", "UAALPHA", "UAOBJ", "UATRANS", "UAALTN", "UAALTG",
                "UAEXE", "UALIST", "UAREL", "UAZTRANS", "UAZAFTER", "UAMOD",
                "UASIDEOBJ", "UASIDETRANS"):
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


def a_tagged(p: Page):
    """Tagged compile (DocumentMetadata) must survive every construct;
    the compile itself is the real assertion (tagpdf errors halt it).

    With one exception, which the compile cannot see: this case carries six
    /Alt-bearing elements, and four of them wrap nothing under lualatex with
    the pre-2026-09-17 .sty.  A compile that survives says nothing about
    that, so it is asserted below rather than left to the two cases that
    happen to cover it.
    """
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
    labels = [row[0].text for row in lst]
    r.append(check(labels == ["pl", "pst", "sg"],
                   f"abbreviation list under tagging: {labels} != "
                   f"['pl', 'pst', 'sg']"))
    if len(lst) == 3:
        r.append(check(abs(lst[0][0].x0 - lst[1][0].x0) < TOL,
                       f"list labels stay flush left under tagging "
                       f"({lst[0][0].x0:.2f} vs {lst[1][0].x0:.2f})"))
        r.append(check(all(row[0].x1 < row[1].x0 + TOL for row in lst),
                       "no list label overruns its explanation under tagging"))
    # The six /Alt elements this case carries must each wrap something;
    # four of them do not with the pre-2026-09-17 .sty, on lualatex only.
    orphans = struct_empty_alts(p.path)
    r.append(check(not orphans,
                   f"every /Alt in the tree wraps content; these wrap "
                   f"nothing: {orphans}"))
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
    labels = [row[0].text for row in lines]
    expected = ["3", "acc", "def", "f\u00e9m", "nom", "obv", "pl", "prs",
                "pst", "sg", "voc"]
    r.append(check(labels == expected,
                   f"front list is complete and alphabetical: {labels} != {expected}"))
    texts = {row[0].text: " ".join(w.text for w in row[1:]) for row in lines}
    for key, meaning in (("3", "third person"), ("acc", "accusative"),
                         ("obv", "obviative"), ("voc", "vocative"),
                         ("f\u00e9m", "f\u00e9minin")):
        r.append(check(texts.get(key) == meaning,
                       f"{key} is explained as {meaning!r} (got {texts.get(key)!r})"))
    # labels flush left in a column of their own: same origin for all of
    # them (a right-aligned label column would spread them by width), and
    # none of them running into its explanation (\labelwidth is the width
    # of the WIDEST key, not of the first one).
    entries = [row for row in lines if len(row) > 1]
    xs = [row[0].x0 for row in entries]
    starts = [row[1].x0 for row in entries]
    r.append(check(xs and max(xs) - min(xs) < TOL,
                   f"list labels are flush left "
                   f"(spread {max(xs) - min(xs):.2f}pt)" if xs else
                   "list labels are flush left (the list is empty)"))
    r.append(check(entries and all(row[0].x1 < row[1].x0 + TOL
                                   for row in entries),
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
