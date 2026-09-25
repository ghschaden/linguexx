#!/usr/bin/env python3
r"""
linguexx regression suite.

Compiles every case in cases/ under every engine and checks assertions
against the RENDERED GEOMETRY of the resulting PDF, not merely against the
exit status.  This matters: every real bug found during development of this
package compiled with zero errors and was visible only in the coordinates
(a judgment mark that failed to hang left, a source that fell flush left
instead of flush right, a \z. that popped the wrong number of levels).

Adding a case: drop <name>.tex in this directory AND add a <name> entry to
ASSERTIONS, which lives in suite/assertions/__init__.py beside the grouped
modules holding the functions themselves.  Only what ASSERTIONS lists is
ever run, so a case file without an entry is dead weight; the suite refuses
to run until every case file is either wired up or declared SMOKE_ONLY (see
suite_integrity).

Layout: this file is the entry point and the facade -- the runner, the
registries of engines and passes, the integrity checks, and main().  The
bulk is in suite/: pdf.py (words and boxes), geometry.py (measured ink),
structure.py (the tag tree and veraPDF), check.py (the assertion protocol)
and assertions/ (the functions, grouped by what they are about).  It is
imported by path as well as run as a script, so it re-exports what
.claude/tools/lxx reads off it; see the note at the import block.

Beyond the cases there are the DOCUMENTS: the manual and the shipped
examples, which are not test cases and still have to build.  --documents
builds them and validates examples/ua-demo.pdf with veraPDF, which is the
pre-delivery gate of CLAUDE.md -- and which, until that flag existed, only
ever ran on the author's machine.  It is opt-in because the manual costs
about a minute; CI passes it, and tooling_integrity checks that CI still
does.

Usage:
    python3 runtests.py                  # all cases, all engines
    python3 runtests.py -e pdflatex      # one engine
    python3 runtests.py -k gloss         # cases matching a substring
    python3 runtests.py -v               # show every assertion, not just failures
    python3 runtests.py -j1              # one case at a time (default: DEFAULT_JOBS)
    python3 runtests.py --documents      # ... and the manual and the examples

Requires: pdflatex / xelatex / lualatex, pdftotext and pdfinfo
(poppler-utils), qpdf (to resolve a named destination to the page it lands
on, which no poppler tool reports), show-pdf-tags (the LaTeX team's own tag
viewer, TeX Live package of that name: it resolves /K the way a consumer
does, which is what sees an /Alt wrapping nothing), and veraPDF on PATH as
`verapdf` -- the only authoritative oracle for PDF/UA, used by the `ua`
case.
That list is REQUIRED_TOOLS, and it is checked rather than described: the
suite refuses to start if a tool is missing from PATH, unnamed in this
paragraph, or not installed by either CI definition.  They used to be
kept in step by hand and were not.

Exit status: 0 iff every assertion passed, 1 on a failing assertion,
2 on a suite-integrity problem (an unwired case file, a missing case file,
a stale KNOWN_XFAIL or PASSES key, a required tool that PATH, this
docstring and the CI definitions do not agree about, a CI definition that
no longer runs --documents) or when no case matches -k.
"""

