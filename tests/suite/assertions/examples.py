"""Numbering, termination, and the shape of a bare example.

Split out of runtests.py; the assertion bodies are unchanged.  Each
function takes a parsed Page and returns a list of (ok, description) pairs
built with check(), which is the whole protocol.
"""


from suite.check import check, warning_body
from suite.pdf import (
    TOL, Page, example_targets,
)

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


def a_exlbr(p: Page):
    r"""linguex's \ExLBr / \ExRBr are honoured, and are not \theExLBr.

    A linguex document that wants square brackets writes
    \renewcommand{\ExLBr}{[}.  Here that line used to be accepted and do
    nothing: the parentheses came from \theExLBr, which is spelled
    differently, so the document compiled and only the page was wrong.
    Three assertions, because the fix has three parts that can each be
    lost separately -- the main pair, the footnote pair that must NOT
    follow it, and the layer above that still overrides both.
    """
    def label_of(sentinel):
        return p.line_of(p.find(sentinel))[0].text

    r = [check(label_of("EXLBRMAIN") == "[1]",
               f"\\ExLBr reaches the printed number: first example is "
               f"{label_of('EXLBRMAIN')!r}, want '[1]'"),
         check(label_of("EXLBRSECOND") == "[2]",
               f"... and the one after it: {label_of('EXLBRSECOND')!r}")]
    ref = [w.text for w in p.line_of(p.find("EXLBRREF"))]
    r.append(check("[1]" in ref,
                   f"a \\ref prints the same delimiters; the line reads {ref}"))
    # The footnote series has its own pair in linguex, and so must have one
    # here: moving \ExLBr alone must not move it.
    r.append(check(label_of("EXLBRFN") == "(i)",
                   f"the footnote series keeps its own \\FnExLBr: "
                   f"{label_of('EXLBRFN')!r}, want '(i)'"))
    # \theExLBr is where the parenthesis-suppression switch lives, so it
    # has to keep the last word over the character it reads.
    r.append(check(label_of("EXLBROVERRIDE") == "[[3]]",
                   f"\\theExLBr still overrides \\ExLBr: "
                   f"{label_of('EXLBROVERRIDE')!r}, want '[[3]]'"))
    return r


def a_clash_input(p: Page):
    r"""\input expex is a warning, and the document still compiles.

    The named check cannot see this one: expex is plain TeX, \input leaves
    no record for \@ifpackageloaded, and the only trace is that \ex is no
    longer the definition this package installed.  An error would be
    wrong -- redefining \ex is a document's own business -- so what is
    asserted is that the package SAYS so and gets out of the way.
    """
    body = warning_body(p.log, "\\ex is no longer linguexx's")
    r = [check(body, f"the package reports that \\ex was taken from it; "
                     f"the log says {body[:120]!r}")]
    r.append(check("redefined" in body,
                   f"... and says what happened, not merely that something "
                   f"did: {body[:120]!r}"))
    r.append(check(p.find("CLASHINPUT") is not None,
                   "the document still typesets: a warning, not an error"))
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


def a_option_unknown(p: Page):
    r"""An unknown package option warns, is ignored, and costs its neighbours nothing.

    The old \DeclareOption* warned and carried on.  The kernel's key
    interface errors on an undeclared key instead, so the migration to
    \DeclareKeys restored the warning with \DeclareUnknownKeyHandler -- and
    this is the only case that passes an option linguexx does not know, so
    it is the only place that can tell the two apart.

    Three claims, because the cheap version of this test passes for the
    wrong reason.  That the warning names the option is not enough: an
    error message names it too.  So the document must also have REACHED the
    end (both examples on the page), and [norelreflinks], which shared the
    bracket with the bad name, must still have been honoured -- if the
    unknown key aborted option processing the switch would silently revert
    to its default and \Next would come out a link.
    """
    r = []
    body = warning_body(p.log, "Package linguexx Warning: Unknown option")
    r.append(check("bogusoption" in body,
                   f"the warning names the option; got {body!r}"))
    txt = " ".join(w.text for w in p.words)
    for tok in ("OUEXONE", "OUEXTWO"):
        r.append(check(tok in txt,
                       f"{tok} is on the page, so the run was not stopped"))
    for tok, want in (("OUNEXT", "(2)"), ("OULAST", "(1)"), ("OUREF", "(1)")):
        r.append(check(f"{tok} {want}" in txt,
                       f"{tok} prints {want}; got "
                       f"{txt[txt.find(tok):][:len(tok) + 14]!r}"))
    # The neighbour option survived the bad name: \Next is not a link, and
    # \ref beside it still is, exactly as in relreflinks-off.
    got = example_targets(p.raw)
    r.append(check("ExNo.lxex.2" not in got,
                   "[norelreflinks] still took effect: \\Next is not a link"))
    r.append(check(got.count("ExNo.lxex.1") == 1,
                   f"and hyperref's own \\ref still is (one link to example "
                   f"1, got {got.count('ExNo.lxex.1')})"))
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


def a_exsource(p: Page):
    r = []
    inline = p.find("SRCINLINE")
    fallback = p.find("SRCFALLBACK")
    # find the right-hand text edge from the long example's own lines
    body_right = max(w.x1 for w in p.words if w.y0 < fallback.y0 - 2)
    line = p.line_of(fallback)
    right_edge = max(w.x1 for w in line)
    r.append(check(right_edge >= body_right - 2.0,
                   f"fallback source is flush right ({right_edge:.1f} vs "
                   f"text edge {body_right:.1f})"))
    # the inline one must sit on the same line as its example text, at the right
    inline_line = p.line_of(inline)
    r.append(check(len(inline_line) > 2,
                   "inline source shares the line with the example text"))
    r.append(check(inline.x0 > p.width / 2,
                   f"inline source sits in the right half ({inline.x0:.1f})"))
    return r
