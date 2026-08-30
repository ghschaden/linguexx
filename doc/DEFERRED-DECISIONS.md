# Deferred decisions

Questions this package has deliberately not answered. Each entry records
what the current behaviour is, why nothing was patched, and what would have
to be true before patching is the right move. An entry is here because the
*semantics* are undecided, not because the work is hard.

The rule for all of them: do not "fix" these in passing. A drive-by patch
picks one of the available semantics by accident, and the accident is then
what the package has promised.

Code is pointed at by NAME here, not by line number. Line numbers were
tried and rotted twice in a single afternoon: every insertion into
`linguexx.sty` moves everything below it, so a citation is stale the next
time anyone commits, and a stale citation in a file whose whole purpose is
to be read later is worse than none. Names survive, and `grep` finds them.

---

## Examples in a `minipage` footnote

*Raised by the code review of 2026-07-30 (item D2); deferred there.
Revisited 2026-08-30 with evidence from the rest of the family (below), and
still deferred.*

**Current behaviour.** Examples inside a footnote of a `minipage` are
numbered on the main `ExNo` series, not on the footnote series `FnExNo`.

**Why.** `\footnote` inside a `minipage` routes through `\@mpfootnotetext`,
which is a different command from the ordinary `\@footnotetext`. linguexx
hooks only the latter (in the `\AtBeginDocument` that also sets
`\@noftnotefalse`, and rebinds `\@footnotetext`), so the flag that switches an example
onto the footnote series is never cleared in the minipage case.

Patching `\@mpfootnotetext` the same way is a two-line change. That is not
the problem. The problem is that there are three defensible answers, and
nothing that chooses between them — the family evidence recorded below
raises the cost of moving off the current one without saying it is right:

1. share `FnExNo` with ordinary footnotes — but two minipages on a page
   then interleave their numbering with each other and with the page's
   real footnotes;
2. stay on the main series, as now — defensible precisely because a
   minipage footnote is often not a footnote in the document's sense;
3. a series per minipage — cleanest in principle, and the only one that
   needs new user-facing syntax to reference an example across the
   boundary.

**What the rest of the family does** *(checked 2026-08-30, while auditing
`langsci-gb4e` for the `[langsci]` option)*. All four packages behave the
same way here, and all four for the same reason: each hooks
`\@footnotetext` and none hooks `\@mpfootnotetext`.

| package | ordinary footnote | minipage footnote |
| --- | --- | --- |
| `linguexx` | `(i)` — footnote series | `(2)` — main series |
| `langsci-gb4e` | `(i)` — footnote series | `(2)` — main series |
| `linguex` | `(i)` — footnote series | `(2)` — main series |
| `gb4e` | `(1)` — no footnote series at all | `(2)` — main series |

Established by rendering the same four-example document against each
package and reading the numbers off the page, not by reading the sources.
In every case the main-text examples on either side of the minipage come
out `(1)` and `(3)`, so the minipage-footnote example does not merely
*look* like a main-series example: it consumes a main-series number. The
saved hooks are `\oldFootnotetext` in `langsci-gb4e` (beside its `fnx`
counter), `\predefinedfootnotetext` in `linguex` and
`\@gbsaved@footnotetext` in `gb4e`; `grep` for those names to re-check
this when any of them is updated.

That is weaker evidence than the table looks, and it cuts both ways.

*It is not a precedent in the sense of a decision.* Three packages landing
on option 2 by the same omission is not three packages choosing option 2.
Nobody weighed the answers above; each hooked the command it knew about,
and `gb4e` — which has no footnote series at all — cannot be said to have
an opinion on which series a footnote example belongs to. What the
uniformity does establish is the other half of the original sentence: there
*are* existing documents built against this behaviour, across the whole
family, so the "no expectations would be violated" half was simply wrong.

*And it now costs more to change than it did.* When this entry was written
linguexx had no reason to match anyone here. `[langsci]` gives it one:
inside that option linguexx is meant to be a drop-in for `langsci-gb4e`,
and a document converting to it one example at a time is checked by
diffing its output against its own previous run. Renumbering a
minipage-footnote example would be a divergence from the package being
emulated, showing up in exactly the shape the migration promise is about —
a number moving for a reason that is not the conversion. This argues for
option 2, but on compatibility grounds only; it says nothing about which
semantics is right, and it would not apply to a document not using
`[langsci]`.

The maintainer's reading, recorded 2026-08-30 when the same behaviour came
up as a candidate defect in the `langsci-gb4e` audit: this looks like a
typesetting decision rather than an error. It was struck from that audit's
findings for that reason.

**What would decide it.** The criterion is unchanged — a real document that
puts numbered examples in a minipage footnote and *cares* which number they
get. What changed on 2026-08-30 is what a patch would have to overcome, not
what would justify one. The family evidence does not supply that document;
it shows only that nobody has been bothered enough to hook the other
command. Until such a document turns up the behaviour is documented rather
than changed: see the manual's "Notes and limitations" (§10), which tells
the reader to put the examples outside the minipage if the numbering
matters. If one does turn up, note that the compatibility argument above
binds only `[langsci]`, so "change it everywhere" and "change it except
under `[langsci]`" are then two different proposals, and the second is a
fourth answer this entry did not originally list.

