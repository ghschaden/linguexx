#!/usr/bin/env python3
r"""The revert check: a change to linguexx.sty's code must be one the suite sees.

Run by tools/hooks/commit-msg (`make hooks` installs it).  For a commit whose
staged linguexx.sty differs from HEAD's in anything but comments, the suite
runs on the commit's own tree with HEAD's .sty put back.  Something has to
fail there -- and, re-run on its own, fail again with the old .sty and pass
with the new one, so that a flaky case cannot stand in for a test.  If
nothing fails, nothing in the suite depends on the change, and the commit
is refused.

Why: cbbffeb kept the [phantomalign] pad's measuring boxes out of the
structure tree and changed only the .sty.  No case declared a math mark and
veraPDF passes the file either way, so reverting it left every gate green,
and the fix went into 1.3.1 before anything tested it.  "Add a test" was
already the rule.  Asking the suite whether it can tell the commit from its
parent is what enforces it.

A change the suite legitimately cannot see -- a refactor, a speed-up, a
reworded message -- says so in the commit message:

    Untested: <why no test can tell the difference>

and goes through without a run.  The reason stays in `git log`, so every
exemption is a claim somebody made and can be found, not a silence.

The tree tested is the INDEX, exported to a temporary directory, not the
working tree: a test written but not staged does not count, because it is
not in the commit.

Limits, stated rather than hidden:
- Per commit, not per hunk.  A commit carrying a tested and an untested
  change passes on the first; keep one change per commit.
- It proves the suite notices the change, not that it checks the right thing.
- Under `git commit --amend` the baseline is the commit being amended, so
  only what the amend adds to the .sty is checked.
- A merge commit is not checked; its sides were, when they were committed.
- The new tree is not required to be green as a whole -- only the case that
  confirms the change is run against it.  Green is the suite's job before
  the commit; running it twice here would double the cost.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

STY = "linguexx.sty"
TRAILER = "Untested"
#: Failing cases re-run, at most, to find one that confirms the change.  A
#: code change fails a handful of cases or a hundred; one confirmed is enough,
#: and each costs two single-case runs.
MAX_CONFIRM = 3


def git(*args, check=True, **kw):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=check, **kw)


def say(text):
    print(text, file=sys.stderr)


def code_lines_changed():
    """The lines of linguexx.sty the commit adds or removes, comments aside."""
    diff = git("diff", "--cached", "-U0", "HEAD", "--", STY).stdout
    out = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---")) or line[:1] not in ("+", "-"):
            continue
        body = line[1:].strip()
        if body and not body.startswith("%"):
            out.append(line)
    return out


def untested_reason(msg_path):
    """The value of an `Untested:` trailer in the message, or None."""
    text = Path(msg_path).read_text()
    # A commented-out template line must not count, whether or not git has
    # stripped the comments before calling the hook.
    text = "\n".join(ln for ln in text.splitlines()
                     if not ln.startswith("#"))
    parsed = git("interpret-trailers", "--parse", input=text).stdout
    for line in parsed.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == TRAILER.lower() and value.strip():
            return value.strip()
    return None


def run_suite(tree, *args):
    """(returncode, failed engine/case keys, output) of the suite in `tree`."""
    r = subprocess.run([sys.executable, str(tree / "tests" / "runtests.py"),
                        *args], cwd=tree, capture_output=True, text=True)
    m = re.search(r"(?m)^FAILED: (.*)$", r.stdout)
    failed = [k.strip() for k in m.group(1).split(",")] if m else []
    return r.returncode, failed, r.stdout + r.stderr


def refuse(msg_path, why, changed):
    say("\nrevert check: REFUSED.\n")
    say(why)
    say("\nEither stage a test that fails without the change, or, if no test "
        "can see it\n(a refactor, a speed-up), say so in the message:\n\n"
        f"    {TRAILER}: <why no test can tell the difference>\n")
    say(f"The message is kept in {msg_path}; `git commit -F {msg_path}` "
        "reuses it.\n`git commit --no-verify` skips every hook, this one "
        "included.")
    say(f"\nThe changed code lines of {STY} ({len(changed)}), first few:")
    for line in changed[:5]:
        say(f"    {line[:100]}")
    return 1


def main():
    msg_path = sys.argv[1]
    if git("rev-parse", "--verify", "--quiet", "HEAD",
           check=False).returncode:
        return 0                                    # the first commit
    gitdir = Path(git("rev-parse", "--absolute-git-dir").stdout.strip())
    if (gitdir / "MERGE_HEAD").exists():
        return 0
    changed = code_lines_changed()
    if not changed:
        return 0
    reason = untested_reason(msg_path)
    if reason:
        say(f"revert check: skipped, {TRAILER}: {reason}")
        return 0

    say(f"revert check: {len(changed)} changed code line(s) in {STY}; "
        f"running the suite with HEAD's {STY} put back ...")
    with tempfile.TemporaryDirectory(prefix="lxx-revert-") as td:
        tree = Path(td)
        # The index, not the working tree: under `git commit -a` or with
        # paths, git points GIT_INDEX_FILE at the commit's own index, and
        # both commands here honour it.
        git("checkout-index", "--all", f"--prefix={tree}/")
        new_sty = (tree / STY).read_bytes()
        old_sty = subprocess.run(["git", "show", f"HEAD:{STY}"],
                                 capture_output=True, check=True).stdout
        (tree / STY).write_bytes(old_sty)

        rc, failed, out = run_suite(tree)
        if rc == 0:
            return refuse(msg_path,
                          f"The suite is GREEN with HEAD's {STY} put back: "
                          f"nothing in it can tell\nthis commit from its "
                          f"parent, so the change is untested.", changed)
        if rc != 1 or not failed:
            tail = "\n".join(out.strip().splitlines()[-8:])
            return refuse(msg_path,
                          f"The suite with HEAD's {STY} ended without a "
                          f"verdict (exit {rc}):\n{tail}", changed)

        tried = []
        for key in failed[:MAX_CONFIRM]:
            engine, _, case = key.partition("/")
            one = ("-k", case, "-e", engine, "-j", "1")
            (tree / STY).write_bytes(old_sty)
            _, f_old, _ = run_suite(tree, *one)
            if key not in f_old:
                tried.append(f"{key}: passed when re-run alone with HEAD's "
                             f"{STY} (flaky?)")
                continue
            (tree / STY).write_bytes(new_sty)
            rc_new, f_new, _ = run_suite(tree, *one)
            if key in f_new or rc_new not in (0, 1):
                tried.append(f"{key}: fails with the staged {STY} too")
                continue
            say(f"revert check: ok -- {key} fails with HEAD's {STY} and "
                f"passes with the staged one ({len(failed)} failing "
                f"case(s) in all).")
            return 0

        return refuse(msg_path,
                      f"The suite failed with HEAD's {STY} put back, but no "
                      f"failure could be pinned\non the change:\n    "
                      + "\n    ".join(tried), changed)


if __name__ == "__main__":
    sys.exit(main())
