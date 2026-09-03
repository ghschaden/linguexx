# Four things `expex` has: design notes

Prospective. Nothing here is implemented, and none of it is a commitment to
implement. Each section says what the feature is, where it would attach in
`linguexx.sty`, what it would do to the structure tree, what has to be
*decided* before anything is written, and what a test that could fail would
look like. The point is to make the cost visible while it is still cheap to
decide against.

Code is cited by NAME, never by line number — the same rule as
`CORE-API-PLAN.md`, and for the same reason: the numbers rot within an
afternoon and the names do not.

A **probe**, where the word is used below, is a throwaway document that
answers one question about behaviour: built outside the package, kept only
until it has answered, and never correct about anything it was not asked.
It is not a test case — a test lives in `tests/`, is wired into
`ASSERTIONS`, runs on every commit and must have a mutation that kills it —
and it is not a prototype, because none of it is meant to survive. It is
cheap precisely because it will be thrown away. Its failure mode is
over-reading one: a probe answers the question it was given, not the
question that should have been asked, and item 1 below records a case of
exactly that.

## Where the comparison came from

`expex` v4.x as installed on this machine:
`/usr/share/texmf-dist/tex/generic/expex/expex.tex` (1618 lines) and
`expex-demo.tex` (1037 lines). Read, not remembered. Every `expex` behaviour
below was checked in that source; where a key or macro is named, it is
named as `expex` spells it.

Two findings frame everything else.

**`expex` is key-value all the way down.** `\lingset{...}` carries about
seventy parameters, settable globally, per example (`\ex[...]`, `\pex[...]`)
or per gloss (`\begingl[...]`); `\definelingstyle{name}{...}` bundles a set
and `lingstyle=name` invokes it. `linguexx` configures through lengths and
macros plus package options; its four `keys_define:nn` groups (`lx/judge`,
`lx/lpzgcheck`, `lx/lpzglist`, `lx/mode`) are all internal. That difference
is the source of item 2 and colours items 1 and 4.

**`expex` has no accessibility layer at all.** Zero occurrences of `tagpdf`,
`DocumentMetadata`, `StructElem`, `/Alt` or "accessib" across all 2655 lines
of source and demo. This is not a criticism — `expex` is plain-TeX-based and
predates the LaTeX tagging project — but it means nothing below can be
imported as-is. Every one of these features has to answer a question `expex`
never had to ask, and for items 1 and 4 that question is the hard part.

## Summary

| | Feature | Cost | Blocking decision |
|---|---|---|---|
| 1 | Free translation *beside* the gloss | **done, v1.4** | — |
| 2 | Key-value façade and named styles | medium | the key names, which become API forever |
| 3 | Reference checking | medium | whether `\ref` itself is in scope |
| 4 | Named label types | medium | whether a type may change the *reference* format |

**Item 1 is implemented** as of v1.4 (`\GlossTransSide`); this section is
kept for the reasoning, and the block at its end records what the
implementation added to what was planned. Remaining order: **2, 3, 4**.

Original order: **2, 1, 3, 4**. Item 2 is the cheapest and the only one
that cannot touch the structure tree, and its key table is what item 1's
syntax question needs answering against. Item 1 is the one a reader would
notice every time, and on a slide it buys vertical space, which is the
scarce thing there. Item 4 is last because its blocking decision is the one
with an `.aux` consequence.

Item 3 was originally third-costed and put first, as a cheap way to find out
whether any of this is wanted. That was wrong, and the section says why: the
`expex` feature it was modelled on does not do the job it was credited with.
What replaces it is worth more and costs more.

---

## 1. Free translation beside the gloss

**What `expex` does.** `\lingset{glftpos=right}` puts the free translation
to the right of the interlinear grid instead of under it. The width is split
by `\ep@setssdims`: `ssratio` (default `.6`) of the available width goes to
the gloss, `sssep` (`2em`) separates the two, and the translation gets the
remainder with `ssrightskip` (`0pt plus 2em`). `\gl@wrap@right@begin` sets
`\hsize=\ssleftwd` and opens an `\hbox`; `\gl@wrap@right@ft` closes it and
sets the translation in a `\vtop` of width `\ssrightwd` beside it.

