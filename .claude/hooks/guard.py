#!/usr/bin/env python3
"""Four guards, each about something that has actually gone wrong here.

CLAUDE.md calls the verification non-negotiable, and the one thing that
makes a rule like that fail is that it is remembered rather than checked.
What follows checks it, in the two places the claim gets made -- a commit,
and a turn that says the work is done -- and gets out of the way otherwise.

  PreToolUse/Bash   a commit whose sources changed since the last green run
  PreToolUse/Read   a large TeX .log read whole (40 kB for ~5 useful lines)
  Stop              a turn that CLAIMS completion on an unverified tree
  PostToolUse/Bash  a raw `python3 tests/runtests.py` that came out green:
                    record the stamp, so the documented command and the
                    harness are equally good ways to earn one

None of these is a policy. The commit passes with LXX_SKIP_GATE=1 in front
of it, and the Stop guard speaks once per state of the tree -- it is there
to catch a slip, not to hold a conversation hostage.
"""
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True          # no __pycache__ in the repo
ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".claude" / ".state"
NAGGED = STATE / "stop-nagged"
LOG_LIMIT = 6000                        # bytes; below this, read it directly

#: What a turn sounds like when it hands work back.  Deliberately about
#: DELIVERY, not about progress: "I fixed the brace" ends a turn, "next I
#: will fix the brace" does not, and a guard that cannot tell them apart
#: would fire on every turn of a long job and be turned off within a day.
CLAIM = re.compile(
    r"\b(all green|suite is green|tests? (?:all )?pass(?:es|ed)?"
    r"|no regressions?|done\b|finished|complete[d]?\b|ready (?:to|for)"
    r"|works now|working now|fixed\b|that fixes|should be good"
    r"|delivered|ship(?:ped)?)\b", re.I)


def lxx():
    """The harness as a module: its source_hash is the one the stamp uses."""
    import importlib.util
    import importlib.machinery
    path = str(ROOT / ".claude" / "tools" / "lxx")
    spec = importlib.util.spec_from_loader(
        "lxx", importlib.machinery.SourceFileLoader("lxx", path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def block(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)                         # 2 = deny; stderr goes back to Claude


def unverified():
    """(True, why) if the tree has changed since the last green suite run.

    With no stamp at all, only a MODIFIED source counts: a fresh clone that
    nobody has touched has nothing to verify, and blocking there would fire
    on a session that only read the code.
    """
    import subprocess
    m = lxx()
    if not m.STAMP.exists():
        r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain",
                            "--", "linguexx.sty", "tests"],
                           capture_output=True, text=True)
        if r.stdout.strip():
            return True, "no green suite run is on record"
        return False, ""
    try:
        st = json.loads(m.STAMP.read_text())
    except Exception:
        return True, "the green-run stamp is unreadable"
    if st.get("hash") != m.source_hash():
        return True, ("linguexx.sty or a test case has changed since the "
                      f"last green run ({st.get('when', '?')})")
    return False, ""


