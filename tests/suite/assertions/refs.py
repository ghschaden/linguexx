"""Cross-references: \ref, the relative family, and the anchors they land on.

Split out of runtests.py; the assertion bodies are unchanged.  Each
function takes a parsed Page and returns a list of (ok, description) pairs
built with check(), which is the whole protocol.
"""

import re

from suite.check import check, warning_body
from suite.pdf import (
    Page, dest_page, example_targets, link_targets,
)

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
