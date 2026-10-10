"""Interlinear glosses, the translation line, and text encoding.

Split out of runtests.py; the assertion bodies are unchanged.  Each
function takes a parsed Page and returns a list of (ok, description) pairs
built with check(), which is the whole protocol.
"""

import re

from suite.check import check, warning_body
from suite.pdf import (
    TOL, Page, bookmark_titles, inflated,
)
from suite.structure import (
    struct_alts, struct_exps, verapdf_report,
)

def a_gloss(p: Page):
    r = []
    # two-tier: columns x-aligned pairwise
    for top, below in [("AAA", "aaa"), ("BBB", "bbb"), ("CCC", "ccc")]:
        wt, wb = p.find(top), p.find(below)
        r.append(check(abs(wt.x0 - wb.x0) < TOL,
                       f"gloss column {top}/{below} aligned ({wt.x0:.2f} vs {wb.x0:.2f})"))
    # an empty cell {} is a column, so the glosses after it stay under
    # their own words -- and nothing is under the word it glosses
    for top, below in [("EMPA", "empa"), ("EMPC", "empc"), ("EMPD", "empd"),
                       ("EMQB", "emqb")]:
        wt, wb = p.find(top), p.find(below)
        r.append(check(abs(wt.x0 - wb.x0) < TOL,
                       f"after an empty cell, {below} is under {top} "
                       f"({wt.x0:.2f} vs {wb.x0:.2f})"))
    for top in ("EMPB", "EMQA"):
        w = p.find(top)
        under = [v for v in p.words
                 if v.y0 > w.y1 - 1 and v.y0 < w.y1 + 8 and v.x0 <= w.x0 + 1
                 and v.x1 >= w.x0 + 1]
        r.append(check(not under,
                       f"and the cell under {top} is empty (found {under})"))
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
    txt = " ".join(w.text for w in p.words)
    # the guillemets survive: BOTH marks, the closing one being the casualty
    return [check("«" in txt and "»" in txt,
                  f"\\og...\\fg keeps both guillemets; got "
                  f"{txt[txt.find('FRGUIL'):][:34]!r}")] + _french_judgments(p)


def _french_judgments(p: Page):
    """The judgment half of babel-fr, shared with polyglossia-fr."""
    r = []
    txt = " ".join(w.text for w in p.words)
    # judgments hang and do not displace the text, exactly as elsewhere --
    # but under babel every ? in the source is an active character
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


def a_polyglossia_fr(p: Page):
    r"""French through polyglossia; see the case's header."""
    r = _french_judgments(p)
    rows = [("AGA", "a."), ("BGA", "b."), ("CGA", "c."), ("DGA", "d."),
            ("EGA", "e."), ("FGA", "f.")]
    for tok, want in rows:
        left = p.left_of(p.find(tok))
        got = left[0].text if left else None
        r.append(check(got == want,
                       f"\\{want[0]}g. sets a glossed sub-example "
                       f"labelled {want}: got {got!r}"))
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