**If it is ever patched:** the change is to hook `\@mpfootnotetext`
alongside `\@footnotetext`, and it needs a test case, since nothing in
`tests/` currently exercises a minipage footnote at all. A test is worth
adding *before* anyone patches it, pinning the present numbering: the
behaviour is deliberate-by-deferral rather than deliberate-by-choice, which
is exactly the kind that gets changed by accident in the course of doing
something else. Such a test asserts the status quo, it does not endorse it,
and whoever settles this entry should expect to rewrite it.

---

## A sub-example part on `\ref`

*Raised on 2026-08-27, alongside the `\xspace` fix to the relative
references; deferred rather than implemented.*

**Current behaviour.** `\ref` takes a label and nothing else. Written
`\ref{ex:10}[a]`, the bracket group is not an argument, it is text, and the
page gets `(10)[a]`. The supported ways to spell "letter a of example 10"
are `\sublabel{ex:10a}` with an ordinary `\ref` to it, and — for a
*relative* reference only — `\Last[a]` and its family (defined beside
`\lx@setrelsub`), whose part is joined with `\firstrefdash` and
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

That reuses the machinery `\refrange`/`\prefrange` already rests on:
suppress the parentheses with `\pref`,
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
by `\__lxp_buildalt:NN`, which runs `\text_purify:n`
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

**Current behaviour.** `\theHExNo` is `lxex.<ExNo>`, built from the
printed counter and nothing else, so two examples that carry
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
the per-chapter reset is linguex's convention and the `\@addtoreset` in
the counters section reproduces it deliberately -- but `\setcounter{ExNo}{0}` anywhere does the
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

**If it is ever patched:** four places spell that anchor and all four have
to change together. `\theHExNo` and `\lx@Hexstem` are what hyperref reads;
`\lx@Hexname`/`\lx@Hfnexname` beside them spell the same name for a number
the counter has not reached, which is what a relative reference needs; and
`\lx_relref_name:` builds it again for the anchors linguexx places itself,
in the documents where hyperref's implicit ones are switched off (beamer).
That fourth one arrived after this entry was first written and was missing
from it for a commit or two -- which is the argument for `grep` over a list.

The ambiguity guard in the relative-reference code should stay either way:
it is about what the `.aux` recorded, so it keeps working whatever the
names become, and it is the only thing that would notice if a new recipe
collided too. `tests/relreflinks-reset.tex` asserts the engine's
duplicate-destination warning on pdflatex and lualatex, so it fails loudly
once the collision is gone -- which is the point at which the withheld link
there becomes needless rather than saved. (It asserts it for real now. It
was first written as a `check(True, ...)` guarded by the very condition it
claimed to test, so this paragraph described something that could not
happen.)

---

## Handing `\gll` to another package: `[nocgloss]`

*Raised on 2026-08-29, while implementing the rest of the `langsci-gb4e`
surface under `[langsci]`; accepted as an option name and not implemented.*

**Current behaviour.** `\usepackage[nocgloss,langsci]{linguexx}` is accepted
and warns that it has no effect. Everything glossing stays defined.

**Why.** In `langsci-gb4e` the option means something narrow: that file
bundles an adapted copy of `cgloss`, and `nocgloss` stops the copy being
read so that a document can load a different glossing package and have it
own `\gll`. There is no bundled copy here to withhold. The glossing *is* the
package: `\exg.` and `\ag.`–`\fg.` expand into it, `\altg` occupies two of
its tiers through a cross-tier protocol, `\GlossTierLang`, `\GlossTransLang`
and `\lpzg` decorate its output, and the whole tagged word-bundle structure
— the thing that makes a gloss read in the right order to a screen reader —
is built inside `\lx@gloss@multi`.

So the option cannot be honoured by not defining four macros. Each of the
following needs an answer, and each has more than one defensible one:

1. `\exg.` and `\ag.`–`\fg.` expand to `\gll`. Do they become errors naming
   the option, keep working against the foreign `\gll` (whose argument
   syntax may differ), or stop being defined?
2. `\altg` needs the tier machinery, not merely the user command. Does
   `[nocgloss]` take `\altg` with it? It is not a glossing command in the
   `cgloss` sense, and a document may want it and a foreign glosser both.
3. `\lpzg` and `\lpzglist` are useful outside a gloss and are wired into the
   tagging. They would presumably stay — but then `\lpzg` inside a foreign
   `\gll` produces a Span this package did not open.
4. The PDF/UA promises in the README are made about *this* glossing engine.
   With another package's output in the tree, they are no longer this
   package's to make, and nothing would say so.

**What would decide it.** A real document that wants `linguexx` for its
examples and a different package for its glosses, and that says which of the
four it expects. Until then the option reports rather than guesses: a
warning costs a line in the log, and a wrong answer to (1)–(4) would be a
silent change in what a gloss means.

**If it is ever implemented:** the seam is `\lx@gloss@multi` and the user
commands immediately below it (`\gll`, `\glll`, the `\gllll`…`\gllllllll`
family, `\gl`…`\endgl`, `\glt`). `\lx@glosshead`, which is what the `\exg.`
shorthands go through, is the one that decides (1). Note that `\altg`'s
two-call protocol reads `\g__lxp_altg_role_int` across tiers of the same
gloss and would have nothing to synchronise against.