**Why want it.** A two-line gloss with a one-line translation wastes a lot
of vertical space, and on a slide vertical space is the scarce thing. This
is the item most likely to be missed in practice.

**The seam here.** `\lx@gloss@multi` sets the grid as a *paragraph* in the
current `\hsize` — columns are `\vtop`s separated by
`\penalty\lx@gl@colpenalty \hskip\GlossSep`, flowed `\raggedright` — and
ends it with `\par`. `\glt` is a separate command issued afterwards:

```
\newcommand\glt{\par\nobreak \GlossTransStyle
  \everypar{\everypar{}\lx@glt@langbegin}\ignorespaces}
```

It takes no argument. Its body runs to the end of the paragraph.

**That is the difficulty.** By the time `\glt` runs, the grid's paragraph
has been broken and contributed to the enclosing list; there is nothing left
to set beside. `expex` avoids it because *its* free translation is
delimited — `\gl@wrap@right@ft #1//` — so the translation is an argument and
both halves can be boxed. Four ways out:

1. **Delimit the translation**, `expex`-style: `\glt ... //`. Cheapest
   mechanically, and the ugliest — it changes what `\glt` means for every
   existing document, and `\glt` is inherited from `cgloss4e`, so the blast
   radius is wider than this package. There are 75 uses in this repo alone.