def a_morphalign(p: Page):
    r"""\GlossMorphAlign: within a column, each morpheme starts at one x.

    Read off the tiers that are NOT widest at a boundary (see the case's
    header): there the next segment is a word of its own, and two such
    readings of one segment start must coincide.
    """
    r = []

    def gap(left, right):
        return p.find(right).x0 - p.find(left).x1

    # (1) the staircase: each segment start read in two tiers
    b2, c2 = p.find("-Bbbbbbbbb-bc"), p.find("-cb")
    r.append(check(abs(b2.x0 - c2.x0) < TOL,
                   f"segment 2 starts at one x in tiers 2 and 3 "
                   f"({b2.x0:.2f} vs {c2.x0:.2f})"))
    a3, c3 = p.find("-ac"), p.find("-Ccccccccc")
    r.append(check(abs(a3.x0 - c3.x0) < TOL,
                   f"segment 3 starts at one x in tiers 1 and 3 "
                   f"({a3.x0:.2f} vs {c3.x0:.2f})"))
    r.append(check(gap("ca", "-cb") > 2,
                   f"a narrower segment leaves room to the next "
                   f"({gap('ca', '-cb'):.2f}pt after 'ca')"))
    # (2) = is a boundary
    r.append(check(gap("ea", "=Ebbbbbbbbb") > 2,
                   f"a clitic boundary splits: '=Ebbbbbbbbb' is set after "
                   f"the object's first segment ({gap('ea', '=Ebbbbbbbbb'):.2f}pt)"))
    # (3) a braced unit is one segment, and the braces do not print
    r.append(check(gap("ha-hx", "-hb") > 2,
                   f"{{ha-hx}} is one segment, so the gloss is aligned "
                   f"({gap('ha-hx', '-hb'):.2f}pt before '-hb')"))
    r.append(check(not any("{" in w.text or "}" in w.text for w in p.words),
                   "no brace is printed"))
    # (3b) a word braced whole is one segment: the gloss under it is alone
    # in splitting, so it is not spread
    r.append(check(p.find("hq-Hb").text == "hq-Hb",
                   "a word braced whole is one morpheme: the gloss under it "
                   "is not aligned against its inside"))
    # ... and the flag belongs to the braced word alone, not to the next one
    r.append(check(gap("ia", "-Ibbbbbbbbb") > 2,
                   f"the word after a braced one is split as usual "
                   f"({gap('ia', '-Ibbbbbbbbb'):.2f}pt before '-Ibbbbbbbbb')"))
    # (4) a mismatch is set by word, and says so once
    k1, k2 = p.find("Kkkkkkkkk-kb"), p.find("kx-ky-kz")
    r.append(check(abs(k1.x0 - k2.x0) < TOL,
                   f"2 against 3 morphemes: both tiers whole at the column "
                   f"origin ({k1.x0:.2f} vs {k2.x0:.2f})"))
    k3 = p.find("kq-Kbbbbbbbbb")
    r.append(check(k3.text == "kq-Kbbbbbbbbb" and abs(k3.x0 - k1.x0) < TOL,
                   "... and the whole column: the tier that agrees with tier "
                   "1 is not aligned with it either"))
    body = warning_body(p.log, "Package linguexx Warning: Gloss column")
    r.append(check("Gloss column 1: the segmented tiers split into 2 and 3 and 2 "
                   "morphemes" in body and "aligned by word" in body,
                   f"the mismatch is reported with its column and counts: "
                   f"{body!r}"))
    r.append(check(p.log.count("which do not match") == 1,
                   f"exactly one mismatch warning in the log, got "
                   f"{p.log.count('which do not match')}"))
    # (5) a leading hyphen is not a boundary
    m, n = p.find("-Mm"), p.find("Nnnnnnnnn-nb")
    r.append(check(abs(m.x0 - n.x0) < TOL,
                   f"-Mm is one segment and stays at the column origin "
                   f"({m.x0:.2f} vs {n.x0:.2f})"))
    # (6) an unsegmented tier does not block the others
    r.append(check(gap("pa", "-Pbbbbbbbbb") > 2,
                   f"tiers 2 and 3 are aligned past an unsegmented tier 1 "
                   f"({gap('pa', '-Pbbbbbbbbb'):.2f}pt before '-Pbbbbbbbbb')"))
    # (7) each tier in its own font: tier 1 is widest and stays one word
    r.append(check(len(p.find_all("Rrrrrrrr")) == 1
                   and p.find("Rrrrrrrr-rb").text == "Rrrrrrrr-rb",
                   "a \\tiny tier is measured \\tiny: the object's first "
                   "segment is still the widest, and its word unbroken"))
    r.append(check(gap("ssssssssss", "-sb") > 2,
                   f"the \\tiny tier is aligned ({gap('ssssssssss', '-sb'):.2f}pt "
                   f"before '-sb')"))
    # (8) the pad counts into the first segment
    v2, x2 = p.find("-Vbbbbbbbbb"), p.find("-xb")
    r.append(check(abs(v2.x0 - x2.x0) < TOL,
                   f"with [phantomalign], segment 2 starts at one x in the "
                   f"unpadded and a padded tier ({v2.x0:.2f} vs {x2.x0:.2f})"))
    r.append(check("Overfull \\hbox" not in p.log,
                   "every segment fits its box: no overfull \\hbox (a pad "
                   "left out of the measuring overflows the first segment)"))
    w = p.find("Wwwwwwwwww-xb")
    r.append(check(abs(w.x1 - x2.x1) < TOL,
                   f"... and in the padded tier holding the widest first "
                   f"segment, whose word ends where '-xb' does "
                   f"({w.x1:.2f} vs {x2.x1:.2f})"))
    # (8b) a split pad: the "(" of both tiers flush, segment 2 at one x
    # in the two tiers that open a gap before it
    z1 = p.find("([za")
    z2 = next(w for w in p.find_all("Zzzzzzzzzz") if w.y0 > z1.y0)
    zparen = max((w for w in p.line_of(z2)
                  if w.text.startswith("(") and w.x0 <= z2.x0 + TOL),
                 key=lambda w: w.x0)
    r.append(check(abs(zparen.x0 - z1.x0) < TOL,
                   f"a pad split behind the tier's own '(': both '(' flush "
                   f"({zparen.x0:.2f} vs {z1.x0:.2f})"))
    zb, zs = p.find("-Zbbbbbbbbb"), p.find("-zc")
    r.append(check(abs(zb.x0 - zs.x0) < TOL,
                   f"... and segment 2 starts at one x in both tiers "
                   f"({zb.x0:.2f} vs {zs.x0:.2f})"))
    # (10) off: one word per tier, at the column origin
    d = p.find("Ddddddddd-db-dc")
    for tok in ("fa-Fbbbbbbbbb-fc", "ga-gb-Ggggggggg"):
        t = p.find(tok)
        r.append(check(abs(t.x0 - d.x0) < TOL,
                       f"\\GlossMorphAlignOff: {tok} is one word at the column "
                       f"origin ({t.x0:.2f} vs {d.x0:.2f})"))
    return r


