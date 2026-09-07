---
description: Run the full pre-delivery gate (3 engines, ua-demo veraPDF, structure, manual)
allowed-tools: Bash(.claude/tools/lxx:*)
---

Run `.claude/tools/lxx verify $ARGUMENTS` and report the result.

Report the checklist as it comes back. If a step fails, do not summarise it
away: name the failing case and engine, and `.claude/tools/lxx log <case>`
for the reason before saying anything about a cause. Do not fix anything
unless asked -- this command is the gate, not the repair.