import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINES = ["pdflatex", "xelatex", "lualatex"]
# engine/case pairs whose failure is an artifact of the TOOLING rather than
# a defect in the package.  Empty, and worth keeping so.
#
# It held "pdflatex/judgment-align" from the initial commit: pdftotext used
# to merge the sub-example label with the judgment marks that follow it into
# a single token, and a_judgment_align cannot take such a token apart -- it
# reports "label and marks merged" -- although the geometry was right all
# along, which is why xelatex and lualatex always passed.  Poppler 26.07
# emits the label as its own token, so the case now passes on all three
# engines and the entry masked a green result instead of guarding anything.
#
# Removed rather than kept as insurance: an entry that never fires cannot be
# told apart from one that still protects something, which is how this one
# outlived its reason by a whole rewrite of the suite around it.  main() now
# reports that state -- an entry whose case ran and passed is a hard error,
# not a quiet XFAIL -- so the next one cannot rot the same way.  Should
# judgment-align ever fail on pdflatex ALONE with that message, this is the
# reason, and the answer is to measure the marks from ink (cf. brace_bulge)
# rather than to re-add a line that hides the assertion.
KNOWN_XFAIL = set()
# LaTeX passes per case; two is enough for cross-references, which is all
# most cases need.  The `ua` case needs three: its PDF/UA validity does not
# converge until the third run under pdflatex and xelatex (lualatex gets
# there in two), and a not-yet-converged file fails veraPDF on all three
# profiles -- which would look exactly like a tagging regression.
#: Per-pass wall clock for one engine run.  A TeX loop ignores
#: -interaction=nonstopmode and spins forever, so without a cap one bad case
#: hangs the whole suite rather than failing it.
CASE_TIMEOUT = 120
#: Cases compiled at once by default.  The CPU count was the obvious number
#: and is the wrong one: it counts SMT threads -- twelve on the six-core
#: machine this is developed on -- and every extra concurrent case widens a
#: race that is not this suite's to fix.  xdvipdfmx creates its temporary
#: file in $TMPDIR with mkstemp, then REOPENS IT BY NAME, and unlinks it by
#: name when it is done (strace: openat("/tmp/dvipdfmx.XXXXXX", O_EXCL),
#: openat(same path), unlink(same path)).  Two concurrent runs that draw
#: the same name inside that window remove each other's file, and the loser
#: dies with "xelatex: dvipdfmx.XXXXXX: No such file or directory": exit 1,
#: a log truncated at "(./case.tex", no TeX error, no signal, no coredump,
#: and the same directory rebuilding cleanly a second later.  That is
#: indistinguishable from a real regression except that it never reproduces
#: -- which is exactly how it wasted an afternoon.
#:
#: Measured: one failure in 600 runs of a single xelatex case at twelve,
#: none in 600 at six.  One in 600 sounds rare and is not: a full run
#: compiles well over a hundred xelatex documents, so it poisons something
#: like one run in five, which matches what was seen.  Six costs 10-15%
#: more wall clock (83-88s against 74-76s) and buys a result that can be
#: believed.  A pdflatex case failed the same way once and stayed
#: unexplained (zero in 600 targeted runs); that one is NOT this race.
#:
#: run_case now gives each case its own TMPDIR, which takes that shared
#: namespace away from the race entirely; six remains the default because
#: the oversubscription it fixes is real on its own -- a case is not one
#: process but a chain of them (the engine, then pdftotext, pdfinfo, qpdf, a
#: 300-600 dpi pdftoppm render, and for `ua` a JVM), and twelve of those
#: chains on six cores buys nothing.  Capped at the CPUs actually present:
#: CI runners have two or four, and six jobs there would re-create on the
#: runner exactly the oversubscription this number exists to avoid.
DEFAULT_JOBS = min(6, os.cpu_count() or 1)
#: Cases that only some engines can run.  Not a way to duck a failure: the
#: entry is for input pdflatex CANNOT REPRESENT AT ALL -- T1 has no slot for
#: a breve-below or a stacked Vietnamese vowel, and inputenc rejects it with
#: "Unicode character ... not set up for use with LaTeX".  Anything pdflatex
#: can typeset belongs in a case that runs everywhere.
ENGINES_FOR = {
    "utf8-unicode": ("xelatex", "lualatex"),
}
DEFAULT_PASSES = 2
PASSES = {"ua": 3, "frontend": 3, "langsci-ua": 3, "exannot-ua": 3,
          "exannot-fit": 2, "exannot-fitbody": 2,
          "exannot-beamer": 2}
