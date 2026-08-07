# Deferred decisions

Questions this package has deliberately not answered. Each entry records
what the current behaviour is, why nothing was patched, and what would have
to be true before patching is the right move. An entry is here because the
*semantics* are undecided, not because the work is hard.

The rule for all of them: do not "fix" these in passing. A drive-by patch
picks one of the available semantics by accident, and the accident is then
what the package has promised.

---

## Examples in a `minipage` footnote

*Raised by the code review of 2026-07-30 (item D2); deferred there and
still deferred.*

**Current behaviour.** Examples inside a footnote of a `minipage` are
numbered on the main `ExNo` series, not on the footnote series `FnExNo`.

**Why.** `\footnote` inside a `minipage` routes through `\@mpfootnotetext`,
which is a different command from the ordinary `\@footnotetext`. linguexx
hooks only the latter (`linguexx.sty:257`, inside the `\AtBeginDocument`
that also sets `\@noftnotefalse`), so the flag that switches an example
onto the footnote series is never cleared in the minipage case.

Patching `\@mpfootnotetext` the same way is a two-line change. That is not
the problem. The problem is that there are three defensible answers and no
evidence for choosing between them:

1. share `FnExNo` with ordinary footnotes — but two minipages on a page
   then interleave their numbering with each other and with the page's
   real footnotes;
2. stay on the main series, as now — defensible precisely because a
   minipage footnote is often not a footnote in the document's sense;
3. a series per minipage — cleanest in principle, and the only one that
   needs new user-facing syntax to reference an example across the
   boundary.

`linguex` never answered this either, so there is no precedent to inherit
and no existing documents whose expectations would be violated.

**What would decide it.** A real document that puts numbered examples in a
minipage footnote and *cares* which number they get. Until then the
behaviour is documented rather than changed: see the manual's "Notes and
limitations" (§10), which tells the reader to put the examples outside the
minipage if the numbering matters.

**If it is ever patched:** the change is to hook `\@mpfootnotetext`
alongside `\@footnotetext`, and it needs a test case, since nothing in
`tests/` currently exercises a minipage footnote at all.
