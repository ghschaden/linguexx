"""Interlinear glosses, the translation line, and text encoding.

Split out of runtests.py; the assertion bodies are unchanged.  Each
function takes a parsed Page and returns a list of (ok, description) pairs
built with check(), which is the whole protocol.
"""

import re

from suite.check import check
from suite.pdf import (
    TOL, Page, bookmark_titles,
)

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


def a_glt_side(p: Page):
    r"""\GlossTransSide: the free translation beside the grid, not under it.

    Every assertion here is about a box's reference point or about what mode
    TeX was in, and three of the four failed during implementation.  None of
    them is an error and all of them look like a deliberate layout, which is
    why they are measured rather than looked at.
    """
    r = []
    # --- the default is untouched: translation UNDER the grid, same left edge
    btier, btrans = p.find("BELOWTIER"), p.find("BELOWTRANS")
    r.append(check(btrans.y0 > btier.y0 + 1,
                   f"below: the translation is under the gloss tier "
                   f"({btrans.y0:.2f} vs {btier.y0:.2f})"))
    r.append(check(abs(btrans.x0 - btier.x0) < TOL,
                   f"below: it starts at the grid's left edge "
                   f"({btrans.x0:.2f} vs {btier.x0:.2f})"))
    # --- beside: clear of the grid's rightmost ink, level with its TOP
    sobj, stier = p.find("SIDEOBJ"), p.find("SIDETIER")
    strans = p.find("SIDETRANS")
    grid_right = max(w.x1 for w in p.line_of(sobj) + p.line_of(stier)
                     if w.x0 < strans.x0)
    r.append(check(strans.x0 > grid_right,
                   f"beside: the translation is clear of the grid "
                   f"({strans.x0:.2f} vs {grid_right:.2f})"))
    # \vtop and not \vbox: the boxes align on their FIRST baselines.  The
    # translation is deliberately the taller of the two, so a \vbox -- whose
    # reference point is its LAST baseline -- would pull its top above the
    # grid's, and the two could not agree by accident.
    r.append(check(abs(strans.y0 - sobj.y0) < 4,
                   f"beside: translation and object tier start on one line "
                   f"({strans.y0:.2f} vs {sobj.y0:.2f}); a \\\\vbox would "
                   f"align their last lines instead"))
    # the grid stays on ONE row of columns.  Losing \leavevmode inside the
    # box leaves TeX in internal vertical mode, so the first column becomes
    # a line of its own -- at ANY width, which is why a wider column hides
    # this instead of fixing it.
    objline = [w.text for w in p.line_of(sobj)]
    for word in ("il", "mio", "libro"):
        r.append(check(word in objline,
                       f"beside: the grid keeps '{word}' on the object row "
                       f"instead of wrapping after the first column "
                       f"(row reads {objline})"))
    # the example number is level with the grid's first line.  \parskip glue
    # at the top of the \vtop makes the box's height zero, dropping all of
    # it below the baseline and so a line under its own number.
    r.append(check(any(re.fullmatch(r"\(\d+\)", w.text) for w in p.line_of(sobj)),
                   f"beside: the example number sits on the grid's first "
                   f"line (that line reads {objline})"))
    # --- a nonzero \parskip must not eat the boxes' height.  article's
    # default is "0pt plus 1pt", natural size zero, so no other block here
    # can tell whether the box zeroes it; this one sets a real length.
    pobj, ptrans = p.find("PSKOBJ"), p.find("PSKTRANS")
    r.append(check(abs(ptrans.y0 - pobj.y0) < 4,
                   f"a nonzero \\parskip does not drop the boxes below "
                   f"their baseline ({ptrans.y0:.2f} vs {pobj.y0:.2f})"))
    r.append(check(any(re.fullmatch(r"\(\d+\)", w.text)
                       for w in p.line_of(pobj)),
                   "... and the example number stays level with the grid"))
    # --- a side gloss with no \glt at all is still put down
    r.append(check(p.find("NOGLT") is not None
                   and p.find("NOGLTTIER") is not None,
                   "a side gloss with no \\\\glt is still placed"))
    # --- no room: falls back to the below position, and says so
    ntier, ntrans = p.find("NARROWTIER"), p.find("NARROWTRANS")
    r.append(check(ntrans.y0 > ntier.y0 + 1,
                   f"no room: the translation falls back underneath "
                   f"({ntrans.y0:.2f} vs {ntier.y0:.2f})"))
    r.append(check("No room for a side translation" in p.log,
                   "no room: and the log says why"))
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