#: Cases that must FAIL to compile, mapped to a substring their .log has to
#: contain.  A package error is as much a feature as a rendering is -- it is
#: what a silently wrong construct was turned into -- and without this it
#: would have no guard: delete the check in the .sty and every other case
#: stays green.  These have no assertion function; the raised error is the
#: assertion.
EXPECT_ERROR = {
    "altg-unpaired": "has no partner",
    # A package this one REPLACES, loaded alongside it.  Both orders: the
    # old \usepackage line left in front (clash-linguex) and a second
    # front-end pulled in behind (clash-after).  Without the check the
    # document compiles, because every one of these defines \ex with \def
    # and the file read second simply wins -- so nothing else in this suite
    # could see it.  clash-input.tex covers the third way in, which is not
    # an error and cannot be one.
    "clash-linguex": "is loaded as well as",
    "clash-after": "is loaded as well as",
    # The one-syntax-per-example rule, both directions and the stray.  Each
    # of these renders without complaint if its guard is removed, and each
    # renders something the writer did not ask for: a sub-level only the
    # forbidden \z. could close, a level opened inside a body that is still
    # being collected, and a list closed where none was open.
    "langsci-nomix": "inside an \\ea example",
    "langsci-eamix": "written in the other syntax",
    "langsci-strayz": "with no \\ea to close",
    "langsci-legacy": "cannot be combined",
    # A package option handed a value.  The options are switches, and the
    # kernel's key interface is what makes the opposite easy to reach by
    # accident: give one of them a non-empty .default:n, or drop
    # \lx@opt@bare, and [legacy=false] sets [legacy] rather than being
    # refused -- the value read as decoration.  Under \DeclareOption the
    # spelling was merely unknown and warned.
    "option-value": "takes no value",
    "langsci-unclosed": "was never closed",
    "langsci-exioutside": "outside an example",
    "langsci-easnest": "inside an example",
    "langsci-nojambox": "Undefined control sequence",
    "langsci-retired": "is not provided",
    "judgment-badarg": "needs one command here",
    "exannot-gloss": "belongs at the end of the OBJECT",
    "glt-side-sub": "for top-level examples only",
    "glt-side-annot": "cannot go on a gloss with a side",
    "straysub": "no example to attach it to",
    # Not a package error but TeX's own, and deliberately so: a dot-syntax
    # body is collected before it is typeset, so \verb cannot protect
    # anything in it and the "_" of the payload arrives as a subscript.
    # The manual documents that limitation; this pins it, and verb.tex
    # pins the environment syntax where \verb does work.
    "verb-dot": "Missing $ inserted",
    # The third cell of the same matrix, and the same error from the same
    # payload by a different route: \ex[j]{text} reads its body as a macro
    # argument, so the catcodes are fixed before the body is used exactly as
    # a collected one's are.  Separate from verb-dot because the route is:
    # this one sits under exe, where verb.tex shows an unbraced \ex handling
    # \verb fine, so the braced form is the only thing on trial.
    "verb-braced": "Missing $ inserted",
}
#: The external tools the suite runs on, and how CI is expected to provide
#: each one.  ONE list, checked three ways by suite_integrity: present on
#: PATH, named in this module's docstring, and installed by the workflow.
#:
#: It exists because the three drifted apart and only the slowest of them
#: noticed.  qpdf was added for the beamer overlay assertions and went into
#: the docstring and not into the workflow; every local run was green
#: (qpdf happens to be installed on the machine it was written on) and CI
#: died two minutes in on a FileNotFoundError from inside a helper, having
#: compiled everything and asserted almost nothing.  A requirement that
#: lives only in prose is a requirement nothing enforces.
#:
#: Fields: how the workflow provides it, whether its absence should stop
#: the suite before anything runs, and what it is for.
#:   "image"      -- comes with the texlive container; nothing to install
#:   "apt:<pkg>"  -- <pkg> must appear in the workflow's apt line
#:   "step:<name>" -- a workflow step of that name must exist
#: veraPDF is deliberately NOT a startup check: a_ua owns that message, and
#: a startup check here would make that branch unreachable dead code.
#: show-pdf-tags is here for the same reason and was missed for a week --
#: it became a hard requirement with struct_empty_alts, which raises
#: without it, and it reached CLAUDE.md and this table's absence instead.
#: It passed only because the texlive container ships it and the machine it
#: was written on had it installed, which is the qpdf story above, again.
REQUIRED_TOOLS = {
    "pdflatex":  ("image", False, "engine"),
    "xelatex":   ("image", False, "engine"),
    "lualatex":  ("image", False, "engine"),
    "pdftotext": ("apt:poppler-utils", True,
                  "word boxes: every geometric assertion reads them"),
    "pdfinfo":   ("apt:poppler-utils", True,
                  "the tagged structure tree"),
    "qpdf":      ("apt:qpdf", True,
                  "resolving a named destination to the page it lands on"),
    "verapdf":   ("step:Install veraPDF", False,
                  "the PDF/UA oracle, used by the `ua` case"),
    "show-pdf-tags": ("image", False,
                      "resolving /K the way a consumer does, which is what "
                      "sees an /Alt that wraps nothing"),
}
#: The CI definitions the tools above are checked against.  Absent from a
#: distribution tarball, where there is no CI to disagree with; the check
#: is about this repository, not about the package.
#:
#: The GitHub workflow is the reference -- REQUIRED_TOOLS cites its step
#: names.  The GitLab pipeline is checked for what generalises: the apt
#: packages, a tool proving it started with --version, and the suite
#: invocation.  Its own header records why it is checked at all: nothing
#: checked it, so it is the one that drifted, and it installed neither qpdf
#: nor veraPDF long after both had become requirements.
REPO = Path(__file__).parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
GITLAB_CI = REPO / ".gitlab-ci.yml"
CASES = Path(__file__).parent / "cases"
if not CASES.is_dir():                       # flat layout: cases beside the script
    CASES = Path(__file__).parent
STY = Path(__file__).parent / "linguexx.sty"
if not STY.exists():                          # repo layout: sty at the root
    STY = Path(__file__).parent.parent / "linguexx.sty"

sys.path.insert(0, str(Path(__file__).resolve().parent))
# After the sys.path line above, hence E402: runtests.py is loaded by PATH as
# well as run as a script (.claude/tools/lxx does the former, and gets no
# tests/ on sys.path for free), so the package has to be made findable first.
from suite.assertions import ASSERTIONS  # noqa: E402
from suite.check import check  # noqa: E402
from suite.pdf import (  # noqa: E402
    parse_pdf,
)
from suite.structure import (  # noqa: E402
    struct_empty_alts, struct_has_formula,
    struct_lbl_depths,
    verapdf_log_records, verapdf_report,
)
# Nothing in this file calls it, and it is still part of the contract:
# .claude/tools/lxx loads runtests.py BY PATH and reads struct_ol_classes
# off the module, along with the seven names above and below it.  An
# "unused import" here is a re-export, so `ruff --fix` removing it is a
# broken `lxx struct`, not a tidy-up -- which is exactly what happened
# during the split.
from suite.structure import struct_ol_classes  # noqa: E402,F401


#: Case files that are deliberately NOT assertion-driven: the two smoke
#: tests the Makefile builds under all three engines, whose only assertion
#: is that they compile.  Listed here so that the integrity check below can
#: tell them apart from a case file whose assertions were forgotten.
SMOKE_ONLY = {"linguexx-test", "linguexx-test-gb4e"}


# ---------------------------------------------------------------------------
#  Documents: the half of the gate that is not a test case
# ---------------------------------------------------------------------------