def a_morphalign_ua(p: Page):
    r"""The alignment moves ink and nothing else: the tree of an aligned
    gloss is the tree of the same gloss set by word, and the measuring
    leaves no structure behind (veraPDF passes that either way, so the
    counts are the guard)."""
    r = []
    verdicts, failures, _ = verapdf_report(p.path)
    r.append(check(bool(verdicts) and all(ok for _, ok in verdicts),
                   f"veraPDF: compliant on every profile ({verdicts}; "
                   f"{failures})"))
    exps = struct_exps(inflated(p.raw))
    want = ["plural", "locative", "present"]
    r.append(check(exps == want + want,
                   f"each \\lpzg expansion once per gloss, the aligned and "
                   f"the word-set alike, none from the measuring: {exps}"))
    alts = struct_alts(p.raw)
    r.append(check(alts == ["ir or er", "ir or er"],
                   f"the \\altn's spoken form once per gloss: {alts}"))
    return r


def _staircase(p: Page, seg2, seg3, where):
    r"""The two readings of a three-tier staircase (see morphalign.tex):
    the start of segment 2 in tiers 2 and 3, that of segment 3 in tiers 1
    and 3.  Each pair is (word, word); `where` names the gloss.

    Matched exactly, not with p.find: its containment fallback would find
    "-scb" inside the unsplit "sca-scb-SCcccccccc" of a gloss set by word,
    where both readings sit at the column origin and coincide anyway."""
    r = []
    for k, (a, b) in ((2, seg2), (3, seg3)):
        wa = [w for w in p.words if w.text == a]
        wb = [w for w in p.words if w.text == b]
        r.append(check(len(wa) == 1 and len(wb) == 1,
                       f"{where}: {a} and {b} are words of their own, so the "
                       f"tiers were split ({len(wa)}, {len(wb)})"))
        if not (wa and wb):
            continue
        wa, wb = wa[0], wb[0]
        r.append(check(abs(wa.x0 - wb.x0) < TOL,
                       f"{where}: segment {k} starts at one x in two tiers "
                       f"({a} {wa.x0:.2f} vs {b} {wb.x0:.2f})"))
    return r


