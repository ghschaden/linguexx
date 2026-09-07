# .claude/ — local agent harness for linguexx

Not part of the package and not distributed. Everything here exists to make
one agent's loop cheaper: fewer commands to get an answer, and far less of
the answer spent on output nobody reads.

    tools/lxx          the harness (see CLAUDE.md, or `lxx -h`)
    hooks/guard.py     refuses a commit on an unverified tree; stops a turn
                       that claims completion on one (once per tree state);
                       refuses to read a 40 kB TeX log whole; and records the
                       stamp when a raw runtests.py run comes out green
    agents/            log-triage (haiku), for scanning MANY logs at once
    commands/          /verify and /repro
    settings.json      wires the hook up and pre-approves the harness
    .state/            build dirs, renderings, and the green-run stamp
                       (regenerable; ignored)

`tools/lxx` imports `tests/runtests.py` rather than reimplementing any of
it: the pass counts, the PDF parsers and the geometry helpers all come from
the suite, so a helper here cannot quietly disagree with an assertion there.

The hook is read at session start. After changing `settings.json` or
`guard.py`, restart the session (or `/hooks`) before expecting the new
behaviour.

Committing this directory is a choice, not a requirement: nothing in the
package depends on it, and `CLAUDE.md`'s Harness section says to ignore it
when absent.