def d_ua_demo(pdf: Path):
    """The PDF/UA gate on the FULL accessible document.

    The `ua` case does not replace this one and was never meant to: it
    deliberately omits footnote examples (its header says so), and a
    footnote example is the construct whose structure is hardest to keep
    valid.  CLAUDE.md has therefore always required veraPDF on this file
    before delivering; what it could not require was that anything but the
    author's own machine ever ran it.

    Three oracles, because no one of them sees what the others do: the
    verdict; what veraPDF LOGGED while parsing, which it can do while still
    reporting compliant (verapdf_log_records); and the depth of the
    top-level numbers, which is the only one of the three that catches an
    element never closed -- that stays spec-valid and quietly adopts the
    rest of the document (struct_lbl_depths).
    """
    if not shutil.which("verapdf"):
        return [(False, "verapdf is not on PATH: the PDF/UA gate for the "
                        "accessible demo cannot run (it is the only "
                        "authoritative oracle for PDF/UA)")]
    verdicts, failures, raw = verapdf_report(pdf)
    if not verdicts:
        return [(False, f"veraPDF produced no verdict -- it is on PATH but "
                        f"could not report (broken install? missing JRE?). "
                        f"Its output was: {raw[:400]!r}")]
    r = [check(len(verdicts) >= 3,
               f"veraPDF reported on all its profiles (got {verdicts})")]
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
    depths = struct_lbl_depths(pdf)
    levels = {d for _, d in depths}
    r.append(check(len(depths) >= 8 and len(levels) == 1,
                   f"every top-level example number sits at one depth; "
                   f"got {depths}"))
    # \altn and \altg are text, not math: a Formula element in a PDF/UA-2
    # document needs an /Alt or a MathML association and this package has
    # neither to give.  Avoiding it is the whole point of the 0.12 rewrite.
    r.append(check(not struct_has_formula(pdf),
                   "no Formula element in the tree"))
    # The fourth oracle, and the one the other three cannot supply: an
    # element carrying a spoken /Alt that wraps nothing.  This document is
    # where it mattered -- 6 of its 12 /Alt elements were empty under
    # lualatex before 2026-09-17, with veraPDF compliant on all three
    # profiles and every depth assertion above satisfied.
    orphans = struct_empty_alts(pdf)
    r.append(check(not orphans,
                   f"every /Alt in the tree wraps content; these wrap "
                   f"nothing: {orphans}"))
    return r


#: The documents that are not test cases and still have to build, with the
#: engine each is built under, the passes it needs and anything to check
#: beyond the build itself.
#:
#: Building IS the assertion for three of them.  That is not a low bar: the
#: manual is the only document that exercises the package as a reader meets
#: it -- every option, both front-ends, the whole of the glossing code, over
#: 3000 lines -- and nothing in cases/ is remotely that long.
#:
#: One engine each, and deliberately not a matrix: the engine matrix belongs
#: to the cases, where `ua`, `langsci-ua`, `exannot-ua` and `tagged` run the
#: tagging under all three.  The manual builds under lualatex alone and
#: errors out under pdflatex on purpose (it documents, and contains, the
#: dot-below transliterations pdflatex gives a broken text layer).
#:
#: ua-demo gets three passes because PDF/UA validity needs a third one on
#: the engines that do not converge in two, and an unconverged file fails
#: veraPDF exactly like a real regression.  See PASSES for the same rule
#: applied to the cases.
DOCUMENTS = {
    "ua-demo": (REPO / "examples" / "ua-demo.tex", "lualatex", 3, d_ua_demo),
    "accessible-demo": (REPO / "examples" / "accessible-demo.tex",
                        "lualatex", 2, None),
    "altg-demo": (REPO / "examples" / "altg-demo.tex", "pdflatex", 2, None),
    "manual": (REPO / "linguexx-doc.tex", "lualatex", 3, None),
}


def run_document(name: str, outdir: Path = None):
    """Build one document and run whatever else it asks for.

    `outdir` keeps the build (and the PDF, at <outdir>/<stem>.pdf) instead
    of discarding it with a temporary directory: what the agent harness
    passes when the point of the run is to look at the result afterwards.
    """
    src, engine, passes, checker = DOCUMENTS[name]
    if not src.is_file():
        return [(False, f"MISSING DOCUMENT FILE: {src}")]
    if not shutil.which(engine):
        return [(False, f"{engine} is not installed, so {src.name} was "
                        f"not built")]
    tmpdir = None
    if outdir is None:
        tmpdir = tempfile.TemporaryDirectory()
        work = Path(tmpdir.name)
    else:
        work = outdir
        work.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy(src, work)
        shutil.copy(STY, work)
        env = dict(os.environ, TMPDIR=str(work))    # see DEFAULT_JOBS
        for _ in range(passes):
            try:
                proc = subprocess.run(
                    [engine, "-interaction=nonstopmode", "-halt-on-error",
                     src.name],
                    cwd=work, capture_output=True, text=True,
                    timeout=CASE_TIMEOUT, env=env,
                )
            except subprocess.TimeoutExpired:
                return [(False, f"TIMED OUT after {CASE_TIMEOUT}s: {engine} "
                                f"did not stop (a TeX loop ignores "
                                f"nonstopmode)")]
            if proc.returncode != 0:
                break
        log = work / f"{src.stem}.log"
        text = log.read_text(errors="replace") if log.exists() else ""
        if proc.returncode != 0:
            errs = [ln for ln in text.splitlines()
                    if ln.startswith("!")][:3]
            return [(False, f"BUILD FAILED under {engine}: "
                            f"{'; '.join(errs) or 'see the log'}")]
        pdf = work / f"{src.stem}.pdf"
        if not pdf.exists():
            return [(False, f"{engine} exited 0 and produced no PDF")]
        r = [(True, f"{src.name} builds under {engine} "
                    f"({passes} passes, {len(text.splitlines())} log lines)")]
        return r + (checker(pdf) if checker else [])
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