def a_morphalign_mix(p: Page):
    r"""\GlossMorphAlign inside \GlossTransSide, beside an \exannot, and in
    a gloss that wraps; see the case's header."""
    r = []
    # (1) \GlossTransSide: aligned, and the side column where it is by word
    r += _staircase(p, ("-SBbbbbbbbb-sbc", "-scb"), ("-sac", "-SCcccccccc"),
                    "\\GlossTransSide")
    ta, tb = p.find("STRANSA"), p.find("STRANSB")
    r.append(check(abs(ta.x0 - tb.x0) < TOL,
                   f"the side translation is where it is by word "
                   f"({ta.x0:.2f} vs {tb.x0:.2f})"))
    grid = ("SAaaaaaaaa-sab", "-sac", "-SBbbbbbbbb-sbc", "-SCcccccccc")
    right = max(p.find(w).x1 for w in grid)
    r.append(check(ta in p.line_of(p.find("SAaaaaaaaa-sab"))
                   and ta.x0 > right,
                   f"... beside the aligned grid, on its first line and "
                   f"clear of it ({ta.x0:.2f} vs {right:.2f})"))
    # (2) \exannot: aligned, and the annotation clear of the aligned grid
    r += _staircase(p, ("-XBbbbbbbbb-xbc", "-xcb"), ("-xac", "-XCcccccccc"),
                    "\\exannot")
    an = p.find("[XANNOT]")
    right = max(p.find(w).x1 for w in ("-xac", "-XBbbbbbbbb-xbc",
                                       "-XCcccccccc"))
    r.append(check(an in p.line_of(p.find("XAaaaaaaaa-xab"))
                   and an.x0 > right,
                   f"the annotation is on the object line, clear of the "
                   f"aligned grid ({an.x0:.2f} vs {right:.2f})"))
    # (3) a gloss that wraps: every column aligned, on every line
    for n in range(1, 9):
        r += _staircase(p, (f"-V{n}bbbbbbbb-v{n}c", f"-u{n}b"),
                        (f"-w{n}c", f"-U{n}cccccccc"),
                        f"wrapped gloss, column {n}")
    first, last = p.find("W1aaaaaaaa-w1b"), p.find("W8aaaaaaaa-w8b")
    r.append(check(last.y0 > first.y0 + 30,
                   f"the long gloss wraps ({first.y0:.2f} -> {last.y0:.2f})"))
    # the leftmost object word of each line (the first line also holds the
    # example number)
    starts = [min(w.x0 for w in p.line_of(word) if w.text.startswith("W"))
              for word in (first, last)]
    r.append(check(abs(starts[0] - starts[1]) < TOL,
                   f"... and its last line starts where its first does "
                   f"({starts[0]:.2f} vs {starts[1]:.2f})"))
    return r


def a_morphalign_mix_ua(p: Page):
    r"""morphalign-mix under PDF/UA-2: compliant, and the measuring of the
    side grid, the annotated grid and the wrapped grid leaves no structure
    behind (see the case's header)."""
    r = []
    verdicts, failures, _ = verapdf_report(p.path)
    r.append(check(bool(verdicts) and all(ok for _, ok in verdicts),
                   f"veraPDF: compliant on every profile ({verdicts}; "
                   f"{failures})"))
    exps = struct_exps(inflated(p.raw))
    want = ["plural", "locative", "present"]
    r.append(check(exps == want * 3,
                   f"each \\lpzg expansion once per gloss, in the side, the "
                   f"annotated and the wrapped grid alike: {exps}"))
    return r


def a_morphalign_beamer(p: Page):
    r"""\GlossMorphAlign in a beamer frame; see the case's header."""
    r = []
    seg2, seg3 = ("-BBbbbbbbbb-bbc", "-bcb"), ("-bac", "-BCcccccccc")

    def exact(tok):
        # not find_all: "-bcb" is also inside the unaligned "bca-bcb-..."
        return [w for w in p.words if w.text == tok]

    for tok in seg2 + seg3:
        r.append(check(len(exact(tok)) == 2,
                       f"the first example is set, aligned, on both slides "
                       f"({tok} found {len(exact(tok))} times)"))
    for k, (a, b) in ((2, seg2), (3, seg3)):
        wa, wb = exact(a), exact(b)
        xs = [w.x0 for w in wa + wb]
        r.append(check(len(xs) == 4 and max(xs) - min(xs) < TOL,
                       f"segment {k} starts at one x in two tiers and on "
                       f"both slides: {[round(x, 2) for x in xs]}"))
    r += _staircase(p, ("-BEbbbbbbbb-bec", "-bfb"), ("-bdc", "-BFcccccccc"),
                    "an example after \\pause")
    return r


