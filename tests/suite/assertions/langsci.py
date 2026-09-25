"""[langsci] and [legacy]/gb4e compatibility.

Split out of runtests.py; the assertion bodies are unchanged.  Each
function takes a parsed Page and returns a list of (ok, description) pairs
built with check(), which is the whole protocol.
"""

import re
import shutil

from suite.check import check
from suite.pdf import (
    _band_lines,
    TOL, Page,
)
from suite.structure import (
    struct_has_formula, struct_label_depths,
    struct_ol_classes, verapdf_log_records,
    verapdf_report,
)

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
    def edges(lines):
        return [max(w.x1 for w in line) for line in lines]

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