# ---------------------------------------------------------------------------

def discover_cases():
    """Case-file stems present on disk (anything but the _preamble* helpers).

    Dotfiles are not cases.  An editor open on a case file leaves its lock
    beside it -- Emacs writes a dangling symlink named ".#<case>.tex" -- and
    the integrity check below reported that as an unwired case file, so the
    whole suite refused to start while somebody had a case open.  Nothing
    was wrong with the tree; the report just named a file the author could
    see no reason for.
    """
    return {p.stem for p in CASES.glob("*.tex")
            if not p.name.startswith(("_", "."))}


def suite_integrity():
    """Cross-check the case files on disk against ASSERTIONS.

    The suite only ever runs what ASSERTIONS lists, so a case file that is
    not listed is silently dead code -- it looks like coverage in the
    directory listing and provides none.  That is not hypothetical: the
    first cedilla.tex was committed without an ASSERTIONS entry and was
    never executed, which is how a silent regression in the sub-example
    letters reached a release.  Report both directions, and a KNOWN_XFAIL
    key that names no such engine or case, as hard errors.

    The OTHER way a KNOWN_XFAIL key goes stale -- naming a real case that
    now passes -- cannot be checked here, because nothing has run yet.
    main() checks it after the run.
    """
    problems = []
    on_disk = discover_cases()
    known = set(ASSERTIONS) | set(EXPECT_ERROR)
    for name in sorted(set(ASSERTIONS) & set(EXPECT_ERROR)):
        problems.append(
            f"{name} is in both ASSERTIONS and EXPECT_ERROR; a case either "
            f"compiles and is asserted on, or fails with a known error.")
    for name in sorted(on_disk - known - SMOKE_ONLY):
        problems.append(
            f"{name}.tex has no ASSERTIONS entry, so it is never run. "
            f"Add an assertion function, or list it in SMOKE_ONLY if it is "
            f"only meant to compile."
        )
    for name in sorted(known - on_disk):
        problems.append(f"'{name}' is registered but has no {name}.tex in {CASES}.")
    for name in sorted(set(PASSES) - known):
        problems.append(f"PASSES['{name}'] names no known case.")
    for name in sorted(set(ENGINES_FOR) - known):
        problems.append(f"ENGINES_FOR['{name}'] names no known case.")
    for name, engs in sorted(ENGINES_FOR.items()):
        for e in engs:
            if e not in ENGINES:
                problems.append(
                    f"ENGINES_FOR['{name}'] names no known engine: {e!r}.")
    for key in sorted(KNOWN_XFAIL):
        engine, _, name = key.partition("/")
        if engine not in ENGINES:
            problems.append(f"KNOWN_XFAIL key {key!r} names no known engine.")
        elif name not in known:
            problems.append(f"KNOWN_XFAIL key {key!r} names no known case.")
    problems.extend(tooling_integrity())
    problems.extend(expect_error_selftest())
    return problems