def a_rtl(p: Page):
    r"""\GlossRTL on the page; see the case's header."""
    r = []
    one, two, three = p.find("RAONE"), p.find("RATWO"), p.find("RATHREE")
    r.append(check(one.x0 > two.x0 > three.x0,
                   f"columns run from the right: first word rightmost "
                   f"({one.x0:.2f} > {two.x0:.2f} > {three.x0:.2f})"))
    b1 = p.find("RBONEXX")
    r.append(check(abs(one.x1 - b1.x1) < TOL and b1.x0 < one.x0 - 2,
                   f"a column's cells sit against its right edge "
                   f"({one.x1:.2f} vs {b1.x1:.2f})"))
    t1, b3 = p.find("RTRANSONE"), p.find("RBTHREE")
    r.append(check(abs(b3.x0 - t1.x0) < TOL,
                   f"a short grid sits beside its number, starting at the "
                   f"text margin like its translation ({b3.x0:.2f} vs "
                   f"{t1.x0:.2f})"))
    first, last = p.find("LWAA"), p.find("LWAN")
    line1 = [w for w in p.line_of(first) if w.text.startswith("LWA")]
    r.append(check(first.x0 == max(w.x0 for w in line1),
                   "a long grid: the first word is the rightmost of its line"))
    line2 = [w for w in p.line_of(last) if w.text.startswith("LWA")]
    end1, end2 = max(w.x1 for w in line1), max(w.x1 for w in line2)
    r.append(check(last.y0 > first.y0 + 5 and abs(end1 - end2) < TOL,
                   f"... it wraps, and both lines end at one right edge "
                   f"({end1:.2f} vs {end2:.2f})"))
    star = [w for w in p.words if w.text == "*"]
    jud = p.find("JUDTWO")
    r.append(check(len(star) == 1 and star[0].x1 <= jud.x0,
                   f"a judgment mark hangs on the left of the grid "
                   f"({star[0].x1 if star else None} vs {jud.x0:.2f})"))
    r.append(check(p.log.count("which do not match") == 1,
                   f"a mismatch in a measured grid is reported once, not "
                   f"once per setting: {p.log.count('which do not match')}"))
    off1, off2 = p.find("OFFONE"), p.find("OFFTWO")
    r.append(check(off1.x0 < off2.x0,
                   "\\GlossRTLOff: left to right again"))
    script = p.line_of(p.find("(6)"))
    dalet = [w for w in script if "\u05d3" in w.text]
    kaf = [w for w in script if "\u05db" in w.text]
    r.append(check(len(dalet) == 1 and len(kaf) == 1
                   and dalet[0].x0 > kaf[0].x0,
                   f"\\glscript sets its line right to left: the first word "
                   f"right of the second ({[w.text for w in script]})"))
    return r


def a_rtl_side(p: Page):
    r"""\GlossTransSide gives way to \GlossRTL, with a warning, and the
    translation goes underneath the grid."""
    body = warning_body(p.log, "Package linguexx Warning:")
    t, g = p.find("SIDETRANS"), p.find("sone")
    return [
        check("cannot be combined with" in body,
              f"the combination is reported: {body!r}"),
        check(t.y0 > g.y0 + 5,
              f"the translation is underneath the grid, not beside it "
              f"({t.y0:.2f} vs {g.y0:.2f})"),
    ]


def a_rtl_move(p: Page):
    r"""A movement arrow in a right-to-left grid, under LuaTeX: the grid is
    not measured (the arrow refuses to run twice), so it compiles and sits
    at the right margin, and the arrow's line gets its room."""
    one, three = p.find("MVONE"), p.find("MVTHREE")
    margin = max(w.x1 for w in p.line_of(p.find("MVREF")))
    return [
        check(one.x0 > three.x0,
              f"the grid runs from the right ({one.x0:.2f} > {three.x0:.2f})"),
        check(abs(one.x1 - margin) < TOL,
              f"not measured: it ends at the right margin, where the full "
              f"line above it does ({one.x1:.2f} vs {margin:.2f})"),
    ]


def a_rtl_morph(p: Page):
    r"""\GlossMorphAlign in a right-to-left grid; see the case's header."""
    pq, r1, ss = p.find("Pa-Qqqqqqqqq"), p.find("Rrrrrrrrr-"), p.find("ss")
    ta, uu = p.find("ta-"), p.find("uu")
    return [
        check(r1.text == "Rrrrrrrrr-" and ta.text == "ta-",
              "the delimiter closes the morpheme before it: 'Rrrrrrrrr-' and "
              "'ta-' are words of their own"),
        check(abs(r1.x1 - ta.x1) < TOL,
              f"the boundary is at one x in two tiers ({r1.x1:.2f} vs "
              f"{ta.x1:.2f})"),
        check(abs(ss.x1 - uu.x1) < TOL and abs(pq.x1 - uu.x1) < TOL,
              f"every word ends at the column's right edge ({pq.x1:.2f}, "
              f"{ss.x1:.2f}, {uu.x1:.2f})"),
        check(pq.x0 > r1.x0 + 2,
              f"a narrower morpheme sits at the end of its box, not the start "
              f"({pq.x0:.2f} vs {r1.x0:.2f})"),
    ]