def last_assistant_text(transcript):
    """The text of the message this turn is ending on, or ''."""
    if not transcript:
        return ""
    p = Path(transcript)
    if not p.exists():
        return ""
    try:
        lines = p.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    for ln in reversed(lines[-400:]):
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if ev.get("type") != "assistant":
            continue
        content = (ev.get("message") or {}).get("content") or []
        if isinstance(content, str):
            return content
        text = " ".join(c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text")
        if text.strip():
            return text
    return ""


# --------------------------------------------------------------------------
def pre_tool(ev):
    tool, inp = ev.get("tool_name", ""), ev.get("tool_input") or {}

    if tool == "Read":
        p = Path(str(inp.get("file_path", "")))
        if p.suffix == ".log" and p.exists() and p.stat().st_size > LOG_LIMIT:
            block(f"{p.name} is {p.stat().st_size // 1024} kB of TeX log; "
                  f"reading it whole costs a lot of context and says little.\n"
                  f"Run instead:  .claude/tools/lxx log {p}\n"
                  f"(that prints every error with its l.NNN line, the "
                  f"warnings, and a box count; grep the file directly if you "
                  f"need something it drops.)")
        return 0

    if tool != "Bash":
        return 0
    cmd = str(inp.get("command", ""))
    if not re.search(r"(^|[;&|]|\s)git\s+(-C\s+\S+\s+)?commit(\s|$)", cmd):
        return 0
    if "LXX_SKIP_GATE=1" in cmd:
        return 0
    bad, why = unverified()
    if not bad:
        return 0
    block(f"Commit held back: {why}.\n"
          f"CLAUDE.md makes this non-negotiable -- run\n"
          f"    .claude/tools/lxx test        (all three engines, ~70s)\n"
          f"or  .claude/tools/lxx verify      (suite + ua-demo veraPDF + manual)\n"
          f"and commit again once it is green.\n"
          f"To commit anyway, put LXX_SKIP_GATE=1 in front of the git command.")
    return 0


def post_tool(ev):
    """A green unfiltered runtests.py run earns the same stamp as `lxx test`.

    Without this, the documented command in CLAUDE.md leaves no record, and
    the two guards above then hold back a commit on a tree whose suite has
    just passed -- a false alarm, and the fastest way to teach someone to
    reach for the override.  The evidence is identical either way: an
    unfiltered run of the whole suite that printed "All green."
    """
    if ev.get("tool_name") != "Bash":
        return 0
    inp = ev.get("tool_input") or {}
    cmd = str(inp.get("command", ""))
    if "runtests.py" not in cmd or "lxx" in cmd:
        return 0
    if re.search(r"\s(-k|--filter|-e|--engine)(\s|=)", cmd):
        return 0                        # a partial run proves less
    cwd = str(ev.get("cwd") or ROOT)
    if not cwd.startswith(str(ROOT)):
        return 0
    resp = ev.get("tool_response")
    out = ""
    if isinstance(resp, dict):
        out = str(resp.get("stdout", "")) + str(resp.get("stderr", ""))
    elif resp:
        out = str(resp)
    if "All green." not in out:
        return 0
    m = lxx()
    summary = next((l.strip() for l in out.splitlines()
                    if "assertions passed across" in l), "green")
    m.write_stamp({"scope": "suite (raw runtests.py)", "summary": summary})
    return 0


def stop(ev):
    """Refuse to end a turn that claims completion on an unverified tree.

    Three things keep this from becoming noise: it needs a completion claim
    in the message actually being sent, it never fires twice for the same
    state of the tree, and stop_hook_active means an already-blocked turn is
    let through rather than looped.
    """
    if ev.get("stop_hook_active"):
        return 0
    bad, why = unverified()
    if not bad:
        return 0
    text = last_assistant_text(ev.get("transcript_path"))
    m = CLAIM.search(text)
    if not m:
        return 0
    h = lxx().source_hash()
    if NAGGED.exists() and NAGGED.read_text().strip() == h:
        return 0                        # said once for this tree; enough
    STATE.mkdir(parents=True, exist_ok=True)
    NAGGED.write_text(h)
    block(f"That turn reports the work as done ({m.group(0)!r}), but {why}.\n"
          f"Run  .claude/tools/lxx test  (~70s, all three engines) -- or "
          f"`lxx verify` if a tagging or manual change is involved -- and say "
          f"what it actually reported.\n"
          f"If the user asked you to skip verification, or the change cannot "
          f"be tested, say THAT plainly instead of reporting success: an "
          f"exit code is not a result here.\n"
          f"(This fires once per state of the tree; it will not interrupt "
          f"you again until something changes.)")
    return 0


def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    kind = ev.get("hook_event_name")
    if not kind:
        kind = ("PostToolUse" if "tool_response" in ev
                else "PreToolUse" if "tool_name" in ev else "Stop")
    try:
        if kind == "PreToolUse":
            return pre_tool(ev)
        if kind == "PostToolUse":
            return post_tool(ev)
        if kind in ("Stop", "SubagentStop"):
            return stop(ev)
    except SystemExit:
        raise
    except Exception as e:
        # A broken guard must not break the session: say so on stderr and
        # let the action through.  A hook that fails closed on its own bug
        # is worse than the slip it was written to catch.
        print(f"lxx guard: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
