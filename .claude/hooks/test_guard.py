#!/usr/bin/env python3
"""The guards of guard.py, run against the events Claude Code sends.

    python3 .claude/hooks/test_guard.py

Each case is one PreToolUse event and the verdict it must get: 2 (refused)
or 0 (let through).  The release switch is tested in a scratch state
directory (LXX_GUARD_STATE), never the real one.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GUARD = HERE / "guard.py"
SWITCH = ".claude/.state/" + "release-ok"


def run(event, state):
    env = {**os.environ, "LXX_GUARD_STATE": str(state)}
    r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event),
                       capture_output=True, text=True, env=env, cwd=ROOT)
    return r.returncode, r.stderr


def edit(rel, old, new):
    return {"hook_event_name": "PreToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": str(ROOT / rel),
                           "old_string": old, "new_string": new}}


def write(rel, content):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": str(ROOT / rel), "content": content}}


def bash(cmd):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": cmd}}


def line_of(rel, needle):
    """The whole line holding `needle`, as an old_string that is there."""
    return next(ln for ln in (ROOT / rel).read_text().splitlines()
                if needle in ln)


def sty_line():
    sty = line_of("linguexx.sty", "\\ProvidesPackage{linguexx}")
    return sty, sty.rsplit("v. ", 1)[1].rstrip("]")


def cases():
    sty, ver = sty_line()
    bumped = sty.replace(f"v. {ver}]", "v. 99.0]")
    redated = sty.replace(sty.split("[", 1)[1][:10], "2099/01/01")
    date = line_of("linguexx-doc.tex", "\\date{Version")
    return [
        # the version, in each of its three places
        ("sty version bump", edit("linguexx.sty", sty, bumped), 2),
        ("sty date alone", edit("linguexx.sty", sty, redated), 0),
        ("sty ordinary edit", edit("linguexx.sty", "\\ProvidesPackage",
                                   "\\ProvidesPackage"), 0),
        ("Write of the sty with a bumped version",
         write("linguexx.sty",
               (ROOT / "linguexx.sty").read_text().replace(sty, bumped)), 2),
        ("changelog: Unreleased becomes a version",
         edit("CHANGELOG.md", "## Unreleased", "## 99.0"), 2),
        ("changelog: a new bullet",
         edit("CHANGELOG.md", "## Unreleased\n", "## Unreleased\n- x\n"), 0),
        ("manual title page version",
         edit("linguexx-doc.tex", date, date.replace(ver, "99.0")), 2),
        # the release build
        ("make ctan", bash("make ctan"), 2),
        ("make ctan-tds", bash("cd x && make ctan-tds"), 2),
        ("ctan.py build", bash("python3 tools/ctan.py --tds"), 2),
        ("ctan.py --check", bash("python3 tools/ctan.py --check"), 0),
        ("make manual", bash("make manual"), 0),
        ("LXX_X=1 make ctan", bash("LXX_X=1 make ctan"), 2),
        # mentioning the target is not running it: both were refused by the
        # first version of this guard, while it was being documented
        ("a heredoc that names it",
         bash("python3 - <<'EOF'\ns = 'the build (`make ctan`, "
              "`tools/ctan.py` without --check)'\nEOF"), 0),
        ("a commit message that names it",
         # (the commit gate reads the real stamp; skip it, it is not tested)
         bash("LXX_SKIP_GATE=1 git commit -m 'refuse make ctan unasked'"), 0),
        # the switch: making it is refused, looking at it is not
        ("touch of the switch", bash(f"touch {SWITCH}"), 2),
        ("redirect into the switch", bash(f": > {SWITCH}"), 2),
        ("Write of the switch", write(SWITCH, ""), 2),
        ("ls of the switch", bash(f"ls -l {SWITCH}"), 0),
        ("grep for the switch", bash("grep -n release-ok guard.py"), 0),
        # machine notes
        ("machine path into CLAUDE.md",
         edit("CLAUDE.md", "## Environment\n",
              "## Environment\n- TeX in ~/texlive/2026/bin/x86_64-linux\n"), 2),
        ("ordinary CLAUDE.md edit",
         edit("CLAUDE.md", "## Environment\n", "## Environment\n- note\n"), 0),
        ("machine path elsewhere is fine",
         write("CLAUDE.local.md.test", "~/texlive/2026/bin"), 0),
    ]


def report(name, got, want, err=""):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got} (want {want})"
          + ("" if ok else f"\n     {err.strip()[:200]}"))
    return not ok


def main():
    fails = 0
    with tempfile.TemporaryDirectory() as d:
        state = Path(d)
        for name, ev, want in cases():
            fails += report(name, *run(ev, state)[:1], want)
        # the switch, made the way the user makes it
        (state / "release-ok").touch()
        sty, ver = sty_line()
        for name, ev in (
                ("bump with the switch on",
                 edit("linguexx.sty", sty, sty.replace(f"v. {ver}]",
                                                       "v. 99.0]"))),
                ("make ctan with the switch on", bash("make ctan"))):
            fails += report(name, run(ev, state)[0], 0)
        # ... and lapsed
        os.utime(state / "release-ok", (0, 0))
        fails += report("a lapsed switch", run(bash("make ctan"), state)[0], 2)
    print("all guard cases pass" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
