#!/usr/bin/env python3
r"""Assemble the CTAN upload for linguexx, and refuse to when it is wrong.

A release is not a hard thing to do; it is a hard thing to do TWICE the
same way, months apart, from memory.  What this file replaces is the
afternoon of judgment: what goes in the archive, which copy of the manual,
what the version has to agree with, and whether the thing that was uploaded
actually loads.

    python3 tools/ctan.py --check     the version consistency check alone
    python3 tools/ctan.py             the whole release build
    python3 tools/ctan.py --tds       ... and a TDS archive beside it

The steps, and why each is here rather than in a checklist somebody reads:

1.  The tree must be clean.  The archive is built from the working tree,
    so a dirty one ships a file no commit records and no tag can name.
2.  The version must agree everywhere it is stated -- see check_versions,
    which is the reason this file exists at all.
3.  The suite must pass, documents included (`runtests.py --documents`).
4.  The manual is REBUILT from the .sty being shipped, in a directory of
    its own, through the suite's own DOCUMENTS entry.  The repository's
    linguexx-doc.pdf is a committed artifact and can be older than the
    package it documents; what goes in the archive never is.
5.  The archive is unpacked into a scratch TEXMF and a probe document is
    compiled against THAT copy, under every engine on the machine.  This
    is the only step that tests the artifact rather than the repository,
    and it is the one that catches an archive missing a file, holding a
    stale .sty, or unpacking into the wrong shape.
6.  The upload form's fields are printed, announcement included, so the
    web form is filled from the CHANGELOG rather than from memory.

What it deliberately does NOT do: bump a version, write a tag, or upload
anything.  Those are decisions; this is plumbing.
"""

import argparse
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STY = REPO / "linguexx.sty"
CHANGELOG = REPO / "CHANGELOG.md"
MANUAL_TEX = REPO / "linguexx-doc.tex"
MANUAL_PDF = REPO / "linguexx-doc.pdf"

#: What the archive contains: the four files the CTAN directory already
#: holds, unpacking into a single directory named after the package.
#: Deliberately not a glob of the repository -- the tests, the notes in
#: doc/ and the agent harness are how the package is made, not what it is,
#: and a release that quietly starts shipping them is a release nobody
#: decided on.
PAYLOAD = ["README.md", "LICENSE", "linguexx.sty", "linguexx-doc.pdf"]

#: The TDS layout, for the optional linguexx.tds.zip: where a TeX
#: distribution would put each of those files.
TDS = {
    "tex/latex/linguexx": ["linguexx.sty"],
    "doc/latex/linguexx": ["README.md", "LICENSE", "linguexx-doc.pdf"],
}

#: The probe compiled against the UNPACKED archive.  Small, and not a smoke
#: test of the package: the suite has 2267 assertions for that.  What it has
#: to do is touch enough of the file that a truncated or half-copied .sty
#: cannot compile it -- an example, a sub-example, a gloss, a judgment, a
#: cross-reference -- and then say which file it loaded.
PROBE = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\ex.\label{p:one} A numbered example.
\a. a sub-example
\b. *a judged one