def tooling_integrity():
    """Cross-check REQUIRED_TOOLS against PATH, the docstring and CI.

    Several places have to agree about what the suite needs, and they had
    already drifted once: qpdf reached the docstring and not the workflow,
    so every local run passed and CI failed on a FileNotFoundError two
    minutes in.  The list in REQUIRED_TOOLS is now the only statement of the
    requirement, and this checks that the others match it.

    The docstring half is not pedantry.  It is what a person reads before
    running the suite, and it is the only one of them a reader of the
    file can see.

    The same drift had a second form, which is why --documents is checked
    here too: CI ran the cases and nothing else, so the manual could stop
    compiling and ua-demo could stop being PDF/UA with every push staying
    green -- the gate that would have caught it lived in CLAUDE.md and ran
    only where the author typed it.  A phase CI can silently omit is a
    phase CI eventually omits.
    """
    problems = []
    for tool, (provided, at_startup, why) in REQUIRED_TOOLS.items():
        if at_startup and not shutil.which(tool):
            problems.append(
                f"{tool} is not on PATH; the suite needs it for {why}.")
        if tool not in (__doc__ or ""):
            problems.append(
                f"{tool} is in REQUIRED_TOOLS but this module's docstring "
                f"does not name it, so nobody reading the file learns they "
                f"need it.")
    # What is searched is the apt-get command's own argument list, and not
    # the file.  Searching the file passes a workflow that installs nothing:
    # this one both installs qpdf and SAYS why, in a comment and in a step
    # name, so a whole-file test finds the word three times over and two of
    # them are prose.  Verified the only way worth trusting -- by deleting
    # qpdf from the apt line and watching the first two versions of this
    # check stay green.
    for ci, reference in ((WORKFLOW, True), (GITLAB_CI, False)):
        if not ci.exists():
            continue
        text = ci.read_text(errors="replace")
        joined = re.sub(r"\\\n\s*", " ", text)   # undo the line continuations
        apt = set()
        for m in re.finditer(r"apt-get\s+install[^\n]*", joined):
            apt.update(m.group(0).split())
        for tool, (provided, at_startup, why) in REQUIRED_TOOLS.items():
            kind, _, value = provided.partition(":")
            if kind == "image":
                continue                # the container brings it
            if kind == "apt":
                ok = value in apt
                what = f"install the package {value!r}"
            elif reference:
                ok = f"- name: {value}" in text
                what = f"run a step named {value!r}"
            else:
                # The GitLab file has no named steps to cite, so what is
                # checked there is what the step exists to DO: install the
                # tool and prove it starts.  Both files end that install by
                # running it once with --version, which is also the line
                # that catches the failure veraPDF is famous for -- a
                # launcher that exits 0 without a JVM.
                ok = re.search(rf"(?m)^\s*-?\s*{tool} --version", joined) \
                    is not None
                what = f"install {tool} and run `{tool} --version`"
            if not ok:
                problems.append(
                    f"{tool} is required ({why}) but {ci.name} does not "
                    f"{what}; CI would then fail on a machine that happens "
                    f"not to have it, long after the compile that hides why.")
        # The INVOCATION lines, not the file, for the reason above: both CI
        # files explain the flag in a comment, so a whole-file test for it
        # passes a pipeline that runs the suite without it.  Measured, not
        # assumed -- the first version of this check did exactly that.
        invocations = [ln for ln in joined.splitlines()
                       if "runtests.py" in ln
                       and not ln.strip().lstrip("-").strip().startswith("#")]
        if not any("--documents" in ln for ln in invocations):
            problems.append(
                f"{ci.name} " + ("does not run the suite at all"
                                 if not invocations else
                                 "runs the suite without --documents") +
                ", so it never builds the manual or the shipped examples and "
                "never validates ua-demo with veraPDF.  See DOCUMENTS: those "
                "are the parts of the gate that used to run nowhere but on "
                "the author's machine.")
    return problems


def expect_error_verdict(want, returncode, log):
    r"""Decide an EXPECT_ERROR case from the engine's status AND its log.

    Both halves are load-bearing, and the second one was missing until
    2026-09-17.  Every string in EXPECT_ERROR is the PAYLOAD of the message
    and none of them contains the word "Error" -- "has no partner", "is
    loaded as well as", "inside an \ea example".  So a guard downgraded from
    \msg_error:nn to \msg_warning:nn keeps its wording exactly, the document
    then compiles to the end, and a log-only check stays green while the
    guard no longer guards anything.  Nineteen cases rest on this branch,
    among them the package-clash detection and the one-syntax-per-example
    rule, and a case whose whole point is that the compile STOPS has to
    assert that it stopped.

    Pure, so that expect_error_selftest() can put the case that matters
    through it without a TeX run: the mutation to kill is the deletion of
    the returncode arm, and nothing that needs an engine can be relied on
    to kill it.
    """
    errs = [ln for ln in log.splitlines() if ln.startswith("!")][:3]
    if want not in log:
        return [(False, f"expected the error {want!r}; got "
                        f"{'; '.join(errs) or 'a clean compile'}")]
    if returncode == 0:
        return [(False, f"logged {want!r} but the compile SUCCEEDED; this "
                        f"case is meant to stop the engine, so the message "
                        f"has been downgraded to a warning")]
    return [(True, f"raises its error: {want!r}")]


def expect_error_selftest():
    """Put the three shapes of EXPECT_ERROR outcome through the verdict.

    The middle one is the point: it is the state the suite could not see
    before, and it is indistinguishable from a pass in the log alone.  This
    costs no TeX run, so it is checked on every invocation rather than
    being a case somebody remembers to run.
    """
    problems = []
    want = "is loaded as well as"
    logged = f"Package linguexx Warning: linguex {want} linguexx.\n"
    if expect_error_verdict(want, 1, logged)[0][0] is not True:
        problems.append(
            "expect_error_verdict() rejects a case that logged its message "
            "and stopped the engine, which is what every EXPECT_ERROR case "
            "is supposed to do.")
    if expect_error_verdict(want, 0, logged)[0][0] is not False:
        problems.append(
            "expect_error_verdict() accepts a case whose message reached the "
            "log but whose compile SUCCEEDED, so all "
            f"{len(EXPECT_ERROR)} EXPECT_ERROR cases would stay green if "
            "their guards were downgraded from errors to warnings.")
    if expect_error_verdict(want, 1, "! Undefined control sequence.\n")[0][0] \
            is not False:
        problems.append(
            "expect_error_verdict() accepts a case that failed with the "
            "WRONG error, so any failure would satisfy any expectation.")
    return problems


