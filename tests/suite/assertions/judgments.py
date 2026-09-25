"""Judgment marks, the gutter they hang into, and phantom alignment.

Split out of runtests.py; the assertion bodies are unchanged.  Each
function takes a parsed Page and returns a list of (ok, description) pairs
built with check(), which is the whole protocol.
"""

import re

from suite.check import check
from suite.pdf import (
    TOL, Page,
)
from suite.structure import (
    _qdf, struct_alts,
)

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
        ("JLABEL", "PLABEL", "main level behind a \\label"),
        ("JSUBLAB", "PSUBLAB", "letter level behind a \\sublabel"),
        ("JGLOSS", "PGLOSS", "gloss object tier behind a \\label"),
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
    for judged, level in [("JSUB", "letter"), ("JROMAN", "roman"),
                          ("JSUBLAB", "letter, behind a \\sublabel")]:
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
    # A skipped label with no mark behind it displaces nothing at all:
    # this is the pair whose two members BOTH sit at the text edge.
    wq, wp = p.find("QLABEL"), p.find("PLABEL")
    r.append(check(abs(wq.x0 - wp.x0) < TOL,
                   f"a \\label alone does not displace text "
                   f"({wq.x0:.2f} vs {wp.x0:.2f})"))
    # The other half of the \label case.  Hanging the mark means taking the
    # label out of the input and putting it back after the \item, and a
    # replay that lands in the wrong place is invisible on the page: the
    # example still looks right and only the reference to it is wrong.  So
    # the references are read back off the page.  \prefrange is in here
    # because it is the one that needs the \sublabel to have been replayed
    # at its own DEPTH -- it prints the recorded letter, and a \sublabel
    # replayed one level out records nothing and silently falls back to a
    # full \pref.
    num = re.compile(r"^\(\d+\)$")

    def number_of(sentinel):
        toks = [w.text for w in p.line_of(p.find(sentinel))]
        hit = [t for t in toks if num.match(t)]
        return hit[0] if hit else None

    main, sub, gloss = (number_of(s) for s in
                        ("JLABEL", "JSUBLAB", "JGLOSS"))
    refs = "".join(w.text for w in p.line_of(p.find("REFCHECK")))
    refs = refs.replace("\u2013", "--").replace("\u2014", "--")
    r.append(check(all((main, sub, gloss)),
                   f"the labelled examples print a number "
                   f"(got {main}, {sub}, {gloss})"))
    if all((main, sub, gloss)):
        # \prefrange is the unparenthesised half of \refrange, so it
        # prints the bare number and the bare letter: "7--a".
        want = [main, sub[:-1] + "a)", gloss, main.strip("()") + "--a"]
        for w in want:
            r.append(check(w in refs,
                           f"a \\label carried across a judgment mark still "
                           f"resolves: expected {w} in {refs!r}"))
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

    # (7)-(9): the pad is the object word's leading run MINUS the tier's own,
    # clamped at zero.  Read off the TOKEN left edges (both tokens open with
    # a mark here), since the stems differ in case and, in (8), in size.

    # (7) same mark, same font: the pad is zero and the parens sit flush.
    # The unconditional pad -- the object's "(" added on top of the gloss's
    # own -- put the gloss a full paren-width right of where it belonged.
    o7, g7 = p.find("(Ppp"), p.find("(ppp")
    r.append(check(abs(g7.x0 - o7.x0) < TOL,
                   f"same mark in both tiers: no pad, parens flush "
                   f"({g7.x0:.2f} vs {o7.x0:.2f})"))

    # (8) same mark, tier 2 at \tiny: the pad is the difference of the two
    # bracket widths -- strictly greater than zero and strictly less than the
    # full object bracket of (1).  The lower bound kills "skip the pad when
    # the prefixes match" (which would flush the brackets and leave the real
    # glyphs apart); the upper bound kills the unconditional pad.
    o8, g8 = p.find("[Rrr"), p.find("[rrr")
    pad8 = g8.x0 - o8.x0
    r.append(check(pad8 > TOL,
                   f"smaller tier, same mark: pad is positive "
                   f"({pad8:.2f}pt) -- not skipped because the marks match"))
    r.append(check(pad8 < shift1 - TOL,
                   f"smaller tier, same mark: pad is the DIFFERENCE, short of "
                   f"the full bracket ({pad8:.2f} vs {shift1:.2f}pt)"))

    # (9) clamp: the gloss carries more mark than the object, so the exact
    # pad is negative and would push ink left out of the column.  Zero
    # instead -- the gloss keeps the column origin.
    o9, g9 = p.find("?Ttt"), p.find("*([ttt")
    r.append(check(abs(g9.x0 - o9.x0) < TOL,
                   f"pad clamped at zero: gloss keeps the column origin "
                   f"({g9.x0:.2f} vs {o9.x0:.2f})"))
    return r


def a_parens_glossing_align(p: Page):
    """A translation that reproduces the object language's parentheses.

    The reported document behind the subtraction in \\__lx_gl_pad:nn:
    "(e questa)" glossed "(est celle-ci)" put the gloss a paren-width right of
    the object, because the pad was measured off the object word alone and
    then added to a gloss word that already carried the same "(".  Real
    prose rather than the synthetic stems of phantomalign.tex -- \\ag./\\bg.,
    a hoisted judgment mark, colour, a braced multi-word gloss cell -- so the
    rule is exercised where it was reported and not only where it is probed.
    The two examples are the same words in two orders, as the report had
    them.  The unmarked columns are deliberately NOT asserted here: a word
    with no leading marks gets no pad under any variant of this rule, so
    checking one would be an assertion nothing can fail.  phantomalign.tex
    (7)-(9) carries the discriminating geometry."""
    def both(text):
        """The two occurrences of an exact token, in reading order."""
        ws = sorted((w for w in p.words if w.text == text), key=lambda w: w.y0)
        assert len(ws) == 2, f"expected 2 of {text!r}, found {len(ws)}: {ws}"
        return ws

    r = []
    for n, (o, g) in enumerate(zip(both("(è"), both("(est")), start=1):
        r.append(check(abs(g.x0 - o.x0) < TOL,
                       f"example {n}: gloss paren sits under the object paren "
                       f"({g.x0:.2f} vs {o.x0:.2f})"))
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


def a_phantommarks_tagged(p: Page):
    r"""The [phantomalign] pad ships width, never structure.

    The pad measures a word's leading run by typesetting it into a box that
    is dropped, and tagpdf builds the tree as material is executed -- so a
    declared mark that enters math left a Formula element per measure, with
    nothing on the page behind it.  veraPDF passes that file, so the count
    is the only guard.  The case prints exactly two math marks, one per
    tier, so the tree must hold exactly two Formula elements: fewer means
    the visible marks lost their tagging, more means the measures are back
    in the tree (four, without the \tag_suspend:n).
    """
    n = len(re.findall(r"/S\s*/Formula", _qdf(p.path)))
    return [check(n == 2,
                  f"two Formula elements, one per visible math mark, and none "
                  f"from the pad's measuring boxes; got {n}")]
