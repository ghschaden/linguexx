"""Interlinear glosses, the translation line, and text encoding.

Split out of runtests.py; the assertion bodies are unchanged.  Each
function takes a parsed Page and returns a list of (ok, description) pairs
built with check(), which is the whole protocol.
"""

import re

from suite.check import check, warning_body
from suite.geometry import brace_bulge
from suite.pdf import (
    TOL, Page, bookmark_titles, inflated, slides,
)
from suite.structure import (
    show_pdf_tags_xml, struct_alts, struct_empty_alts, struct_exps,
    struct_lbl_depths, verapdf_compliant,
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


def a_polyglossia_de(p: Page):
    r"""polyglossia's German shorthands inside linguexx constructs; see the
    case's header.  Each word is compared with the same shorthand set as
    plain text on the CONTROL line, never with a spelling written here."""
    r = []
    control = [w.text for w in p.line_of(p.find("CONTROL"))][1:]
    r.append(check(len(control) == 6, f"the control line: {control}"))
    # the comparison below is relative, so it would pass with the
    # shorthands off; the control must show they are on
    r.append(check(bool(control) and control[0].startswith("„")
                   and not any('"' in w for w in control),
                   f"the shorthands are active at all: {control}"))
    want = dict(zip(("hoehle", "zuckerguss", "suess", "schiffahrt", "gross",
                     "zuckerguss2"), [_nfc(w) for w in control]))

    def line(tok):
        # an \\altn stack's rows sit above and below the line it is on
        words = p.words if tok == "DEALT" else p.line_of(p.find(tok))
        return _nfc(" ".join(w.text for w in words))

    for tok, key, where in (("DEMAIN", "hoehle", 'main example ("` "\')'),
                            ("DESUB", "zuckerguss", 'sub-example ("-)'),
                            ("DESUB", "suess", 'sub-example ("< ">)'),
                            ("DEOBJ", "schiffahrt", 'gloss tier ("f)'),
                            ("DETRANS", "gross", "translation"),
                            ("DEALT", "zuckerguss2", '\\altn alternative ("=)')):
        got = line(tok) if p.find(tok) else ""
        r.append(check(want.get(key, "\0") in got,
                       f"the shorthand comes out as in plain text in the "
                       f"{where}: want {want.get(key)!r} in {got!r}"))
    quote = p.find("DEQUOTE")
    left = p.left_of(quote) if quote else []
    r.append(check(quote is not None and quote.text.startswith("„")
                   or bool(left) and left[-1].text == "„",
                   f"an example may open with the active \": the quote is "
                   f"typeset, not taken for a judgment: {quote}"))
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
    r.append(verapdf_compliant(p.path))
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
    r.append(verapdf_compliant(p.path))
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


def a_rtl_main(p: Page):
    r"""A right-to-left document's examples mirror a left-to-right one's;
    see the case's header.  Every expected position is derived from the
    english example set in the same file."""
    r = []
    left = p.find("LTRMAIN")
    L = min(w.x0 for w in p.line_of(left))          # the (1), on the margin
    R = p.width - L                                  # symmetric margins
    d_main = left.x0 - L
    d_sub = p.find("LTRSUBA").x0 - L
    ltr_b = p.find("LTRSUBB")
    ltr_star = [w for w in p.left_of(ltr_b) if w.text == "*"]
    gap = ltr_b.x0 - ltr_star[-1].x1 if ltr_star else None

    main = p.find("RTLMAIN")
    line = p.line_of(main)
    r.append(check(abs(max(w.x1 for w in line) - R) < TOL,
                   f"the number sits against the right margin: "
                   f"{max(w.x1 for w in line):.2f} vs {R:.2f}"))
    r.append(check(abs(main.x1 - (R - d_main)) < TOL,
                   f"the text starts as far in from the right as the "
                   f"reference's does from the left: {main.x1:.2f} vs "
                   f"{R - d_main:.2f}"))
    suba = p.find("RTLSUBA")
    r.append(check(abs(suba.x1 - (R - d_sub)) < TOL,
                   f"a sub-example's text, likewise: {suba.x1:.2f} vs "
                   f"{R - d_sub:.2f}"))
    label = [w for w in p.line_of(suba) if w.x0 >= suba.x1 - TOL]
    lab_x1 = max((w.x1 for w in label), default=0)
    r.append(check(abs(lab_x1 - (R - d_main)) < TOL,
                   f"its letter stands at the main text's edge, not against "
                   f"its own text: {lab_x1:.2f} vs {R - d_main:.2f}"))
    subb = p.find("RTLSUBB")
    star = [w for w in p.line_of(subb) if "*" in w.text and w.x0 >= subb.x1]
    r.append(check(gap is not None and bool(star)
                   and abs(star[0].x0 - subb.x1 - gap) < TOL,
                   f"the mark hangs to the right of the text it judges, as "
                   f"far from it as on the left in the reference: "
                   f"{[w.text for w in star]} gap "
                   f"{(star[0].x0 - subb.x1) if star else None} vs {gap}"))

    # an english example in this Hebrew document: mirrored like the rest
    en = p.find("ENMAIN")
    enlines = sorted({round(w.y0) for w in p.words
                      if abs(w.x0 - en.x0) < 400 and en.y0 - 1 <= w.y0
                      < p.find("ENSUBA").y0 - 1})
    first = p.line_of(en)
    r.append(check(abs(max(w.x1 for w in first) - R) < TOL,
                   f"an english example is numbered at the RIGHT margin, as "
                   f"the main language has it: "
                   f"{max(w.x1 for w in first):.2f} vs {R:.2f}"))
    text1 = [w for w in first if w.x1 < R - d_main + 2 * TOL]
    r.append(check(abs(max(w.x1 for w in text1) - (R - d_main)) < 1.0
                   and min(w.x0 for w in text1) < L + 2,
                   f"its first line fills the mirrored text column: "
                   f"{min(w.x0 for w in text1):.2f}-"
                   f"{max(w.x1 for w in text1):.2f} vs {L:.2f}-"
                   f"{R - d_main:.2f}"))
    r.append(check(len(enlines) >= 2,
                   f"it runs onto a second line: {len(enlines)}"))
    last = [w for w in p.words if round(w.y0) == enlines[-1]] \
        if enlines else []
    r.append(check(bool(last) and abs(max(w.x1 for w in last)
                                      - (R - d_main)) < TOL,
                   f"its short last line stands against the text edge, no "
                   f"space left before \\a. to push it off: "
                   f"{max((w.x1 for w in last), default=0):.2f} vs "
                   f"{R - d_main:.2f}"))
    ensuba = p.find("ENSUBA")
    r.append(check(abs(en.x0 - min(w.x0 for w in text1)) < TOL,
                   f"its words run left to right: ENMAIN, the first word, is "
                   f"the leftmost of its line ({en.x0:.2f})"))
    sub_line = p.line_of(ensuba)
    sub_text = [w for w in sub_line if w.x1 <= R - d_sub + TOL]
    r.append(check(abs(max(w.x1 for w in sub_text) - (R - d_sub)) < TOL,
                   f"a short sub-example line stands against the text edge "
                   f"next to its letter, not at the far margin: "
                   f"{max(w.x1 for w in sub_text):.2f} vs {R - d_sub:.2f}"))
    enlab = [w for w in sub_line if w.x0 >= R - d_sub - TOL]
    r.append(check(bool(enlab) and abs(max(w.x1 for w in enlab)
                                       - (R - d_main)) < TOL,
                   f"its letter stands at the main text's edge: "
                   f"{[w.text for w in enlab]}"))
    visual = "".join(w.text for w in sorted(enlab, key=lambda w: w.x0))
    r.append(check(visual == ".a",
                   f"its letter reads in the DOCUMENT's direction, \".a\" "
                   f"as the Hebrew ones read \".א\": {visual!r}"))
    ensubb = p.find("ENSUBB")
    enstar = [w for w in p.line_of(ensubb) if "*" in w.text
              and w.x0 >= R - d_sub - TOL]
    r.append(check(gap is not None and bool(enstar)
                   and abs(enstar[0].x0 - (R - d_sub) - gap) < TOL,
                   f"its mark hangs to the right of the text: "
                   f"{[(w.text, round(w.x0, 2)) for w in enstar]}"))

    nt = p.find("ENNOTEXT")
    ntline = p.line_of(nt)
    r.append(check(abs(max(w.x1 for w in ntline) - R) < TOL,
                   f"an example with no text of its own has its number on its "
                   f"first sub-example's line, not alone above it: "
                   f"{[w.text for w in ntline]}"))

    # the braces: each one points AWAY from its stack, whichever side of
    # it the engine has put which word
    for a, b, what in (("STKA", "STKB", "an \\altn in Hebrew text"),
                       ("STKC", "STKD", "an \\altn in a line of Latin text"),
                       ("STKE", "STKF", "a solo \\altg")):
        rows = [p.find(a), p.find(b)]
        top, bot = min(w.y0 for w in rows), max(w.y1 for w in rows)
        mid = (top + bot) / 2
        band = [w for w in p.words if w not in rows
                and abs((w.y0 + w.y1) / 2 - mid) < 6]
        x0, x1 = min(w.x0 for w in rows), max(w.x1 for w in rows)
        lnb = max((w.x1 for w in band if w.x1 <= x0 + TOL), default=None)
        rnb = min((w.x0 for w in band if w.x0 >= x1 - TOL), default=None)
        if lnb is None or rnb is None:
            r.append(check(False, f"{what}: words on both sides of the "
                                  f"stack ({lnb}, {rnb})"))
            continue
        lb = brace_bulge(p.path, lnb, x0, top, bot)
        rb = brace_bulge(p.path, x1, rnb, top, bot)
        r.append(check(lb < -5.0 and rb > 5.0,
                       f"{what}: both braces point away from the stack "
                       f"(left tip - ends = {lb:.1f}px, want < -5; right "
                       f"{rb:.1f}px, want > +5)"))
    return r


def a_rtl_letters(p: Page):
    r"""Sub-example letters in a Hebrew document, the language's and then
    Latin through \Exalph; see the case's header."""
    r = []

    def label(tok):
        # the label stands to the RIGHT of its text in a right-to-left line;
        # strip the period, which either engine may put on either side
        w = p.find(tok)
        right = [t for t in p.line_of(w) if t.x0 >= w.x1 - TOL]
        return "".join(t.text for t in right).replace(".", "")

    def ref(tok):
        return "".join(t.text for t in p.line_of(p.find(tok))
                       if t.text != tok)

    for tok, want, why in (("HESUBA", "א", "the language's first letter"),
                           ("HESUBB", "ב", "... and its second"),
                           ("HESUBSUB", "i", "roman numerals stay Latin"),
                           ("LASUBA", "a", "\\ExLatinAlph: Latin a"),
                           ("LASUBB", "b", "... and b")):
        got = label(tok)
        r.append(check(got == want, f"{why}: {tok} is labelled {got!r}, "
                                    f"want {want!r}"))
    lab = [t for t in p.line_of(p.find("LASUBA"))
           if t.x0 >= p.find("LASUBA").x1 - TOL]
    visual = "".join(t.text for t in sorted(lab, key=lambda t: t.x0))
    r.append(check(visual == ".a",
                   f"a Latin letter in a Hebrew document reads in the "
                   f"document's direction, \".a\", the same under both "
                   f"engines: {visual!r}"))
    for tok, want, why in (("HEREF", "ב", "a reference prints the "
                                           "language's letter"),
                           ("LAREF", "2b", "... and the Latin one, after "
                                           "the switch")):
        got = ref(tok)
        r.append(check(want in got, f"{why}: {got!r}"))
    return r


def a_rtl_babel(p: Page):
    r"""Hebrew under babel: built, said once, the examples left alone.  See
    the case's header; the Hebrew example's own layout is not asserted."""
    r = []
    n = p.log.count("babel's right-to-left support is on")
    r.append(check(n == 1, f"one warning that right-to-left documents need "
                           f"polyglossia, got {n}"))
    r.append(check(any(w.text == "HEMAIN" for w in p.words),
                   "the Hebrew example is on the page"))
    mains = [p.find(t) for t in ("ENMAIN", "ENAFTER", "ENOBJ")]
    lefts = [min(w.x0 for w in p.line_of(t)) for t in mains]
    r.append(check(max(lefts) - min(lefts) < TOL
                   and max(t.x0 for t in mains) - min(t.x0 for t in mains)
                   < TOL,
                   f"every English example is numbered at the left margin "
                   f"with its text at one indent: numbers at "
                   f"{[round(x, 2) for x in lefts]}, text at "
                   f"{[round(t.x0, 2) for t in mains]}"))
    a, b = p.find("ENSUBA"), p.find("ENAFTERA")
    r.append(check(abs(a.x0 - b.x0) < TOL and a.x0 > mains[0].x0,
                   f"sub-examples before and after the Hebrew one at one "
                   f"indent: {a.x0:.2f} vs {b.x0:.2f}"))
    t = p.find("ENTRANS")
    r.append(check(abs(t.x0 - mains[2].x0) < TOL,
                   f"the translation starts under the gloss: {t.x0:.2f} vs "
                   f"{mains[2].x0:.2f}"))
    return r


def a_ltr_main(p: Page):
    r"""A Hebrew example in an English document is laid out as the English
    one is; see the case's header.  Distances from the English reference
    in the same file."""
    r = []
    ref = p.find("ENMAIN")
    L = min(w.x0 for w in p.line_of(ref))
    d_main = ref.x0 - L
    d_sub = p.find("ENSUBA").x0 - L
    ref_b = p.find("ENSUBB")
    ref_star = [w for w in p.left_of(ref_b) if w.text == "*"]
    gap = ref_b.x0 - ref_star[-1].x1 if ref_star else None

    for main, subs, what in (("HEMAIN", ("HESUBA", "HESUBB"), "dot syntax"),
                             ("GBMAIN", ("GBSUBA", "GBSUBB"), "gb4e, xlist")):
        m = p.find(main)
        line = p.line_of(m)
        # the example's own direction: its first word, a Latin sentinel,
        # stands at the RIGHT end of its right-to-left text, not the left
        for tok in (main,) + subs:
            t = p.find(tok)
            words = [w for w in p.line_of(t) if w.x0 >= L + d_sub - TOL
                     and w.text not in ("*",)]
            r.append(check(abs(t.x1 - max(w.x1 for w in words)) < TOL,
                           f"{what}: {tok}'s text runs right to left, its "
                           f"first word rightmost: {t.x1:.2f} vs "
                           f"{max(w.x1 for w in words):.2f}"))
        r.append(check(abs(min(w.x0 for w in line) - L) < TOL,
                       f"{what}: the Hebrew example is numbered at the LEFT "
                       f"margin: {min(w.x0 for w in line):.2f} vs {L:.2f}"))
        if main == "HEMAIN":
            below = p.find(subs[0]).y0
            lines = sorted({round(w.y0) for w in p.words
                            if m.y0 - 1 <= w.y0 < below - 1})
            last = [w for w in p.words if round(w.y0) == lines[-1]]
            r.append(check(len(lines) >= 2 and abs(min(w.x0 for w in last)
                                                   - (L + d_main)) < TOL,
                           f"{what}: a wrapped Hebrew example's short last "
                           f"line stands against the text edge, no space "
                           f"left before \\a. to push it off: "
                           f"{min(w.x0 for w in last):.2f} vs "
                           f"{L + d_main:.2f} ({len(lines)} lines)"))
        a, b = p.find(subs[0]), p.find(subs[1])
        aline = p.line_of(a)
        text = [w for w in aline if w.x0 >= L + d_sub - TOL]
        lab = [w for w in aline if w.x1 <= L + d_sub + TOL]
        r.append(check(abs(min(w.x0 for w in text) - (L + d_sub)) < TOL,
                       f"{what}: a short Hebrew sub-example line stands "
                       f"against the text edge next to its letter: "
                       f"{min(w.x0 for w in text):.2f} vs {L + d_sub:.2f}"))
        r.append(check(bool(lab) and abs(min(w.x0 for w in lab)
                                         - (L + d_main)) < TOL,
                       f"{what}: its letter stands at the main text's edge: "
                       f"{[w.text for w in lab]}"))
        visual = "".join(w.text for w in sorted(lab, key=lambda w: w.x0))
        r.append(check(visual == "א.",
                       f"{what}: its letter reads in the DOCUMENT's "
                       f"direction, \"א.\" as the English ones read "
                       f"\"a.\": {visual!r}"))
        bline = p.line_of(b)
        star = [w for w in bline if "*" in w.text and w.x1 <= L + d_sub + TOL]
        btext = min(w.x0 for w in bline if w.x0 >= L + d_sub - TOL)
        r.append(check(gap is not None and bool(star)
                       and abs(btext - star[-1].x1 - gap) < TOL,
                       f"{what}: the mark hangs left of the text, as in the "
                       f"reference: {[(w.text, round(w.x1, 2)) for w in star]}"
                       f" text at {btext:.2f}, gap {gap}"))
    return r


def _hebrew_reads(p, x0, x1, y0, y1, want):
    """Whether the Hebrew between x0..x1 on the band y0..y1 reads `want`.

    The page is read, not the text layer's word: LuaTeX gives a glyph per
    word box and XeTeX the whole word in visual order, so the glyphs are put
    in VISUAL order, left to right, and reversed -- which is the reading
    order of right-to-left text that is set right.  A word set letter by
    letter backwards fills the same box and reads `want` reversed."""
    glyphs = sorted((w for w in p.words
                     if w.x0 >= x0 - TOL and w.x1 <= x1 + TOL
                     and w.y0 >= y0 - TOL and w.y1 <= y1 + TOL),
                    key=lambda w: w.x0)
    visual = "".join(w.text for w in glyphs)
    return visual[::-1] == want, visual[::-1]


def _wrapped_lines(p, prefix):
    """The rendered lines a long grid's sentinel tier runs over."""
    ws = [w for w in p.words if re.fullmatch(prefix + r"[A-Z]{1,2}", w.text)]
    ys = sorted({round(w.y0) for w in ws})
    return [[w for w in ws if round(w.y0) == y] for y in ys]


def a_rtl_gloss(p: Page):
    r"""Glosses in a right-to-left document; see the case's header."""
    r = []
    ref = p.find("PLAINREF")
    R = max(w.x1 for w in p.line_of(ref))
    L = p.width - R
    edge = ref.x1                      # where the text of an example starts
    # a Hebrew example: right-to-left grid against the text edge
    a, b, c = p.find("HGA"), p.find("HGB"), p.find("HGC")
    r.append(check(abs(max(w.x1 for w in p.line_of(p.find("HGA"))
                           if w.x1 <= edge + TOL) - edge) < TOL
                   and a.x0 > b.x0 > c.x0,
                   f"a Hebrew grid runs from the right, its first column "
                   f"against the text edge ({a.x1:.2f}..; edge {edge:.2f})"))
    num = [w for w in p.words if abs(w.y0 - a.y0) < 20 and w.x1 > R - TOL]
    r.append(check(bool(num),
                   f"... and its number stands at the right margin ({R:.2f})"))
    rl = _wrapped_lines(p, "RL")
    r.append(check(len(rl) >= 2 and all(abs(max(w.x1 for w in ln) - edge)
                                        < TOL for ln in rl),
                   f"a long Hebrew grid: every line ends at the text edge, "
                   f"ragged on the left: "
                   f"{[round(max(w.x1 for w in ln), 2) for ln in rl]}"))
    # an English example: the mirror of \GlossRTL
    ea, eb, ec = p.find("ENA"), p.find("ENB"), p.find("ENC")
    row = [w for w in p.words if 4 < w.y0 - ea.y0 < 20
           and w.x0 >= ea.x0 - TOL and w.x1 <= edge + TOL]
    grid_right = max([ec.x1] + [w.x1 for w in row])
    r.append(check(ea.x0 < eb.x0 < ec.x0 and abs(grid_right - edge) < TOL,
                   f"an English grid runs from the left and, being short, "
                   f"stands beside its number against the text edge: "
                   f"{ea.x0:.2f}..{grid_right:.2f} vs edge {edge:.2f}"))
    for obj, want in ((ea, "הילד"), (eb, "אכל"), (ec, "את")):
        nxt = [o.x0 for o in (ea, eb, ec) if o.x0 > obj.x0]
        right = min(nxt) - TOL if nxt else edge + TOL
        ok, got = _hebrew_reads(p, obj.x0, right, obj.y1, obj.y1 + 14, want)
        r.append(check(ok, f"the Hebrew gloss under {obj.text} is {want!r} "
                           f"and reads right to left: {got!r}"))
    # its translation: the document's language, right to left, at the edge
    gl_bottom = max(w.y1 for w in p.words if 4 < w.y0 - ea.y0 < 20)
    tband = [w for w in p.words if 2 < w.y0 - gl_bottom < 16
             and w.x1 <= edge + TOL]
    ok, got = _hebrew_reads(p, min((w.x0 for w in tband), default=0), edge,
                            gl_bottom + 2, gl_bottom + 18, "")
    words = got.replace("’", "").replace("'", "").replace(".", "")
    r.append(check(bool(tband) and abs(max(w.x1 for w in tband) - edge)
                   < TOL and words.strip() == "הילדים אכלו".replace(" ", ""),
                   f"its translation is in the document's direction: Hebrew "
                   f"reading right to left, against the text edge: "
                   f"{got!r} ending at "
                   f"{max((w.x1 for w in tband), default=0):.2f} vs {edge:.2f}"))
    lw = _wrapped_lines(p, "LW")
    r.append(check(len(lw) >= 2 and all(abs(min(w.x0 for w in ln) - L) < TOL
                                        for ln in lw),
                   f"a long English grid: every line starts at the left "
                   f"margin, as \\GlossRTL's end at the right: "
                   f"{[round(min(w.x0 for w in ln), 2) for ln in lw]}"))
    return r


def a_ltr_gloss(p: Page):
    r"""Hebrew glossed in an English document; see the case's header."""
    r = []
    ref = p.find("ENREF")
    L = min(w.x0 for w in p.line_of(ref))
    R = p.width - L
    edge = ref.x0
    a, b, c = p.find("HGA"), p.find("HGB"), p.find("HGC")
    r.append(check(abs(c.x0 - edge) < 3 and a.x0 > b.x0 > c.x0,
                   f"a short Hebrew grid stands beside its number, running "
                   f"from the right: {c.x0:.2f} vs edge {edge:.2f}"))
    for gl, want in ((a, "הילד"), (b, "אכל"), (c, "את")):
        ok, got = _hebrew_reads(p, gl.x0 - 25, gl.x1 + 25, gl.y0 - 16,
                                gl.y0 - 1, want)
        r.append(check(ok or want in got,
                       f"the Hebrew over {gl.text} reads {want!r}, right to "
                       f"left: {got!r}"))
    rl = _wrapped_lines(p, "RL")
    r.append(check(len(rl) >= 2 and all(abs(max(w.x1 for w in ln) - R)
                                        < TOL for ln in rl),
                   f"a long Hebrew grid: every line ends at the right margin: "
                   f"{[round(max(w.x1 for w in ln), 2) for ln in rl]}"))
    return r


def a_commongloss_exe_ua(p: Page):
    r"""\begin{xlist}[CommonGloss] against the dot syntax; see the case.

    Page 1 is the dot form, page 2 the exe form of the same examples.  The
    exe form is held to the dot form's layout and tree, which
    a_commongloss_ua pins in detail, rather than to a second copy of those
    assertions."""
    r = []
    # every word at the same place on both pages: pdftotext merges the
    # pages, so each (text, x, y) must occur an even number of times
    ordinary = {round(w.y0, 1) for name in ("XORDA", "XORDB", "XORDHEAD")
                for w in [p.find(name)]}
    skip = re.compile(r"^(\(\d+[a-z]?\)\.?|FORM(DOT|EXE)|(DOT|EXE)REFS)$")
    seen = {}
    for w in p.words:
        if skip.match(w.text) or round(w.y0, 1) in ordinary:
            continue
        key = (w.text, round(w.x0, 1), round(w.y0, 1))
        seen[key] = seen.get(key, 0) + 1
    odd = sorted(k for k, n in seen.items() if n % 2)
    r.append(check(len(seen) > 40 and not odd,
                   f"the exe form sets every word where the dot form does "
                   f"({len(seen)} placed words; unpaired: {odd[:8]})"))
    # (2) the head-less number on row a's line, on page 2 too
    nums = [t.text for w in p.find_all("HLA2")[1:2] for t in p.line_of(w)]
    r.append(check("(5)" in nums,
                   f"head-less exe form: (5) is on row a's line ({nums})"))
    # (4) the ordinary xlist after it is lettered and laid out as ever
    # (the letters and text where the dot form's ordinary sub-examples
    # put theirs: "ev" is row a's first cell in (3), at the sub-level text
    # edge, and its "a." the letter)
    xa, xb = p.find("XORDA"), p.find("XORDB")
    la = p.left_of(xa)
    ev = p.find_all("ev")[0]
    lev = [t for t in p.left_of(ev) if t.text == "a."]
    r.append(check([t.text for t in la] == ["a."] and bool(lev)
                   and abs(la[0].x0 - lev[0].x0) < TOL
                   and xb.y0 > xa.y0,
                   f"an ordinary xlist after the table: lettered a. at the "
                   f"sub-level ({[(t.text, round(t.x0, 2)) for t in la]}, "
                   f"table's a. at {lev and round(lev[0].x0, 2)})"))
    refs = [t.text.rstrip(".") for t in p.line_of(p.find("EXEREFS"))]
    r.append(check("(4b)" in refs,
                   f"a \\label on an exe row resolves to (4b): {refs}"))

    # the tree: the halves' Tables identical in everything but their ids
    root = show_pdf_tags_xml(p.path)

    def local(el):
        return el.tag.rsplit("}", 1)[-1]

    def sig(el):
        attrs = tuple(sorted((k.rsplit("}", 1)[-1], v)
                             for k, v in el.attrib.items() if k != "id"))
        return (local(el), attrs, " ".join((el.text or "").split()),
                tuple(sig(c) for c in el))

    tables = [el for el in root.iter() if local(el) == "Table"]
    r.append(check(len(tables) == 6,
                   f"one Table per shared gloss, both forms: {len(tables)} of 6"))
    for i in range(min(3, len(tables) // 2)):
        r.append(check(sig(tables[i]) == sig(tables[i + 3]),
                       f"Table {i + 1}: the exe form's tree is the dot "
                       f"form's (tags, scope, language, text, spoken forms)"))
    alts = struct_alts(getattr(p, "raw", b""))
    for phrase, n in (("acceptable", 2), ("obligatory", 2),
                      ("questionable", 2)):
        r.append(check(alts.count(phrase) == n,
                       f"spoken {phrase!r} {n} time(s): {alts.count(phrase)} "
                       f"({alts})"))
    r.append(verapdf_compliant(p.path))
    depths = struct_lbl_depths(p.path)
    r.append(check(len(depths) == 7 and len({d for _, d in depths}) == 1,
                   f"every example number at one depth: {depths}"))
    empty = struct_empty_alts(p.path)
    r.append(check(not empty, f"no /Alt wraps nothing: {empty}"))
    return r


def a_commongloss_ua(p: Page):
    r"""\CommonGloss: variant rows sharing gloss lines; see the case's header.

    Geometry first (columns, judgments, annotations, phantom and morpheme
    alignment, the head-less number, the rebinding undone), then the TABLE
    the tagged PDF must carry -- read with show-pdf-tags, the way a
    consumer resolves it -- and veraPDF on top."""
    r = []
    label = re.compile(r"^(\(\w+\)|[a-f]\.|[ivx]+\.)$")

    def first_x(sentinel):
        toks = [t for t in p.line_of(p.find(sentinel))
                if not label.match(t.text)]
        return min(t.x0 for t in toks)

    # (1) every column one x, across the variant rows and the shared lines
    cols = {1: ["CA1", "G11", "G21"],
            2: ["CA2", "CB2", "G12", "G22"],
            3: ["CA3", "CB3", "CC3", "G13", "G23"],
            4: ["CA4", "CB4", "CC4", "G14", "G24"],
            5: ["CB5", "CC5", "G15"],
            6: ["CA6", "CB6", "CC6"]}
    for k, words in cols.items():
        xs = [p.find(w).x0 for w in words]
        r.append(check(max(xs) - min(xs) < TOL,
                       f"column {k} starts at one x in every row: "
                       f"{dict(zip(words, (round(x, 2) for x in xs)))}"))
    # the "(" of row c's first cell stays with its word, in column 1
    cc1 = p.find("CC1")
    r.append(check(cc1.text.startswith("(") and abs(cc1.x0 - p.find("CA1").x0) < TOL,
                   f"*(: the parenthesis stays in column 1 ({cc1.text!r} at "
                   f"{cc1.x0:.2f})"))
    # annotations: one column, right of the table
    ann = [p.find(w) for w in ("ANNA", "ANNB", "ANNC")]
    r.append(check(max(a.x0 for a in ann) - min(a.x0 for a in ann) < TOL
                   and ann[0].x0 > p.find("CA6").x1 + 1.0,
                   f"the annotations form one column right of the table "
                   f"({[round(a.x0, 2) for a in ann]}, table ends "
                   f"{p.find('CA6').x1:.2f})"))
    # judgments hang at the label exactly as an ordinary sub-example's do,
    # and the first column starts at the sub-example's text edge
    for row, ref, what in (("CA1", "RA1", "\\ok"), ("CB2", "RA1", "\\ok on a row "
                           "that opens with a gap"), ("CC3", "RB1", "*(")):
        x, xr = first_x(row), first_x(ref)
        r.append(check(abs(x - xr) < TOL,
                       f"{what}: the mark sits where an ordinary "
                       f"sub-example's does ({x:.2f} vs {xr:.2f})"))
    r.append(check(abs(p.find("CA1").x0 - p.find("RA1").x0) < TOL,
                   f"column 1 starts at the sub-example text edge "
                   f"({p.find('CA1').x0:.2f} vs {p.find('RA1').x0:.2f})"))
    # (3) no head line: the number stands on row a's line
    toks = [t.text for t in p.line_of(p.find("HLA"))]
    r.append(check("(3)" in toks,
                   f"head-less: the number is on row a's line ({toks})"))
    # (4) phantom: the column's real glyphs start past the widest bracket
    pha, pgx = p.find("[PHA"), p.find("PGX")
    shift = pgx.x0 - pha.x0
    r.append(check(shift > 1.0,
                   f"phantom: the shared line starts past row a's bracket "
                   f"(shift {shift:.2f})"))
    phy, phz, pgy = p.find("PHY"), p.find("[PHZ"), p.find("PGY")
    r.append(check(abs(phy.x0 - pgy.x0) < TOL
                   and abs(phz.x0 + shift - phy.x0) < TOL,
                   f"phantom: a row without the bracket lines up with the "
                   f"letter after another row's ({phy.x0:.2f}, "
                   f"{phz.x0:.2f}+{shift:.2f}, {pgy.x0:.2f})"))
    # (5) morphemes: morpheme 2 starts at one x in every segmented row
    lera, plz = p.find("-lerA"), p.find("-plZ")
    r.append(check(abs(lera.x0 - plz.x0) < TOL,
                   f"morphemes: -lerA and -plZ start at one x "
                   f"({lera.x0:.2f} vs {plz.x0:.2f})"))
    r.append(check("morphemes, which do not match" not in p.log,
                   "morphemes: no mismatch reported for matching rows"))
    # (6) the rebinding ended with its example: \ag. reads its gloss again
    una, ung = p.find("UNA"), p.find("UNG")
    r.append(check(abs(una.x0 - ung.x0) < TOL and ung.y0 > una.y0,
                   f"after the table \\ag. has its own gloss line again "
                   f"(UNG at {ung.x0:.2f},{ung.y0:.2f} under UNA at "
                   f"{una.x0:.2f},{una.y0:.2f})"))
    refs = [t.text for t in p.line_of(p.find("CGREFS"))]
    r.append(check("(1b)" in refs,
                   f"a \\label on a variant row resolves to (1b): {refs}"))

    # the tree: a Table per shared gloss, row headers, languages
    root = show_pdf_tags_xml(p.path)

    def local(el):
        return el.tag.rsplit("}", 1)[-1]

    def text(el):
        return "".join(el.itertext()).strip()

    tables = [el for el in root.iter() if local(el) == "Table"]
    r.append(check(len(tables) == 4,
                   f"one Table per shared gloss: {len(tables)} of 4"))
    if tables:
        trs = [el for el in tables[0] if local(el) == "TR"]
        r.append(check(len(trs) == 5,
                       f"example (1) has five rows: {len(trs)}"))
        scope = "{http://iso.org/pdf/ssn/Table}Scope"
        for i, tr in enumerate(trs[:5]):
            cells = [el for el in tr if local(el) in ("TH", "TD")]
            head = cells[0] if cells else None
            got = head is not None and (local(head), head.get(scope),
                                        text(head))
            if i < 3:
                r.append(check(head is not None and local(head) == "TH"
                               and head.get(scope) == "Row"
                               and text(head).startswith("abc"[i] + "."),
                               f"row {i + 1} opens with a row header TH "
                               f"/Scope /Row reading {'abc'[i]}.: {got}"))
                langs = {c.get("lang") for c in cells[1:-1]}
                r.append(check(langs == {"ht"},
                               f"row {i + 1}: its cells are in the object "
                               f"language: {langs}"))
            else:
                r.append(check(head is not None and local(head) == "TD"
                               and not text(head),
                               f"shared line {i - 2} opens with an empty TD, "
                               f"no header: {got}"))
                langs = {c.get("lang") for c in cells[1:]}
                r.append(check(langs == {None},
                               f"shared line {i - 2}: no object language: "
                               f"{langs}"))
        first = [el for el in trs[0] if local(el) == "TD"][:1]
        r.append(check(bool(first) and text(first[0]) == "CA1",
                       f"the judgment is in the header, not the first cell: "
                       f"{first and text(first[0])!r}"))
    alts = struct_alts(getattr(p, "raw", b""))
    for phrase, n in (("acceptable", 3), ("obligatory", 1),
                      ("ungrammatical", 1)):
        r.append(check(alts.count(phrase) == n,
                       f"spoken {phrase!r} {n} time(s): {alts.count(phrase)} "
                       f"({alts})"))
    r.append(verapdf_compliant(p.path))
    depths = struct_lbl_depths(p.path)
    r.append(check(len(depths) == 6 and len({d for _, d in depths}) == 1,
                   f"every example number at one depth: {depths}"))
    empty = struct_empty_alts(p.path)
    r.append(check(not empty, f"no /Alt wraps nothing: {empty}"))
    return r


# ---- \CommonGloss and direction, \CommonGloss and \pause -------------------

def _right_of(p: Page, word):
    """The words on `word`'s line that start at or after its right edge."""
    return [w for w in p.line_of(word) if w is not word and w.x0 >= word.x1 - TOL]


def _by_y(p: Page, text):
    """Every word reading exactly `text`, top to bottom."""
    return sorted((w for w in p.words if w.text == text), key=lambda w: w.y0)


def a_commongloss_rtl(p: Page):
    r"""\CommonGloss in a right-to-left document; see the case's header.
    Every position is read off an ordinary gloss in the same file."""
    r = []
    # (1)/(2): a Hebrew table on the columns of the ordinary gloss
    for g in ("RG1", "RG2", "RG3"):
        ws = _by_y(p, g)
        r.append(check(len(ws) == 3 and max(w.x0 for w in ws)
                       - min(w.x0 for w in ws) < TOL,
                       f"{g}: the table's column is the ordinary gloss's "
                       f"({[round(w.x0, 2) for w in ws]})"))
    g1, g2, g3 = (_by_y(p, g)[0] for g in ("RG1", "RG2", "RG3"))
    r.append(check(g1.x0 > g2.x0 > g3.x0,
                   f"the columns run from the right: RG1 {g1.x0:.2f}, "
                   f"RG2 {g2.x0:.2f}, RG3 {g3.x0:.2f}"))
    stars = _by_y(p, "*")
    r.append(check(len(stars) == 4 and max(s.x0 for s in stars)
                   - min(s.x0 for s in stars) < TOL,
                   f"every mark hangs from the letters' column, where an "
                   f"ordinary sub-example's does -- the English table's too, "
                   f"its frame being the document's "
                   f"({[round(s.x0, 2) for s in stars]})"))
    anns = _by_y(p, "ANN")
    r.append(check(len(anns) == 3 and max(a.x0 for a in anns)
                   - min(a.x0 for a in anns) < TOL,
                   f"every annotation in one mirrored column "
                   f"({[round(a.x0, 2) for a in anns]})"))
    r.append(check(bool(anns) and anns[0].x1 < g3.x0,
                   f"... on the left, past the grid ({anns[0].x1:.2f} < "
                   f"{g3.x0:.2f})" if anns else "no annotation found"))
    # (3)/(4): an English table, columns from the left, letters on the right
    ea1, ea2, ea3 = (_by_y(p, w) for w in ("EA1", "EA2", "EA3"))
    r.append(check(len(ea1) == 2 and len(ea2) == 3 and len(ea3) == 3,
                   f"the English words are all found: {ea1}, {ea2}, {ea3}"))
    if len(ea1) == 2 and len(ea2) == 3 and len(ea3) == 3:
        t1, t2, t3 = ea1[0], ea2[0], ea3[0]
        r.append(check(t1.x0 < t2.x0 < t3.x0,
                       f"its columns run left to right: EA1 {t1.x0:.2f}, "
                       f"EA2 {t2.x0:.2f}, EA3 {t3.x0:.2f}"))
        for name, t, ref in (("EA1", t1, ea1[1]), ("EA2", t2, ea2[2]),
                             ("EA3", t3, ea3[2])):
            r.append(check(abs(t.x0 - ref.x0) < TOL,
                           f"{name} stands where the ordinary gloss puts it "
                           f"({t.x0:.2f} vs {ref.x0:.2f})"))
        lab, labref = _right_of(p, t3), _right_of(p, ea3[2])
        r.append(check(bool(lab) and bool(labref)
                       and abs(max(w.x1 for w in lab)
                               - max(w.x1 for w in labref)) < TOL,
                       f"its letter is on the right, where the ordinary "
                       f"gloss's is ({lab} vs {labref})"))
        eg = _by_y(p, "eg1")
        r.append(check(len(eg) == 2 and abs(eg[0].x0 - t1.x0) < TOL,
                       f"its gloss starts under its first word "
                       f"({eg and eg[0].x0} vs {t1.x0:.2f})"))
    # (5): no head line, the number on row a's line
    toks = [w.text for w in p.line_of(p.find("NHA"))]
    r.append(check("(5)" in toks or "5" in toks,
                   f"head-less: the number is on row a's line ({toks})"))
    n1, n2, n3 = (p.find(g) for g in ("NG1", "NG2", "NG3"))
    r.append(check(n1.x0 > n2.x0 > n3.x0,
                   f"head-less: its columns run from the right too "
                   f"({n1.x0:.2f}, {n2.x0:.2f}, {n3.x0:.2f})"))
    return r


def _cg_tables(path):
    """Each Table of the tag tree as its rows, each row as (tag, text)."""
    root = show_pdf_tags_xml(path)

    def local(el):
        return el.tag.rsplit("}", 1)[-1]

    return [[[(local(c), "".join(c.itertext()).strip()) for c in tr
              if local(c) in ("TH", "TD")]
             for tr in t if local(tr) == "TR"]
            for t in root.iter() if local(t) == "Table"]


def _cg_tree_checks(p: Page, expect):
    """The tables' trees read in logical order: `expect` is, per table, its
    first row's first cell and its shared line's first cell."""
    r = []
    tables = _cg_tables(p.path)
    r.append(check(len(tables) == len(expect),
                   f"one Table per shared gloss: {len(tables)} of {len(expect)}"))
    for i, (tbl, (first, shared)) in enumerate(zip(tables, expect)):
        rows = [row for row in tbl if row]
        ok = (len(rows) == 3 and rows[0][0][0] == "TH"
              and rows[0][1] == ("TD", first)
              and rows[2][0] == ("TD", "") and rows[2][1] == ("TD", shared))
        r.append(check(ok, f"table {i + 1} reads row a from its letter and "
                           f"then its FIRST word {first!r}, the shared line "
                           f"from {shared!r}: {rows}"))
        r.append(check(len(rows) > 1 and "*" in rows[1][0][1]
                       and rows[1][0][0] == "TH",
                       f"table {i + 1}: row b's judgment is in its header: "
                       f"{rows[1][0] if len(rows) > 1 else None}"))
    alts = struct_alts(getattr(p, "raw", b""))
    r.append(check(alts.count("ungrammatical") == len(expect),
                   f"each mark spoken: {alts}"))
    r.append(verapdf_compliant(p.path))
    depths = struct_lbl_depths(p.path)
    r.append(check(bool(depths) and len({d for _, d in depths}) == 1,
                   f"every example number found at one depth: {depths}"))
    empty = struct_empty_alts(p.path)
    r.append(check(not empty, f"no /Alt wraps nothing: {empty}"))
    return r


def a_commongloss_rtl_ua(p: Page):
    r"""\CommonGloss tagged in a right-to-left document; see the header."""
    return _cg_tree_checks(p, [("א", "RG1"), ("EA1", "א")])


def a_commongloss_ltr_ua(p: Page):
    r"""A Hebrew example's \CommonGloss in an English document: columns
    from the right, in the frame of the English one above it."""
    r = []
    lg = {g: _by_y(p, g) for g in ("lg1", "lg2", "lg3")}
    r.append(check(all(len(v) == 2 for v in lg.values()),
                   f"both tables' glosses found: {lg}"))
    if all(len(v) == 2 for v in lg.values()):
        en = [lg[g][0] for g in ("lg1", "lg2", "lg3")]
        he = [lg[g][1] for g in ("lg1", "lg2", "lg3")]
        r.append(check(en[0].x0 < en[1].x0 < en[2].x0,
                       f"the reference runs left to right "
                       f"({[round(w.x0, 2) for w in en]})"))
        r.append(check(he[0].x0 > he[1].x0 > he[2].x0,
                       f"the Hebrew example's columns run from the right "
                       f"({[round(w.x0, 2) for w in he]})"))
        r.append(check(abs(min(w.x0 for w in he) - en[0].x0) < TOL,
                       f"... in a grid that starts where the reference's "
                       f"does, beside its letter "
                       f"({min(w.x0 for w in he):.2f} vs {en[0].x0:.2f})"))
    stars, anns = _by_y(p, "*"), _by_y(p, "ANN")
    r.append(check(len(stars) == 2 and abs(stars[0].x0 - stars[1].x0) < TOL,
                   f"its mark hangs at the letter, where the reference's "
                   f"does ({stars})"))
    r.append(check(len(anns) == 2 and abs(anns[0].x0 - anns[1].x0) < TOL,
                   f"its annotation is in the reference's column ({anns})"))
    r += _cg_tree_checks(p, [("LA1", "lg1"), ("א", "lg1")])
    return r


def a_commongloss_beamer(p: Page):
    r"""\CommonGloss with \pause; see the case's header."""
    r = []
    pages = slides(p.path)
    r.append(check(len(pages) == 11,
                   f"P1 3 slides, P2 2, P3 3, P4 2, P5 1: {len(pages)}"))
    if len(pages) != 11:
        return r

    def on(i):
        return {w.text for w in pages[i]}

    def has(i, *ws):
        return all(w in on(i) for w in ws)

    def lacks(i, *ws):
        return not any(w in on(i) for w in ws)

    # P1: a | b | c, the shared line from the first slide
    r.append(check(has(0, "PA1", "PG1", "PANN") and lacks(0, "PB3", "PC1"),
                   f"P1 slide 1: row a and the shared line only: {sorted(on(0))}"))
    r.append(check(has(1, "PA1", "PB3", "PG1") and lacks(1, "PC1", "‘PTRANS’"),
                   f"P1 slide 2: row b added: {sorted(on(1))}"))
    r.append(check(has(2, "PA1", "PB3", "PC1", "PG1")
                   and any("PTRANS" in w for w in on(2)),
                   f"P1 slide 3: row c and the translation: {sorted(on(2))}"))
    # P2: a \pause among the shared lines delays only what follows it
    r.append(check(has(3, "QA1", "QB1", "QG1") and lacks(3, "QH1"),
                   f"P2 slide 1: rows and first shared line: {sorted(on(3))}"))
    r.append(check(has(4, "QH1"), f"P2 slide 2: second shared line: {sorted(on(4))}"))
    # P3: the exe form, after an earlier \pause
    r.append(check(has(5, "SBEFORE") and lacks(5, "SA1", "SG1"),
                   f"P3 slide 1: only what precedes the \\pause: {sorted(on(5))}"))
    r.append(check(has(6, "SA1", "SG1") and lacks(6, "SB1"),
                   f"P3 slide 2: row a and its gloss: {sorted(on(6))}"))
    r.append(check(has(7, "SB1"), f"P3 slide 3: row b: {sorted(on(7))}"))
    # P4: no head line -- the number on row a's line on both slides
    for i in (8, 9):
        ta = [w for w in pages[i] if w.text == "TA1"]
        num = [w for w in pages[i] if w.text in ("(4)", "4")]
        r.append(check(bool(ta) and bool(num) and abs(ta[0].y0 - num[0].y0) < TOL,
                       f"P4 slide {i - 7}: the number on row a's line "
                       f"({num}, {ta})"))
    # every word of a table at one place on every slide it is on
    for frame in ((0, 1, 2), (3, 4), (5, 6, 7), (8, 9)):
        seen, moved = {}, []
        for i in frame:
            for w in pages[i]:
                if w.text in seen and (abs(seen[w.text][0] - w.x0) > TOL
                                       or abs(seen[w.text][1] - w.y0) > TOL):
                    moved.append((w.text, seen[w.text], (w.x0, w.y0)))
                seen.setdefault(w.text, (w.x0, w.y0))
        r.append(check(not moved, f"frame of slides {frame}: nothing moves "
                                  f"from slide to slide: {moved}"))
    # P1's last slide is P5, the same frame without \pause, word for word
    def body(i):
        return sorted((w.text, round(w.x0, 1), round(w.y0, 1))
                      for w in pages[i] if w.text not in ("P1", "P5", "(1)",
                                                          "(5)", "1", "5"))
    r.append(check(body(2) == body(10),
                   f"P1's last slide is the frame without \\pause: "
                   f"{set(body(2)) ^ set(body(10))}"))
    return r