def run_case(name: str, engine: str, verbose: bool):
    """Compile one case under one engine and run its assertions."""
    src = CASES / f"{name}.tex"
    if not src.is_file():
        return [(False, f"MISSING CASE FILE: {src}")]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        shutil.copy(src, tmp)
        for pre in CASES.glob("_preamble*.tex"):
            shutil.copy(pre, tmp)
        shutil.copy(STY, tmp)
        first_log = ""
        # A TMPDIR of this case's own.  xdvipdfmx creates its temporary file
        # there with mkstemp, then reopens it BY NAME and unlinks it by name
        # when it is done; with every concurrent case sharing /tmp, two runs
        # that draw the same name inside that window delete each other's
        # file and the loser dies with "No such file or directory", exit 1,
        # a log truncated at "(./case.tex", no TeX error and no signal.  It
        # never reproduces, which is what makes it expensive.  A private
        # directory removes the shared namespace the race needs; see
        # DEFAULT_JOBS for the measurement.  The assertion helpers below
        # still use the system /tmp, and may: none of them reopens a
        # temporary file by name.
        env = dict(os.environ, TMPDIR=str(tmp))
        for npass in range(PASSES.get(name, DEFAULT_PASSES)):
            try:
                proc = subprocess.run(
                    [engine, "-interaction=nonstopmode", "-halt-on-error",
                     src.name],
                    cwd=tmp, capture_output=True, text=True,
                    timeout=CASE_TIMEOUT, env=env,
                )
            except subprocess.TimeoutExpired:
                # A TeX loop does not stop for -interaction=nonstopmode: it
                # spins with nothing in the log, and without this the whole
                # suite hangs instead of reporting.  This is a real failure
                # mode, not a hypothetical -- an unguarded \DeclareJudgment
                # argument redefines \% and loops forever.
                return [(False, f"TIMED OUT after {CASE_TIMEOUT}s: the engine "
                                f"did not stop (a TeX loop ignores "
                                f"nonstopmode)")]
            # The COLD run's log, kept because some of what the package
            # reports can only be said on it.  A mechanism that hands the
            # anchors of one run to the next has nothing to go on when the
            # .aux is empty, and what it must do there -- ask for a rerun,
            # rather than report every reference as unresolved -- is invisible
            # in the converged log the assertions otherwise see.
            if npass == 0:
                cold = tmp / f"{name}.log"
                first_log = cold.read_text(errors="replace") if cold.exists() \
                    else ""
        # Cases whose point IS the error: the compile is meant to stop, so
        # check the message before treating a non-zero status as a failure --
        # and check that it DID stop, which is the other half.  See
        # expect_error_verdict() for why the log alone cannot say so.
        if name in EXPECT_ERROR:
            return expect_error_verdict(
                EXPECT_ERROR[name], proc.returncode,
                (tmp / f"{name}.log").read_text(errors="replace"))
        if proc.returncode != 0:
            log = (tmp / f"{name}.log").read_text(errors="replace")
            errs = [ln for ln in log.splitlines() if ln.startswith("!")][:3]
            return [(False, f"COMPILE FAILED: {'; '.join(errs) or 'see log'}")]
        pdf = tmp / f"{name}.pdf"
        if not pdf.exists():
            return [(False, "COMPILE produced no PDF")]
        page = parse_pdf(pdf)
        # Warnings never reach the PDF, so a case that is about what the
        # package REPORTS needs the log as well as the rendering.
        page.log = (tmp / f"{name}.log").read_text(errors="replace")
        page.first_log = first_log
        # ... and a case about hyperref ANCHORS needs the .aux: the anchor a
        # \label stores is invisible in the rendering (the printed number is
        # right even when the anchor is wrong), and the engines disagree on
        # whether a duplicate destination is even reported -- pdflatex and
        # lualatex warn, xelatex says nothing at all, because the collision
        # is resolved by xdvipdfmx and not by the format.  The .aux is the
        # one record all three write identically.
        aux = tmp / f"{name}.aux"
        page.aux = aux.read_text(errors="replace") if aux.exists() else ""
        # ... and a case about a PDF BOOKMARK needs hyperref's .out, for the
        # same reason: a bookmark is not on the page, it is not in the text
        # layer, and in the PDF it sits inside a compressed object stream.
        # The .out is what hyperref writes it from, in one line per heading.
        out = tmp / f"{name}.out"
        page.out = out.read_text(errors="replace") if out.exists() else ""
        # ... and a case about what an ENGINE reports needs to know which
        # one it is.  The three do not agree about a duplicate destination:
        # pdftex and luatex warn, xdvipdfmx says nothing, and an assertion
        # that cannot name the engine can only shrug at the difference.
        page.engine = engine
        try:
            return ASSERTIONS[name](page)
        except AssertionError as e:
            return [(False, f"ASSERTION SETUP: {e}")]


