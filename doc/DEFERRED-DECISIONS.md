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

---

## A sub-example part on `\ref`

*Raised on 2026-08-27, alongside the `\xspace` fix to the relative
references; deferred rather than implemented.*

**Current behaviour.** `\ref` takes a label and nothing else. Written
`\ref{ex:10}[a]`, the bracket group is not an argument, it is text, and the
page gets `(10)[a]`. The supported ways to spell "letter a of example 10"
are `\sublabel{ex:10a}` with an ordinary `\ref` to it, and — for a
*relative* reference only — `\Last[a]` and its family
(`linguexx.sty:1734`ff), whose part is joined with `\firstrefdash` and
lands inside the parentheses.

So there is an asymmetry: a relative reference can name a sub-example
without a label, a `\ref` cannot. That asymmetry is the whole of the case
for changing this, and it is a real one.

**Why nothing was patched.** Not because it is hard. A working spelling is
two lines, and it was prototyped and confirmed before this entry was
written:

```latex
\newcommand\prefsub[2]{\pref{#1}\firstrefdash#2}
\newcommand\refsub[2]{(\prefsub{#1}{#2})}
```

That reuses the machinery `\refrange`/`\prefrange` already rests on
(`linguexx.sty:3202-3203`): suppress the parentheses with `\pref`,
decorate, put the parentheses back. It needs no `.aux` change, it inherits
`[legacy]`'s `(10-a)` for free because it goes through `\firstrefdash`,
and a braced argument cannot be confused with anything in running text.

What is undecided is whether the package should encourage the thing at
all, and — if it should — under which of two spellings, which are not
variants of one feature but two different features:

1. **`\refsub{ex:10}{a}`**, the two lines above. Cheap, contained, and
   named beside `\refrange`, which does the same kind of job.

2. **`\ref{ex:10}[a]`**, the spelling that was actually asked for, because
   it is what `\Last[a]` looks like. This one is not cheap, and its cost is
   not in the typing:

   - *The part has to be spliced, not appended.* The `.aux` stores a label
     as `{\theExLBr 10\theExRBr }` — see any `\newlabel` line in
     `linguexx-doc.aux` — so `\ref` hands back a finished `(10)`. Putting
     the letter inside the parentheses means turning `\theExNo`,
     `\theSubExNo` and `\theSubSubExNo` into macros carrying a hole for it,
     which changes the recorded label format and breaks a stale `.aux` for
     one run.
   - *It applies to every label in the document, not to example labels.*
     `\ref{sec:intro}[a]` has no hole for the part to land in. Silently
     dropping it, printing it outside, and raising an error are all
     defensible, and they are three different promises.
   - *It puts linguexx into `\ref`.* Today the package only ever *uses*
     `\ref`; hyperref, cleveref, varioref and nameref all wrap it, and
     linguexx is currently immune to the order they load in. Redefining it
     forfeits that immunity for a convenience.
   - *The syntax is ambiguous in prose.* A trailing `o` argument skips
     spaces, so `see \ref{ex:1} [Chomsky 1981]` loses its bracket group.
     `!o` (no space skipping) narrows this to the adjacent case but does
     not close it, and the failure is silent — the same shape as the
     `(1)[b]` bug that `tests/relrefs.tex` now guards against.

**The argument on the other side**, which is why this is not simply "no":
the manual's "Relative references" subsection (inside "Cross-references")
already tells the reader to prefer `\sublabel` + `\ref`, because a hand-typed
letter does not survive renumbering — insert a sub-example above it and the
reference goes quietly wrong. Both spellings above make that habit easier
to reach for. `\Last[a]` has the same defect, but it is inherited from
`linguex` and kept for compatibility; a `\ref` part would be linguexx
choosing it.

**What would decide it.** A document that wants the sub-part on a `\ref`
often enough that adding the `\sublabel` is the friction — that is, a real
case where the target genuinely cannot be labelled (someone else's file, a
generated example, an example one refers to at several letters), rather
than a case where labelling it was merely two keystrokes further away. If
that case shows up, spelling 1 is the answer; spelling 2 needs, in
addition, a decided answer for a `\ref` to a non-example label.

**If it is ever patched:** add `\refsub`/`\prefsub` next to
`\refrange`/`\prefrange`, document them in the same subsection, and test
them in `tests/refs.tex` under both modes — the `[legacy]` value of
`\firstrefdash` is the half a test would otherwise miss. Do not redefine
`\ref` to get there.