2. **An environment or a second command**, e.g. `\gltside{...}`, used
   *instead* of `\glt` when the side position is wanted. Additive; nothing
   existing changes; two names for one concept, and the argument must be
   `\long` to admit a `\par` — `expex` had to make exactly that fix ("made
   `\glft` a long definition to allow `\par`", its changelog, 2011).
3. **Tell `\gll` in advance** — a key on the gloss. It only chooses the
   layout; the translation's extent still has to be found, so underneath it
   collapses into (2) or (4). Worth having as a *spelling* on top of
   whichever is chosen, not as an answer.
4. **Shape the translation around a boxed grid**, requiring no new syntax at
   all: box the *grid* (which `\lx@gloss@multi` already knows the end of),
   place it, and let `\glt` set `\hangindent`/`\hangafter` so its paragraph
   hangs past it. `\glt` keeps taking no argument. A scratch probe got the
   two halves side by side with the short case degrading cleanly, which is
   what put this option on the list.

**Why (4) is not the answer, although it looked like it.** The probe's
appeal was "no new syntax", and an earlier draft of this section claimed for
it that the structure tree would be unchanged. That claim was wrong, and the
reason is the one thing this package cannot be relaxed about.

Under shaping the grid is a box placed *inside the translation's paragraph*.
The grid builds `Part → P → Span`s of its own, so that block structure ends
up inside the translation's `P`. This is the shape recorded in the version
history at v0.10/v0.11 — "a Span may not contain the Part/P that the math
tagging then builds", rejected by veraPDF — and it is the single entry in
CLAUDE.md's **Do Not** list. It may be escapable: `\tag_mc_end_push:` /
`\tag_mc_begin_pop:n` exists precisely to suspend an open MC around
something like this, and the package uses it everywhere. But "escapable with
the idiom that has broken compliance before" is not free, and only veraPDF
can say whether it worked.

The rest of shaping's fragility is ordinary but silent:

| | fails how | loud? |
|---|---|---|
| line count `⌈height/baselineskip⌉` | `\singlegloss`, `\small`, beamer's leading — off by one, so the box overlaps a line or an indent is wasted | **silent** |
| paragraph breaks across a page | the box stays on the first page, the indent continues on the next | **silent** |
| another user of `\hangindent` in the same paragraph | one parameter, last setter wins | silent |

In its favour, the package uses `\hangindent` and `\parshape` **nowhere**
(zero occurrences), so there is no internal conflict to inherit.

Option (2) fails differently: a boxed pair **cannot break across a page at
all**, which is an overfull vbox and therefore loud, and its argument needs
`\long`, which is a known and already-solved problem. Its tagging is clean —
two boxes, two sibling elements, emitted in reading order, the same shape
the gloss columns already have.

**So the trade is silent failures in the tagging and line-count layers
against loud ones in page-breaking, and for this package loud wins.** The
suite exists because every real bug in it compiled with zero errors. The
recommendation is (2), with (3) as its spelling if a key reads better than a
second command name.

**What it does to the structure tree.** With (2): reading order is
unchanged, because left-then-right *is* grid-then-translation, so
`LBody → Part(grid) , Part(translation)` still describes it. What must be
checked is that the two boxes do not become an untagged two-column artifact
and that the translation's `/Lang` (`\GlossTransLang`) still lands on the
right element. `examples/ua-demo.tex` would need a side-by-side gloss with
veraPDF run on it; `struct_label_depths` would catch a `Part` left open.

### Decisions taken, 2026-09-03

Three settled in conversation, and one thing that turned out not to be a
choice at all. Recorded so the next reader inherits the reasoning and not
just the outcome.

**Top-level examples only.** A side translation is refused below the top
level — `\lx@subdepth > 0` is a package error. The reasoning is under
"Sub-examples, and short ones" below; the short version is that the saving
does not exist there, the
measure is already reduced twice, and a split taken from the local
`\linewidth` puts every sibling's translation at a different x.

**`\exannot` is illegal on a gloss with a side translation.** Its column is
measured from `\columnwidth` (`\lx@annot@width:`), which is meaningless once
the grid has been narrowed, and making the two agree is real design for a
combination nobody has asked for. A package error, not a silent
reinterpretation.

**The layout is boxed, not shaped** — option (4) above, for the tagging
reason given there.

**And the thing that is not a choice: the decision has to be known BEFORE
the grid is typeset.** A first pass proposed `\gltrans{...}` as both the
translation *and* the signal — the command being the switch, so that there
is no separate state to leak. That cannot work, and the reason is worth
writing down because it is invisible from outside the engine:

> By the time `\gltrans` is read, `\lx@gloss@multi` has already set the grid
> as a full-width paragraph and `\par`-ed it into the enclosing list. There
> is nothing left to set beside.

`expex` knows early too, and the resemblance to its `\glft ... //` is what
misled the first pass: the delimiter there is about **capturing the
translation**, while the layout is chosen by `glftpos` on `\begingl`, and
`\gl@wrap@right@begin` sets `\hsize=\ssleftwd` *before* the grid is set.
Two different jobs that look like one.

The alternative — box the grid speculatively and hold it pending until
something says where it goes — means flushing a pending box at every exit an
example has. `\lx@glt@langend` is called from **nine** sites for exactly
that kind of obligation (`\lx@bodyend`, `\lx@zpop@one`, the `exe` and
`xlist` ends, and the five `xlist` variants), and the history records one of
them being missed: a `\glt` language Span "left the Span open across the
list close and failed veraPDF on all three profiles. Nothing showed on the
page and no structure assertion saw it." Nine flush points is nine chances
to repeat that.

Deciding early pays for itself elsewhere too. The `\exannot` prohibition can
then fire at the lift, inside `\gll`, naming the annotation — instead of a
flag that has to survive to the translation command and be cleared per
gloss, which is precisely the stale-stash bug `\l__lx_gl_annot_tl` produced
this week and that took a mutation to find. The top-level check happens at
the same moment, and the tagging emission point is known when the box is
built rather than when it is placed.

### Where the switch lives

| | | |
|---|---|---|
| (a) a key on the gloss, `\gll[side]` | the family is **eight** grid commands (`\gl`, `\gll`, `\glll`, `\gllll` … `\gllllllll`). Add it to one and it is inconsistent; add it to eight and every delimited signature grows a peek | weak |
| (b) **a declaration before the example** | no signature changes at all, applies to whichever gloss command was used, and matches the existing precedent — `\ExAnnotFit`, `\ExRaggedRight` and `\GlossPhantomAlign` are all group-scoped layout declarations | **chosen** |
| (c) a separate gloss command, `\gllside` | multiplies by eight | out |

So a declaration:

```latex
{\GlossTransSide   % name not settled
 \ex. ...
 \z.}
```

**Still open: whether it auto-resets at example end.** Leaving it to TeX
grouping is what every other layout declaration here does, and it is
predictable. Auto-resetting makes a leak impossible — and a leaked layout
flag is a silent defect, the shape of the `\altg` role toggle that "leaves
the toggle set, and every later `\altg` in the gloss takes the opposite
role". Against it: an explicit declaration cancelled by the machinery is
surprising, and it would make this switch behave unlike its three
neighbours.

### Still open

- ~~Whether the translation needs to be an argument at all.~~ **Answered by
  probe, 2026-09-03: it does not.** See "What the probe settled" below.
- ~~The name, if a translation command is needed after all.~~ Moot: no new
  command is needed.
- **What happens when there is no room** at top level — a slide, a
  `twocolumn` paper. Falling back to the below position with a warning is
  the recommendation: the author gets a document and the log says why it is
  not the one they asked for. Erroring is the alternative.
- **What happens when the translation is taller than the gloss.** `expex`
  lets its `\vtop` grow. Fine, but it should be stated rather than
  discovered.
- **`\altg`**, whose two-call protocol runs across tiers of one grid
  (`\g__lxp_altg_role_int`). Narrowing the grid does not disturb the
  protocol, but the brace geometry is measured from the stack's extents and
  should be checked rather than assumed.

### What the probe settled, 2026-09-03

**Question.** With the switch known early, does `\glt` still need its
translation as an argument — or can it open a `\vtop` of the remaining
width, closed by the machinery that already closes things at every example
exit?

**Answer: it does not need an argument.** A throwaway document faked the
early switch by hand — the grid boxed at `\gll`, `\glt` opening a second
box, both set down at `\lx@bodyend` — under
`\DocumentMetadata{tagging=on}`, with veraPDF as the oracle rather than the
page. The layout came out right, the reading order came out right
(`Part`(grid) then `Part`(translation), matching what the page shows), and
veraPDF passed all three profiles with nothing logged.

So **item 1 needs no new user syntax**: `\glt` keeps its signature, the
declaration carries the decision, and `\gltrans{...}` is not wanted after
all. That is the whole of what the probe was for.

Three things it turned up on the way, all of which an implementation has to
know.

**The box placement must suspend the ambient marked content.** Setting the
two boxes down inside the paragraph that places them nests their marked
content inside its own, and the first version of the probe did exactly that.
The numbers are the point:

| | veraPDF verdicts | records logged while parsing |
|---|---|---|
| baseline, ordinary gloss | 3/3 pass | 0 |
| boxes placed naively | **3/3 pass** | **17** (`Nested MCID`) |
| placed inside `\tag_mc_end_push:` … `\tag_mc_begin_pop:n {}` | 3/3 pass | 0 |

Every profile calls the naive version compliant. Only the second read of
veraPDF's output tells the two apart — which `a_ua` does, and which exists
because "some malformed nesting is only logged, and a run that logs it still
reports compliant". The remedy is this package's own idiom, the same
suspend-and-resume that `\lx@tag@span@open:n` performs everywhere else, and
it costs two lines.

**Reading order follows PLACEMENT, not typesetting.** The BDC/EMC operators
travel inside the box and reach the page's content stream when the box is
shipped, not when its contents were set. The probe's own comment claimed the
opposite and was wrong. It happens not to matter here, because both boxes
are placed in the order they were built — but anything that ever placed them
in the other order would reverse the reading order while leaving the page
identical, which is worth knowing before somebody reorders the placement for
a good typographic reason.

**The exit order is enforced by TeX, not by veraPDF.** `\lx@glt@langend` has
to run *inside* the box, before the `\egroup` that closes it, because the
language Span is opened from `\everypar` in there. Getting it backwards was
tried: it is a hard TeX error at compile time ("Missing number, treated as
zero"), not a silent tagging defect. One less thing to guard, and the only
one of these three that announces itself.

**What the probe did not answer**, and was not asked to: page-breaking a
boxed pair, the no-room fallback, `\altg`, and the two cases that are
refused by decision anyway (sub-examples, `\exannot`).

### What implementing it added, v1.4

Shipped as `\GlossTransSide` / `\GlossTransBelow` exactly as designed above:
a declaration before the example, boxed layout, `\glt` unchanged, top level
only, no `\exannot`, fallback with a warning below `\GlossTransMinWidth`.
Four bugs on the way, and the reason to write them down is that all four are
the same *kind* — a box's reference point, or what mode TeX was in — and none
of them was an error:

1. **The grid wrapped after its first column, at any width.** The grid is a
   *paragraph* of column boxes; opening the side box leaves TeX in internal
   vertical mode, where the first column is contributed as a vertical item of
   its own and only the `\hskip` after it starts a paragraph. Seen first with
   a 60pt gloss in a 222pt column, and a wider column *hid* it — which sent
   the diagnosis off after a width problem that was not there. `\leavevmode`
   inside the box.
2. **The translation hung half a line low.** `\glt` begins `\par\nobreak`,
   and `\nobreak` is a penalty; a `\vtop` whose first item is not a box has
   height zero. Opening the translation box before the penalty put the
   penalty at the top of it. Fixed by opening it after.
3. **A `\vbox` would have been wrong** and looked right in easy cases: its
   reference point is its last baseline, so two columns of unequal length
   line up at the bottom and drift apart at the top. expl3 has no
   `\vbox_set_top:Nw`, so the `\vtop` counterpart is written out.
4. **The placement had to suspend the ambient marked content**, exactly as
   the probe said. 19 records logged with all three verdicts passing.

And one line that was written, could not be killed by any mutation, and was
removed: a `\parskip` reset at the top of the box. A gloss is always inside
an example list, LaTeX's `\list` sets `\parskip` from `\parsep`, and the
example lists zero it — measured at 0.0pt inside the box with
`\parskip=2\baselineskip` outside. `tests/glt-side.tex` keeps that document
as a guard on the list's `\parsep` instead.

### Sub-examples, and short ones: why the restriction

Decided 2026-09-03, against `expex`, which allows it anywhere. `expex`'s own
demo puts the side position on a *long* top-level example, which is where it
obviously pays; one or two indents down it is doubtful, and the reasons are
mechanical rather than a matter of taste.

What is not a matter of taste is *why* it is doubtful:

- **The saving only exists when the gloss is tall or the translation long.**
  A short sub-example gives a short gloss, a wide gap and a short
  translation: horizontal space spent, no vertical space saved.
- **The measure is already reduced twice.** Split what is left `.6/.4` and
  both halves are narrow, and the gloss may start wrapping between columns —
  the exact failure `\lx@gl@colpenalty` was added to prevent.
- **Siblings would not line up.** If the split is a ratio of the local
  `\linewidth`, then (a), (b) and (c) each put their translation at a
  different x. This is the `\ExAnnotColumn` lesson word for word: a column
  measured from `\linewidth` drifts one indent step per level and looks
  deliberate. It has to come from `\columnwidth`.

So *if* it is allowed below the top level, three things follow and should be
decided together, not one at a time:

1. the split is measured from `\columnwidth`, so sibling translations align;
2. there is a minimum width below which it falls back to the below-position,
   and the fallback is **announced** rather than silent;
3. it is a **per-gloss** decision, not a document-wide mode — whether it
   pays depends on the shape of the individual example, and a paper full of
   short sub-examples set globally to `glftpos=right` would be worse off
   than without the feature.

**What was decided:** top-level only, a package error below that. Not
because a sub-example side translation is wrong, but because nobody yet
knows what it should look like, and the three points above are what a design
would have to answer. Lifting the restriction later is free; guessing now
costs whatever the guess turns out to be wrong about. If a document does
turn up wanting one, those three points are the agenda and
`doc/DEFERRED-DECISIONS.md` is where the question should move.

**How it would be tested.** Geometry: the translation's `x0` is right of the
grid's rightmost ink and shares its vertical band; the split honours the
ratio; two sibling sub-examples put their translations at one x (the check
that would have caught the `\linewidth` mistake). Tagging: reading order in
`pdfinfo -struct-text`, plus veraPDF on a UA build. Mutation that must kill
it: swap the two widths — if no assertion notices, the case is only checking
that two boxes exist.

**Cost.** Medium, down from medium–high: the syntax, the sub-example
question and the tagging risk are all settled above, and the probe showed
the tagging works with two lines of the package's own suspend-and-resume.
What remains is the width arithmetic, the declaration and its reset
question, the no-room fallback, and the test case — which has to assert on
veraPDF's *log* and not only its verdict, since that is the only thing that
told the working version from the broken one.

---

## 2. Key-value façade and named styles

**What `expex` does.** One name per parameter, one setter (`\lingset`), and
`\definelingstyle{name}{...}` + `lingstyle=name` to bundle and invoke a set.
Options can also ride on a single example or gloss.

**What `linguexx` already has, and this is the important part.** Per-example
override is *not* missing. TeX grouping gives it today:

```latex
{\setlength{\Exlabelsep}{1.2em}\ex. one example set differently.}
```

and the mode registry (`\lx_mode_new:nn`, `\lx@mode@defaults@<name>`,
`\resetExdefaults`) already is a named-bundle mechanism — `[legacy]` is
exactly a bundle of parameter values with a name. So the gap is narrower
than the `expex` surface suggests. What is genuinely missing is:

- **one vocabulary.** Parameters are a mix of lengths (`\Exlabelsep`,
  `\JdgSep`, `\ExAnnotColumn`), macros (`\GlossSep`, `\firstrefdash`,
  `\SubExLBr`), and switches (`\ExAnnotFit`, `\GlossPhantomAlign`). A reader
  cannot tell which is which without the manual.
- **a light bundle.** A mode is a heavy thing — it carries geometry hooks
  and a defaults table. There is nothing between "set six lengths by hand"
  and "define a mode".

**The design that follows.** A façade, not a replacement:
`\ExSet{key=value,...}` mapping onto the existing parameters, and
`\ExDefineStyle{name}{...}` + `\ExSet{style=name}`. Additive: every existing
`\setlength` and `\renewcommand` keeps working and stays documented, because
they are in the wild. `\resetExdefaults` continues to win, and must be
asserted to.

**The seam here.** The defaults blocks `\lx@defaults@lazy` and
`\lx@defaults@legacy` are the authoritative list of what a parameter *is* —
if a thing is set there, it is a parameter; if it is not, it is either
derived (`\Extopsep`, `\Exredux`, `\ExAnnotColumn` via `\lx@setannotcol`) or
not configuration at all. The key table should be generated by reading that
list rather than written beside it, or the two will drift exactly as
`REQUIRED_TOOLS` and the CI workflow did.

**What it does to the structure tree.** Nothing. This is the only one of the
four that cannot affect tagging, which is most of why it is cheap.

**What must be decided first.**

- **The key names.** They become API on the day they ship and cannot be
  renamed afterwards. Worth writing the whole table out and living with it
  for a week before committing.
- Whether `\ExSet` may set things the lengths cannot — a `style` key, a
  `mode` key — or is strictly a synonym layer. Strictly-synonym is easier to
  promise and easier to test.
- Whether the derived lengths are settable through it. `\ExAnnotColumn` has
  a re-derivation guard (`\lx@auto@annotcol`) that a key-value setter must
  not silently defeat.

**How it would be tested.** Table-driven: for every key, set it through
`\ExSet` and assert the underlying parameter took the value; then
`\resetExdefaults` and assert it went back. Mutation that must kill it: a
key that expands to nothing — it must fail loudly, not silently leave the
default in place, which is the failure mode a façade is prone to.

**Cost.** Medium, and almost all of it is the key table and its
documentation rather than code.

---

## 3. Reference checking

**What `expex` does.** `\refproofing` sets a flag; every reference it prints
is then decorated — `\mathhigh@lightref` wraps it as
`$\overline{\underline{\hbox{#1}}}$` — so that on a proofreading pass every
cross-reference is visible as a cross-reference rather than as a number that
happens to be in parentheses.

**Why that is not the feature.** It answers "is this a reference?" and never
"is it the right one". An earlier draft of this section credited it with
catching references that point at the wrong example; it cannot, and nothing
printed on a static page can. The objection is worth recording because it is
the obvious one and it is fatal to the feature as `expex` has it.

**What the highlight does buy, which is the inverse.** The value is in what
is *not* highlighted. A hand-typed `(4)` in prose is pixel-identical to
`\ref{ex:x}`, and with proofing on it is the only unhighlighted number on
the page. A hand-typed number is a real failure — it does not renumber — and
this is the only way to see one. That is narrow, and it is all of it.

**The failure that matters here, and why the highlight is blind to it.** In
this package a wrong reference is usually not a mistyped key. `\Next` and
`\Last` mean *the example after/before this point in the text*. Insert an
example between the prose and its target and they retarget silently: there
is no wrong key to find, because the key is positional and the position
moved. The number is correct for where the reference now sits and wrong for
what was meant, and a decoration around it says nothing either way.

One neighbouring failure is already guarded: `\lx_relref_if_unseen_here:`
refuses to link to an anchor the previous run did not record, so a relative
reference cannot point at *nothing*. Pointing at the wrong thing is the
uncovered half.

**The proposal: a report, not a decoration.** Show what each reference
*resolved to*. The package already has the shape for this — `\lpzgcheck`
reports at the end of any document every Leipzig key with no known
expansion, and with `unused=true` every `\SetLeipzig` that was never used.
A reference report in the same idiom would list, per reference: the key (or
the relative command), the number it resolved to, the page, and **the first
few words of the target example**. Then

```
\Next  ->  (12) p.7  "que Pierre est fatigue depuis mardi"
```

is wrong at a glance, in a list read in half a minute, rather than by
cross-checking numbers over forty pages. It is checkable output rather than
decorated output, which is the same preference the test suite already makes
about geometry.

Two checks come free with it and are not available to the eye at all:

- an example `\label` that is never referenced — usually a reference someone
  meant to make and did not;
- a `\Next` whose target is not on the page the prose is on, where that
  prose says "the following example".

**The seam here.** Three sites, all of them already load-bearing for
something else:

- **the relative family** goes through `\lx_relref_emit:nnn` (via
  `\lx@fmtEx` and `\lx@fmtFnEx`), whose third argument is the printed text.
  One hook covers `\Last`, `\Next`, `\NNext`, `\LLast`, `\TextNext` and the
  `\p...` twins; `\refrange`, `\prefrange` and `\Refrange` are a second.
- **the target's opening words** need an `.aux` round trip, which the
  package now has: `\ExAnnotFit` established the pattern, including the
  lesson that the record macros must be `\providecommand`'d into the main
  `.aux` unconditionally or a stale file breaks the next run.
- **turning a collected body into a string** is `\text_purify:n`, already
  used in ten places for `\altn`'s spoken `/Alt`. The dot-syntax body is
  collected token by token (see the note above the collector), so the text
  is there to purify.

**What it does to the structure tree.** Nothing, if the report goes to the
log and the console, which is what `\lpzgcheck` does. If it is ever *typeset*
into the document it becomes a list and has to be tagged as one — the
precedent for that is `\lpzglist`, which is a separate command from
`\lpzgcheck` for exactly this reason. Keep the two apart.

**What must be decided first.**

- **Whether `\ref` itself is in scope.** The relative half needs nothing
  new. The unreferenced-label half needs to see `\ref` calls, and
  `doc/DEFERRED-DECISIONS.md` ("A sub-example part on `\ref`") argues
  against putting this package inside `\ref` — the immunity to the order
  hyperref, cleveref, varioref and nameref load in is worth more than a
  convenience. Two honest ways out: confine the wrapping to an explicitly
  invoked proofing pass (much easier to defend than a package option), or
  drop the unreferenced-label check and report only what the package prints.
  Note that the report can identify example labels *without* wrapping
  anything, by reading them back from the `.aux`: an example label's
  `\newlabel` value contains `\theExLBr`, which nothing else writes. It
  comes in two shapes and an implementer will meet both —
  `{\theExLBr 10\theExRBr }` for a whole example, and
  `{\hbox {\theExLBr 30a\theExRBr }` for a `\sublabel` — so match on the
  delimiter, not on the shape. What that does not give is who referenced
  them.
- **How much of the target to quote.** A word count is arbitrary; a width is
  meaningless in a log. Probably a fixed number of words with an ellipsis,
  and it should be settable.
- **Whether the highlight survives at all.** It is one hook at the same site
  and it does buy the hand-typed-number check. If it is kept it must be an
  Artifact under tagging (`\tag_mc_begin:n {artifact}`), or a proofing build
  stops being conformant and the tagging tests report a defect that is not
  one.

**How it would be tested.** A case with a `\Next` whose target is *not* the
intended example, asserting that the report names the target's actual
opening words — the assertion is on the quoted text, not on the number,
because the number is right in both the good and the bad case. Mutation that
must kill it: report the number and the page but not the target text, which
is exactly the shape the useless version of this feature takes, and which
every other assertion would accept.

**Cost.** Medium, and higher than the highlight it replaces: a record per
example in the `.aux`, a purify pass over collected bodies, an
end-of-document listing, and a decision about `\ref`. Call it a few days.
The highlight alone remains an afternoon, and is worth having only if the
hand-typed-number check is wanted for its own sake.

---

## 4. Named label types

**What `expex` does.** `\definelabeltype` bundles the whole identity of a
label under one name. Its own `alpha` type is

```
\definelabeltype{alpha}{labelgen=char,pexcnt=`a,labelformat=A.,
   fullrefformat=XA,labelalign=left,labelwidth=.72em}
```

— counter representation, printed format, **reference** format, alignment
and box width, switched together by `labeltype=alpha`.

**Why want it.** `linguexx` has every one of those pieces, and they are five
separate settings a document has to keep consistent by hand: `\Exarabic` /
`\Exalph` (the representation), `\theExLBr`/`\theExRBr` and
`\SubExLBr`/`\SubExRBr` (the delimiters), `\firstrefdash`/`\secondrefdash`
(the reference format), and `\Exlabelwidth` with `\lx@calc@Exlabelwidth`
(the geometry). Getting four of the five right produces a document that
looks correct and references wrongly.

**The seam here.** `[legacy]` already switches exactly this set —
`\lx@defaults@legacy` sets the delimiters and both dashes, and
`\lx@geom@main@legacy` the geometry. **A label type is a narrower mode**, so
the design should reuse the mode registry (`\lx_mode_new:nn`) rather than
grow a parallel one beside it. That also means the work is mostly deciding
what a type may contain, not building a mechanism.

**What must be decided first, and this one has teeth.**

- **May a label type change the *reference* format?** `expex`'s does
  (`fullrefformat`). In `linguexx` the `.aux` stores the *formatted* label —
  see any `\newlabel` line in `linguexx-doc.aux`, which holds
  `{\theExLBr 10\theExRBr }` — so switching the format mid-document
  invalidates a stale `.aux` for one run. That is survivable and is exactly
  the cost `doc/DEFERRED-DECISIONS.md` records for the `\ref`-with-a-part
  proposal. It should be an accepted cost, not a discovery.
- **Per level, or one type for the document?** `expex` types are per level
  (`pexcnt` is the sub-example counter's origin). Per level is more useful
  and multiplies the test surface by three.
- **Does a type carry geometry?** `expex`'s does (`labelalign`,
  `labelwidth`). If `linguexx`'s does, a type is a mode; if it does not, a
  type is a formatting bundle and geometry stays where it is. The second is
  a smaller promise and probably the right one to make first.

**What it does to the structure tree.** `/ListNumbering` is chosen per level
by the geometry hooks and must stay consistent with what the label actually
prints — a type that prints letters while the list is declared `Decimal` is
valid PDF and a lie to a screen reader. This is the one place where item 4
can do real accessibility damage, and it is not visible on the page.

**How it would be tested.** The printed labels *and* the `\ref` output for
the same examples, in one case, at two types; plus `/ListNumbering` read
from the tree. Mutation that must kill it: a type that sets the label format
but not the reference format — the page looks perfect and every reference is
wrong, which is precisely the defect the feature exists to prevent.

**Cost.** Medium, dominated by the test matrix rather than the code.

---

## What none of these may do

Constraints that apply to all four, restated so that no note has to argue
them separately:

- **No change to default output.** Every one of these is opt-in. A document
  that does not ask for them must produce a byte-identical PDF.
- **No new `Formula`, and no untagged ink.** The `\altn`/`\altg` invariant
  applies here too: anything drawn must be an Artifact or a real element.
- **veraPDF before belief.** Items 1 and 4 change the structure tree; a
  clean `pdfinfo -struct-text` is not evidence, as
  `doc/TAGGING-NOTES.md` records.
- **Nothing in `doc/DEFERRED-DECISIONS.md` gets settled in passing.**
  Items 3 and 4 both brush against the `\ref` entry, and item 1 against
  nothing but its own new syntax. If implementing one of these would decide
  a deferred question, that is a separate decision with its own evidence,
  not a side effect.
