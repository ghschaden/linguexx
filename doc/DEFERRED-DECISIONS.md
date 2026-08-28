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
hooks only the latter (`linguexx.sty:270`, inside the `\AtBeginDocument`
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
(`linguexx.sty:1983`ff), whose part is joined with `\firstrefdash` and
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
(`linguexx.sty:3691-3692`): suppress the parentheses with `\pref`,
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

---

## What a nested `\altn` should sound like, and where it belongs in the tree

*Found on 2026-08-27, while checking whether the judgment-gutter work had
made nested stacks unsafe. It had not — but the check turned this up.*

**Current behaviour.** A stack inside a stack —

```latex
\altn[l]{aa}{*bb \altn[l]{xx}{*yy} cc}
```

— prints correctly. Both stacks are drawn, both braced, the inner one set
inside the outer's second row, and nothing about the printed page is
wrong. What is wrong is the outer stack's *spoken* form. Under active
tagging each stack is wrapped in a `Span` carrying an `/Alt` string built
by `\__lxp_buildalt:NN` (`linguexx.sty:2995`), which runs `\text_purify:n`
over each alternative so that formatting is stripped for speech. A nested
`\altn` purifies to its own source text, brackets and all:

```
outer /Alt:  "aa or *bb [l]xx*yy cc"      <- wrong
inner /Alt:  "xx or *yy"                  <- right
```

So a screen reader announces the optional argument (`[l]`) as if it were
part of the example, and runs the inner alternatives together with no
"or" between them.

The structure tree makes it worse, and not in the way one would guess.
The two `Span`s are **siblings, not parent and child** — the inner stack
is built while the outer's box is being filled, so its marked content is
closed before the outer `Span` is ever opened (the outer's is opened at
emit time, around `\box_use:N`). `pdfinfo -struct-text` on the example
above gives, in reading order:

```
P
  "OUT"
  Span ["xx or *yy"]        <- the INNER stack, announced first
    "xx*yy"
  "cc"                      <- inside the outer's second row, but in
  Span ["aa or *bb [l]xx*yy cc"]   neither Span
    "aa*bb"
  "END."
```

Three things are wrong there and only the first is about wording. The
reading order is inverted: the inner stack is announced before the outer
one that visually contains it. `cc`, which belongs to the outer's second
alternative, is emitted between the two `Span`s and so sits inside
neither. And because the `Span`s are siblings rather than nested, both
`/Alt` strings are spoken, so the inner alternatives are announced twice
— once on their own, correctly, and once mangled inside the parent's
string.

**Why this survives every check.** veraPDF passes it — `ua2`, `wt1a` and
`wt1r` all PASS on a document containing the example above. An `/Alt`
string that is present and well-formed satisfies the specification no
matter what it says, and two sibling `Span`s in an unhelpful order are
perfectly valid: nothing in PDF/UA requires reading order to match what
the eye sees. The suite misses it from the other side — every assertion
in `tests/` about a stack measures where the ink landed, and the ink is
right. Nothing currently reads an `/Alt` string or walks the tree of a
nested stack at all. This is the case the notes in `CLAUDE.md` describe,
where the validator and the structure checks are complementary and here
neither is enough, because the defect is in what the tree *says* rather
than in whether it is well formed.

**Why nothing was patched.** The mechanism is not the hard part —
`\__lxp_buildalt:NN` could recognise a nested call and recurse. The
question is what the result should say, and there are at least three
defensible answers with no evidence to choose between them:

1. **Flatten** into the parent's list: "aa, or bb xx or yy cc". Reads as
   one list, but silently claims a structure the author did not write, and
   the nesting — which is the whole point of writing it that way — is lost
   to a listener.
2. **Omit** the nested stack from the parent's string and let the inner
   `Span` speak for itself. Correct in that nothing is said twice, but the
   parent's alternative then has a hole in the middle of it.
3. **Announce the nesting**: "aa, or bb, one of xx or yy, cc". Truthful,
   and the only one that conveys what is on the page, but it invents
   wording the package would then have to own in every language a document
   might be in — and `/Alt` has no language machinery behind it here.

There is also a prior question: whether nested stacks should be supported
at all. `\altg` already documents that alternatives cannot spread over
three tiers, and a stack inside a stack is a rare enough construction that
"say it in two examples instead" may be the better advice.

**What would decide it.** A document that nests stacks *and* is meant to
be read aloud — the two together, since either alone is served by what is
there now. Failing that, a screen-reader convention for nested inline
alternatives that the package could follow rather than invent.

**If it is ever patched:** the `/Alt` wording is `\__lxp_buildalt:NN`
alone, but the reading order is not — that one is about when the outer
`Span` is opened relative to the box it wraps, which is the same
open-at-the-wrong-moment hazard the tagging notes describe, and it cannot
be fixed by changing a string. Decide the wording question first; the
ordering question may well answer itself by making the inner stack a
child, at which point only one `/Alt` is spoken and the flatten-or-omit
choice above changes shape. It needs a test that reads the `/Alt` strings
out of the PDF rather than asserting on geometry — `tests/` has no such assertion yet, and the one
written to find this uses `qpdf --qdf --object-streams=disable` to get at
them, since they are inside compressed object streams. Note also that the
inner `Span` is not the thing to change: it is already correct.

---

## Two examples, one hyperref anchor, when the counter is reset

*Found on 2026-08-28, while making the relative references clickable. The
links work around it; nothing about the anchors themselves was changed.*

**Current behaviour.** `\theHExNo` is `lxex.<ExNo>` (`linguexx.sty:303`),
built from the printed counter and nothing else, so two examples that carry
the same number claim the same hyperref anchor. hyperref keeps the first
destination of a name and drops the rest, with a warning from pdfTeX and
LuaTeX and none at all from `xdvipdfmx`. A `\label` on the second example
therefore links to the first:

```latex
\documentclass{book}
\usepackage[legacy]{linguexx}\usepackage{hyperref}
\begin{document}
\chapter{One}   \ex.\label{c1} First of chapter one.
\chapter{Two}   \ex.\label{c2} First of chapter two.
\ref{c1} \ref{c2}      % both jump to chapter one
\end{document}
```

`[legacy]` in a class with chapters is the case that arrives by itself --
the per-chapter reset is linguex's convention and `linguexx.sty:238`
reproduces it deliberately -- but `\setcounter{ExNo}{0}` anywhere does the
same thing in any class.

The printed number is right in every case. Only the destination is wrong,
which is why the whole suite passed over it: this is the same shape as the
footnote sub-example collision fixed in v1.2, one level up, and it was found
the same way -- by reading the anchors rather than the page.

**What the relative-reference links do about it.** They refuse to link. An
anchor that two examples recorded is marked ambiguous in the `.aux` and
treated exactly like one no example recorded: the number prints as before,
no link is made, and the reference is reported in its own words at the end
of the run (`tests/relreflinks-reset.tex`). That is a promise about the new
links only -- linguexx adds no *second* wrong jump to a document that
already has one -- and deliberately not a fix.

**Why nothing was patched.** The mechanism is easy and the semantics are
not. Three answers, and the cheapest one is not the best:

1. **Carry the chapter**, `lxex.<chapter>.<ExNo>`, whenever linguexx is the
   one that made ExNo reset. Two lines, and it covers the case that arrives
   by itself. It does nothing for `\setcounter{ExNo}{0}`, or for a document
   that adds its own `\@addtoreset`, so it makes the failure rarer and no
   less silent -- arguably worse, since a rare silent failure is the kind
   nobody looks for.
2. **Make the anchor independent of the printed number** -- a serial that
   counts examples through the document, reset by nothing. Correct by
   construction and immune to every reset, but the anchor stops being
   readable, and the `.aux` of an existing document names anchors that the
   next run will not create.
3. **Leave the anchors and report the collision**, as the links now do, but
   for `\ref` as well: one warning naming the examples that share a
   destination. Fixes nothing and tells the author exactly what is wrong,
   which for a defect this rare may be worth more than a silent renaming.

All three change what `\theHExNo` records or what the package says about it,
and (1) and (2) invalidate a stale `.aux` for one run -- the same cost the
sub-part-on-`\ref` entry above weighs, and the reason neither was settled in
passing.

**What would decide it.** A document that resets ExNo *and* is read on
screen: the two together, since the collision costs nothing on paper. If it
is a `[legacy]` book, (1) is enough and cheap; if the reset is the author's
own `\setcounter`, only (2) is, and then the question is whether an
unreadable anchor is a price worth paying for a defect that has been in the
package since `\theHExNo` was written.

**If it is ever patched:** the anchor is `\theHExNo` and `\lx@Hexstem`
(`linguexx.sty:303-304`), and `\lx@Hexname`/`\lx@Hfnexname` beside them have
to be changed in step, since they spell the same name for a number the
counter has not reached. The ambiguity guard in the relative-reference code
should stay either way: it is about what the `.aux` recorded, so it keeps
working whatever the names become, and it is the only thing that would
notice if a new recipe collided too. `tests/relreflinks-reset.tex` asserts
the duplicate-destination warning on the engines that emit it, so it fails
loudly once the collision is gone -- which is the point at which the withheld
link there becomes needless rather than saved.
