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
| 1 | Free translation *beside* the gloss | medium–high | the syntax for the translation body |
| 2 | Key-value façade and named styles | medium | the key names, which become API forever |
| 3 | Reference checking | medium | whether `\ref` itself is in scope |
| 4 | Named label types | medium | whether a type may change the *reference* format |

Suggested order: **2, 1, 3, 4**. Item 2 is the cheapest and the only one
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

**That is the whole difficulty.** By the time `\glt` runs, the grid's
paragraph has been broken and contributed to the enclosing list; there is
nothing left to set beside. `expex` avoids this because *its* free
translation is delimited — `\gl@wrap@right@ft #1//` — so the translation is
an argument and both halves can be boxed. Three ways out:

1. **Delimit the translation**, `expex`-style: `\glt ... //`. Cheapest
   mechanically, and the ugliest — it changes what `\glt` means for every
   existing document, and `\glt` is inherited from `cgloss4e`.
2. **An environment**, e.g. `\begin{glosstrans}...\end{glosstrans}`, or a
   `\gltside{...}` variant used *instead* of `\glt` when the side position
   is wanted. Additive; nothing existing changes; two names for one thing.
3. **Tell `\gll` in advance** — a key or option on the gloss — so that
   `\lx@gloss@multi` sets the grid into a box of reduced width and *defers*
   its `\par`, leaving `\glt` to land in a parallel `\vtop`. This is what
   `expex` does structurally, and it still needs the translation's extent to
   be known, so it collapses into (1) or (2) unless `\glt` is made to
   scan ahead.

**What it does to the structure tree.** Reading order is unchanged: left
then right *is* grid then translation, so `LBody → Part(grid) ,
Part(translation)` still describes it. What must be checked is that the two
`\vtop`s do not become an untagged two-column artifact, and that the
translation's `/Lang` (`\GlossTransLang`) still lands on the right element.
`examples/ua-demo.tex` would need a side-by-side gloss and veraPDF run on
it; `struct_label_depths` would catch a `Part` left open.

**What must be decided first.**

- The syntax (above). This is new user syntax, so CLAUDE.md's rule applies:
  not "by default", and not without prior explicit validation.
- What happens when the translation is *taller* than the gloss. `expex`
  simply lets the `\vtop` grow. Fine, but it should be stated.
- The interaction with `\exannot`, whose column is measured from
  `\columnwidth` (see `\lx@annot@width:`). In a narrowed grid, either the
  annotation column must be measured against the left box instead, or an
  annotation on a side-by-side gloss is refused. Refusing is defensible and
  much cheaper.
- The interaction with `\altg`, whose two-call protocol runs across tiers of
  one grid (`\g__lxp_altg_role_int`). Narrowing the grid does not disturb
  that, but the brace geometry is measured from the stack's extents and
  should be checked rather than assumed.

**How it would be tested.** Geometry: the translation's `x0` is right of the
grid's rightmost ink and shares its vertical band; the split honours
`ssratio`. Tagging: reading order in `pdfinfo -struct-text`, plus veraPDF on
a UA build. Mutation that must kill it: swap `ssleftwd` and `ssrightwd` —
if no assertion notices, the case is only checking that two boxes exist.

**Cost.** Medium–high. The width arithmetic is an afternoon; the syntax
question and the tagging check are the work.

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