\exg. Der Hund bellte.\\
the dog barked\\
\glt `The dog barked.'

Cross-references: (\ref{p:one}) and \Last{}.
\end{document}
"""


def sh(cmd, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("errors", "replace")
    return subprocess.run([str(c) for c in cmd], **kw)


def runtests():
    """tests/runtests.py as a module: DOCUMENTS and run_document.

    The manual is built through the suite's own entry for it rather than by
    a second copy of the recipe here.  There is exactly one statement of
    "how the manual is built", and CI, the agent harness and this file all
    read it from the same place.
    """
    spec = importlib.util.spec_from_file_location(
        "runtests", REPO / "tests" / "runtests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
#  The version consistency check
# ---------------------------------------------------------------------------

#: Where the version number is written down.  Four places, and they have
#: already disagreed: the working tree says 1.2 and so does CTAN, but
#: CTAN's 1.2 is the tag from 2026-07-31 and the tree's is sixty-odd
#: commits past it, including a public API and a user-visible alignment
#: fix.  Nothing said so, because nothing was checking.  The date is
#: checked with the number because \usepackage{linguexx}[2026/09/03] is a
#: real thing a document can write, and it compares the DATE.
def package_version():
    """(version, date) from \\ProvidesPackage, or (None, None)."""
    m = re.search(r"\\ProvidesPackage\{linguexx\}\[(\d{4})/(\d{2})/(\d{2})"
                  r"[^\]]*?v\.\s*([0-9]+(?:\.[0-9]+)*)\]", STY.read_text())
    if not m:
        return None, None
    return m.group(4), f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def tracked(pattern):
    """Files git tracks, so an untracked work order cannot block a release."""
    out = sh(["git", "-C", REPO, "ls-files", pattern]).stdout
    return [REPO / l for l in out.split() if l]


def check_versions():
    """Every place that states the version must state the same one.

    Returns a list of problems, empty when they agree.  Each entry says
    what disagrees with what, because the fix is never "make it pass" but
    "decide which number is right and put it everywhere".
    """
    problems = []
    version, when = package_version()
    if not version:
        return [f"{STY.name}: no \\ProvidesPackage line of the expected "
                f"shape (a date and 'v. N.N'); everything else here is "
                f"checked against it, so nothing can be checked."]

    # 1. the changelog's top section
    head = re.search(r"(?m)^##\s+(\S+)", CHANGELOG.read_text())
    if not head:
        problems.append(f"{CHANGELOG.name}: no '## <version>' heading found.")
    elif head.group(1) != version:
        problems.append(
            f"{CHANGELOG.name} opens with '## {head.group(1)}' but the "
            f"package is v{version}: the release notes and the package "
            f"disagree about what is being released.")

    # 2. the manual's title page
    m = re.search(r"\\date\{Version\s+([0-9.]+)", MANUAL_TEX.read_text())
    if not m:
        problems.append(f"{MANUAL_TEX.name}: no '\\date{{Version N.N ...}}' "
                        f"to check.")
    elif m.group(1) != version:
        problems.append(
            f"{MANUAL_TEX.name} puts 'Version {m.group(1)}' on the title "
            f"page of a v{version} package: the manual in the archive would "
            f"name a different release than the .sty beside it.")

    # 3. the tag.  A version that is already tagged is already released --
    #    the whole failure this check exists for.
    tag = sh(["git", "-C", REPO, "rev-parse", "--verify", "--quiet",
              f"refs/tags/{version}^{{commit}}"]).stdout.strip()
    head_commit = sh(["git", "-C", REPO, "rev-parse", "HEAD"]).stdout.strip()
    if tag and tag != head_commit:
        n = sh(["git", "-C", REPO, "rev-list", "--count",
                f"{version}..HEAD"]).stdout.strip()
        problems.append(
            f"v{version} is already tagged, at {tag[:7]}, and this tree is "
            f"{n} commits past it.  Uploading it would put a second, "
            f"different package on CTAN under a version number that is "
            f"taken.  Bump the version (and the date) in {STY.name}, open a "
            f"new section in {CHANGELOG.name}, and set the manual's "
            f"\\date{{Version ...}} to match.")

    # 4. prose that names a LATER version than the one being released.  This
    #    is the drift the notes produce: a feature is written up as landing
    #    in the next release, ships in this one, and the note keeps the
    #    number it was drafted with (doc/EXPEX-GAPS.md said v1.4 for what
    #    shipped in 1.2).  Only tracked files, and only numbers ahead of the
    #    package: history is allowed to mention every version there ever was.
    def key(v):
        return tuple(int(x) for x in v.split("."))

    for path in tracked("*.md"):
        if path.name == "CHANGELOG.md":
            continue                    # history, by definition
        for m in re.finditer(r"v\.?\s?([0-9]+\.[0-9]+)", path.read_text()):
            if key(m.group(1)) > key(version):
                line = path.read_text()[:m.start()].count("\n") + 1
                problems.append(
                    f"{path.relative_to(REPO)}:{line} names v{m.group(1)}, "
                    f"which is ahead of the v{version} being released: "
                    f"either the note is wrong or the release is.")

    # 5. the date.  It is what \usepackage{linguexx}[<date>] compares, so
    #    it has to be the release's own date, not the date of some earlier
    #    edit -- and it can never be in the future.
    if when > date.today().isoformat():
        problems.append(f"{STY.name} is dated {when}, which is in the "
                        f"future; \\usepackage{{linguexx}}[{when}] would "
                        f"then be unsatisfiable by a correct install.")
    last = sh(["git", "-C", REPO, "log", "-1", "--format=%ad", "--date=short",
               "--", str(STY)]).stdout.strip()
    if last and last > when:
        problems.append(
            f"{STY.name} is dated {when} but was last changed on {last}: "
            f"the date a document tests with is older than the file it "
            f"tests, so a fix would appear to be in a release that predates "
            f"it.")
    return problems


# ---------------------------------------------------------------------------
#  The archive
# ---------------------------------------------------------------------------

def build_manual(into: Path):
    """The manual, rebuilt from the .sty being shipped.  Returns its PDF."""
    rt = runtests()
    results = rt.run_document("manual", outdir=into)
    bad = [d for good, d in results if not good]
    if bad:
        raise SystemExit("the manual does not build, so there is nothing to "
                         "ship:\n  " + "\n  ".join(bad))
    return into / "linguexx-doc.pdf"


def stage(outdir: Path, manual_pdf: Path):
    """dist/linguexx/, holding exactly PAYLOAD."""
    tree = outdir / "linguexx"
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    for name in PAYLOAD:
        src = manual_pdf if name == "linguexx-doc.pdf" else REPO / name
        if not src.is_file():
            raise SystemExit(f"the archive wants {name} and there is none.")
        shutil.copy(src, tree / name)
    return tree


def zip_tree(tree: Path, zip_path: Path, prefix: str = None):
    """Zip a directory, optionally under one top-level name.

    The upload archive wants the prefix (CTAN unpacks it into a directory
    named after the package); a TDS archive must NOT have one -- it is
    unpacked at the root of a texmf tree, and a prefix would bury every
    file one level below where kpathsea looks.
    """
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(tree.rglob("*")):
            if p.is_file():
                rel = p.relative_to(tree)
                z.write(p, f"{prefix}/{rel}" if prefix else str(rel))
    return zip_path


def tds_zip(tree: Path, outdir: Path):
    """linguexx.tds.zip: the same files, in the layout an install expects."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for where, names in TDS.items():
            d = root / where
            d.mkdir(parents=True)
            for n in names:
                shutil.copy(tree / n, d / n)
        return zip_tree(root, outdir / "linguexx.tds.zip")


def install_test(zip_path: Path, version: str, when: str):
    """Compile a probe against the UNPACKED archive, under every engine.

    Nothing before this step has tested the thing that gets uploaded: the
    suite tests the working tree, and the working tree is not what a user
    installs.  An archive that unpacks into the wrong shape, or is missing
    the file it names, or holds last month's .sty, passes every other check
    in this file and fails here.

    TEXMFHOME is where the copy goes, because kpathsea prefers it to the
    distribution's own tree -- so the linguexx already installed on this
    machine (there is one; that is the point of releasing) cannot answer
    for the one under test.  The log is then read for the path it actually
    opened, which is the only proof of that.
    """
    problems = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(root / "unpacked")
        unpacked = root / "unpacked" / "linguexx"
        if not unpacked.is_dir():
            return [f"{zip_path.name} does not unpack into a single "
                    f"'linguexx/' directory."]
        missing = [n for n in PAYLOAD if not (unpacked / n).is_file()]
        if missing:
            problems.append(f"the archive is missing {missing}.")

        texmf = root / "texmf" / "tex" / "latex" / "linguexx"
        texmf.mkdir(parents=True)
        shutil.copy(unpacked / "linguexx.sty", texmf)
        work = root / "probe"
        work.mkdir()
        (work / "probe.tex").write_text(PROBE)
        # max_print_line: TeX wraps the log at 79 columns, and both things
        # read out of it below -- the path of the file it opened and the
        # \ProvidesPackage line it echoed -- are longer than that.  The
        # first version of this check asked for them in a wrapped log and
        # reported that the archive did not identify itself, which was
        # true of the log and false of the archive.  The env var is
        # belt; the braces are the de-wrapped copy matched against.
        env = dict(os.environ, TEXMFHOME=str(root / "texmf"),
                   TEXINPUTS="", TMPDIR=str(work), max_print_line="10000")
        for engine in ("pdflatex", "xelatex", "lualatex"):
            if not shutil.which(engine):
                problems.append(f"{engine} is not installed, so the archive "
                                f"was not tested under it.")
                continue
            for _ in range(2):          # \ref needs the second pass
                proc = subprocess.run(
                    [engine, "-interaction=nonstopmode", "-halt-on-error",
                     "probe.tex"], cwd=work, capture_output=True, text=True,
                    errors="replace", env=env, timeout=180)
            log = (work / "probe.log").read_text(errors="replace")
            flat = log.replace("\n", "")     # see max_print_line above
            if proc.returncode != 0:
                errs = [l for l in log.splitlines() if l.startswith("!")][:3]
                problems.append(f"the archive's linguexx.sty does not "
                                f"compile under {engine}: "
                                f"{'; '.join(errs) or 'see the log'}")
                continue
            if str(texmf) not in flat:
                problems.append(
                    f"under {engine} the probe did not load the archive's "
                    f"copy: nothing under {texmf} appears in the log, so "
                    f"some other linguexx answered and this test proved "
                    f"nothing.")
            m = re.search(r"Package: linguexx (\d{4})/(\d{2})/(\d{2})"
                          r".*?v\.\s*([0-9.]+)", flat)
            if not m:
                problems.append(f"under {engine} the log does not identify "
                                f"the package it loaded.")
            else:
                got, got_when = m.group(4), "-".join(m.group(1, 2, 3))
                if (got, got_when) != (version, when):
                    problems.append(
                        f"under {engine} the archive loaded v{got} of "
                        f"{got_when}, and the release is v{version} of "
                        f"{when}: the zip holds the wrong file.")
    return problems


def announcement(version: str):
    """The CHANGELOG section for this version, for the upload form."""
    text = CHANGELOG.read_text()
    m = re.search(rf"(?ms)^##\s+{re.escape(version)}\s*$(.*?)(?=^##\s)", text)
    return (m.group(1).strip() if m else
            "(no CHANGELOG section found for this version)")


def sha256(path: Path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(
        description="build the CTAN upload for linguexx",
        epilog="It never bumps a version, writes a tag, or uploads.")
    ap.add_argument("--check", action="store_true",
                    help="run the version consistency check and stop")
    ap.add_argument("--no-test", action="store_true",
                    help="skip the regression suite (it is the slow step, "
                         "and skipping it is a decision, not a shortcut)")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="build from a tree with uncommitted changes")
    ap.add_argument("--tds", action="store_true",
                    help="also write linguexx.tds.zip")
    ap.add_argument("--out", type=Path, default=REPO / "dist",
                    help="where the archive goes (default: dist/)")
    a = ap.parse_args()

    version, when = package_version()
    problems = check_versions()
    if problems:
        print(f"VERSION CHECK FAILED ({len(problems)} problem(s)):\n")
        for p in problems:
            print(f"  X {p}\n")
        return 1
    print(f"version: linguexx v{version}, dated {when} -- "
          f"the .sty, the changelog, the manual and the tags agree.")
    if a.check:
        return 0

    dirty = sh(["git", "-C", REPO, "status", "--porcelain"]).stdout.strip()
    if dirty and not a.allow_dirty:
        print("\nthe tree has uncommitted changes, so the archive would "
              "hold a file no commit records:\n")
        print("\n".join("  " + l for l in dirty.splitlines()))
        print("\ncommit them, or pass --allow-dirty if this is a dry run.")
        return 1

    if not a.no_test:
        print("\nrunning the suite (all three engines, documents included) "
              "-- this is the slow part ...")
        rc = subprocess.run([sys.executable, "tests/runtests.py",
                             "--documents"], cwd=REPO).returncode
        if rc != 0:
            print("\nthe suite did not come out green; nothing was built.")
            return 1

    a.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        print("\nrebuilding the manual from the .sty being shipped ...")
        manual = build_manual(Path(td) / "manual")
        tree = stage(a.out, manual)
        archive = zip_tree(tree, a.out / "linguexx.zip", "linguexx")
        if a.tds:
            tds = tds_zip(tree, a.out)

    print(f"\ntesting the archive itself, unpacked, under every engine ...")
    problems = install_test(archive, version, when)
    if problems:
        print(f"\nARCHIVE REJECTED ({len(problems)} problem(s)):\n")
        for p in problems:
            print(f"  X {p}\n")
        return 1

    print(f"\n  {archive}  ({archive.stat().st_size // 1024} kB)")
    print(f"  sha256 {sha256(archive)}")
    for name in PAYLOAD:
        print(f"    linguexx/{name}")
    if a.tds:
        print(f"  {tds}  ({tds.stat().st_size // 1024} kB)")

    print(f"""
The archive loads, under every engine on this machine, from an install of
its own.  What is left is yours: tag it and upload it.

    git tag -a {version} -m "linguexx {version}"
    # https://ctan.org/upload

    Package    linguexx
    Version    {version}
    Date       {when}
    Licence    lppl1.3c
    Author     Gerhard Schaden
    Summary    Standalone linguistic examples, linguex-compatible interface
    Archive    {archive}

Announcement (from CHANGELOG.md):
""")
    print(announcement(version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