def main():
    ap = argparse.ArgumentParser(description="linguexx regression suite")
    ap.add_argument("-e", "--engine", action="append", choices=ENGINES,
                    help="restrict to one engine (repeatable)")
    ap.add_argument("-k", "--filter", help="only cases whose name contains this")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print passing assertions too")
    ap.add_argument("-j", "--jobs", type=int, default=DEFAULT_JOBS,
                    help=f"cases to compile at once (default: {DEFAULT_JOBS}, "
                         f"see DEFAULT_JOBS; -j1 runs them one at a time)")
    ap.add_argument("--documents", action="store_true",
                    help="also build the manual and the shipped examples, "
                         "and validate ua-demo with veraPDF (see DOCUMENTS); "
                         "CI passes this, and the manual costs about a "
                         "minute, which is why it is opt-in")
    args = ap.parse_args()

    # Deliberately before -k filtering: a filtered run must still notice a
    # case file that nothing runs.
    problems = suite_integrity()
    if problems:
        print("SUITE INTEGRITY:", file=sys.stderr)
        for p in problems:
            print(f"  X {p}", file=sys.stderr)
        return 2

    engines = args.engine or ENGINES
    names = sorted(set(ASSERTIONS) | set(EXPECT_ERROR))
    if args.filter:
        names = [n for n in names if args.filter in n]
    # -k filters the documents too, so `-k manual --documents` is a way to
    # build one of them and nothing else.
    doc_names = sorted(DOCUMENTS) if args.documents else []
    if args.filter:
        doc_names = [n for n in doc_names if args.filter in n]
    if not names and not doc_names:
        print("no cases match", file=sys.stderr)
        return 2

    total = passed = 0
    failed_cases = []
    # A KNOWN_XFAIL entry is a claim that a pair still fails.  Track which
    # pairs this run actually observed and which of them bore the claim out,
    # so an entry that has quietly started passing can be reported instead of
    # silently swallowing a green result (see the KNOWN_XFAIL comment).
    # `exercised` is what makes that safe under -k, -e, ENGINES_FOR and a
    # missing engine: without it, every entry a filtered run never reached
    # would be indistinguishable from one that no longer fires.
    exercised = set()
    fired = set()

    # The plan, built before anything runs: for each engine either the cases
    # it will run or None for "not installed".  Two things need it up front.
    # The report must come out in this order however the work is scheduled,
    # and a parallel run has to know the whole job list before starting.
    plan = []
    for engine in engines:
        if not shutil.which(engine):
            plan.append((engine, None))
        else:
            plan.append((engine, [n for n in names
                                  if engine in ENGINES_FOR.get(n, ENGINES)]))
    units = [(e, n) for e, ns in plan if ns for n in ns]

    # A case is independent of every other one: run_case makes its own
    # temporary directory, copies the package and the preambles into it, and
    # compiles with cwd set there, so nothing outside is read or written and
    # no two cases can meet.  Serial execution was therefore buying nothing
    # but ordered output, which is recovered below by printing along `plan`
    # rather than as results arrive.
    #
    # Threads rather than processes: every slow part here is a subprocess --
    # the engine, pdftotext, pdfinfo, qpdf, veraPDF -- so the interpreter
    # lock is released for almost the whole of a case, and threads keep the
    # results as ordinary objects instead of pickling them back.
    jobs = max(1, args.jobs)
    if jobs > 1 and len(units) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(run_case, n, e, args.verbose): (e, n)
                       for e, n in units}
            done = {futures[f]: f.result()
                    for f in concurrent.futures.as_completed(futures)}
    else:
        done = {(e, n): run_case(n, e, args.verbose) for e, n in units}

    for engine, engine_names in plan:
        if engine_names is None:
            print(f"SKIP {engine}: not installed")
            continue
        print(f"\n=== {engine} ===")
        for name in engine_names:
            results = done[(engine, name)]
            ok = sum(1 for good, _ in results if good)
            total += len(results)
            passed += ok
            bad = [d for good, d in results if not good]
            key = f"{engine}/{name}"
            exercised.add(key)
            if bad and key in KNOWN_XFAIL:
                status = "XFAIL"
                fired.add(key)
            else:
                status = "PASS" if not bad else "FAIL"
            print(f"  [{status}] {name:16s} {ok}/{len(results)} assertions")
            if args.verbose:
                for good, d in results:
                    if good:
                        print(f"           . {d}")
            for d in bad:
                print(f"           X {d}")
            if bad and key not in KNOWN_XFAIL:
                failed_cases.append(key)

    # The documents last: they are the slowest part of the run and the one
    # whose failure is least likely to be diagnosed from the line above it.
    doc_total = doc_passed = 0
    if doc_names:
        print("\n=== documents ===")
        for name in doc_names:
            results = run_document(name)
            ok = sum(1 for good, _ in results if good)
            doc_total += len(results)
            doc_passed += ok
            bad = [d for good, d in results if not good]
            print(f"  [{'PASS' if not bad else 'FAIL'}] {name:16s} "
                  f"{ok}/{len(results)} checks")
            if args.verbose:
                for good, d in results:
                    if good:
                        print(f"           . {d}")
            for d in bad:
                print(f"           X {d}")
            if bad:
                failed_cases.append(f"documents/{name}")

    print(f"\n{passed}/{total} assertions passed across {len(engines)} engine(s).")
    if doc_names:
        print(f"{doc_passed}/{doc_total} checks passed on "
              f"{len(doc_names)} document(s).")
    stale = sorted((KNOWN_XFAIL & exercised) - fired)
    if stale:
        print("STALE KNOWN_XFAIL: these ran and PASSED, so the entry no "
              "longer excuses anything and hides the assertion instead:",
              file=sys.stderr)
        for key in stale:
            print(f"  X {key}", file=sys.stderr)
    if failed_cases:
        # A real failure outranks a stale entry: it is the thing to look at
        # first, and the stale list is printed above either way.
        print("FAILED: " + ", ".join(failed_cases))
        return 1
    if stale:
        return 2
    print("All green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
