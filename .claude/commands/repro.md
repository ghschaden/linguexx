---
description: Build a minimal repro of a linguexx construct and show what it renders
argument-hint: <LaTeX body, e.g. \ex. \gll AAA BBB \\ aaa bbb \\>
allowed-tools: Bash(.claude/tools/lxx:*)
---

Build this body as a minimal document on the suite's own preamble:

    .claude/tools/lxx snippet --show -c '$ARGUMENTS'

If it fails, the digest under the FAILED line is the error; give it
verbatim with its `l.NNN` line. If it compiles, show the text layer, and
when the question is about position or shape, follow up with
`.claude/tools/lxx words <pdf>` for coordinates or
`.claude/tools/lxx png <pdf> --crop` and LOOK at the image -- CLAUDE.md
does not accept a conclusion drawn from an exit code.

Add `--preamble _preamble-tagged` (or -ua, -beamer, -langsci, -gb4e) when
the construct is about tagging, overlays or another front-end.
