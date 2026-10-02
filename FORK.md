# What this fork changes, and which parts should not stay a fork

`pyterm` carries a fork of prompt-toolkit because `ptterm` and `pymux`
need things the library does not do. Every commit here is written to be
upstreamable: minimal, in upstream's style, about one thing, with a
test. **None of them has been sent.** A patch that could go upstream
costs exactly as much to maintain as one that could not.

This file is the list, so that the sending can start. It is a judgement
about each commit, not an answer from a maintainer.

## How big the fork actually is

**52 commits**, measured against `583b3412`, upstream's Release
3.0.53, which is the last commit here that is not ours:

| | insertions | deletions | files |
| --- | --- | --- | --- |
| `src/` | 1,737 | 596 | 27 |
| `tests/` | 1,603 | 3 | 13 |
| packaging | 422 | 0 | 5 |

**Re-measure this table when the fork moves**, with that base:

    git diff --numstat 583b3412..HEAD -- src/ | awk '{a+=$1;d+=$2} END {print a, d}'

A ledger nobody re-measures is a ledger nobody trusts. This one was
wrong on the day it was written: its first draft took the base from a
commit count rather than from the last upstream commit, which put the
base three commits inside our own history and hid two of the ones that
matter most.

Three of those numbers are smaller than they look.

- **The tests are not a burden.** All 1,603 lines are ours, they are
  additions, and upstream would take them with the change they judge.
- **`vt100_colors.py` is a move, not new weight.** It is +269 lines,
  and `vt100.py` is +176 -235 over the same span: the colour tables
  came out of it into a file of their own.
- **Two commits cancel.** `3c8f5eb2` added DEC line attributes (+282)
  and `97f80a12` took them out again (-243). `line_attributes.py` does
  not exist. They are in the history and not in the tree.

**Six commits, 425 lines of `src/`, are the part that stays forked.**
That is the real answer to "do we maintain this forever".

## 1. Send: performance

Pure speed. No API changes, no behaviour changes, and each one carries
its measurement in the commit message. These are the easiest thing a
maintainer can say yes to, so send them first.

| commit | what |
| --- | --- |
| `cea3c0fb` `e24df8f6` | Build the default key bindings once |
| `2ff3c7c0` | Walk the layout without a generator frame per level |
| `d861f4e6` | Build the control list without a generator |
| `5bc87c51` | Resolve the merged key bindings once per matching step\* |
| `9030dc2b` | Inline `restyled` into the innermost loop of a render |
| `f55f6d5e` | Skip a row of the render diff that did not change |
| `0ac2d5d8` | Name the position a full screen redraw starts from |
| `7803370e` | Write nothing for a frame that changes nothing |
| `3ba06302` | Carry the size handed out, instead of re-adding it |
| `7b6b4fe9` | `take_using_weights`: 2x, and 25x for one item |
| `f1922277` | Remember how a split divided its area (-29% of a render) |
| `852b4afb` | Reuse the last answer while filling an area with a style\* |
| `4aefc515` | Set a region's mouse handler a row at a time |
| `e18d697a` | Record where characters landed as runs, not as cells |
| `32548423` | Erase a window's background a row at a time |
| `e9cc2238` | A window that erases its area styles its cells as it writes them |

**Send `7b6b4fe9` and `f1922277` first.** Both are self-contained, both
have a benchmark a maintainer can run, and together they are worth 29%
of a render. `3ba06302` belongs in the same pull request as `7b6b4fe9`:
they are the same loop.

\* `5bc87c51` adds no public API, but it does add an **internal
contract**: `_CombinedRegistry.clear_step_cache()`, which
`KeyProcessor` has to call before each matching step. A maintainer
will ask about that coupling, so lead with it rather than let them
find it.

\* `852b4afb` is the inner half of `e9cc2238`: a window that erases
its area never calls `fill_area` anymore, so the reuse only serves
windows that erase nothing. Send the two together, with measurements
re-taken on the same tree, or squash them first.

## 2. Send: a fix

Behaviour that looks wrong today, with a test that shows it.

| commit | what |
| --- | --- |
| `1a2a11b5` | Stop taking the blinking of the cursor away |
| `25eabf0e` | Count only the columns of the screen in a row |
| `c1dce84b` | Erase a row that holds nothing from its first column |
| `1e643916` | Judge the 256 colour table, which upstream has since fixed\* |
| `e586ce5e` | Up is "A" and down is "B", whatever is held down with it |
| `0edac8d9` | Repost a postponed callback with `call_soon` |
| `f490ee5f` `c2525a25` | Draw a `ScrollablePane` where it goes, and 344 lines of tests that say what it puts on the screen |

\* `1e643916` is tests only now: upstream's 3.0.53 fixed the table
itself (`f04219e1`), so the `src/` hunk this commit once carried went
away on the rebase. What stays are the table-content tests --
256 colours, the cube ending at 231, the ramp from 232 -- which
upstream's own suite does not assert.

## 3. Send: an application can ask for something it could not

Additive and opt-in. The default does not change, so the risk to
upstream is small -- but each needs a use case in the pull request,
because the answer is "why would anybody want this?"

| commit | what | why we want it |
| --- | --- | --- |
| `3684648a` | Name the key that came back up | a pane needs key release |
| `d652eda0` | Name control and shift on a letter | the kitty keyboard protocol |
| `722494d1` | Make a key name a type | so an application names its own keys |
| `3dd746dd` | Let content say its characters are already decided | a pane draws another program's output, and must not have it rewritten |
| `1f1759f8` | Let an application give the cursor back | content that says nothing about the cursor follows content that did |
| `7ea47367` | Hold a frame back instead of hiding the cursor | showing a cursor restarts its blink |
| `6098e26c` | Let an application say it does not want SIGWINCH | a server holds several applications, and the handler is a stack |
| `f1875801` | Let a display control omit the cursor padding | a full-width read-only line wrapped onto a blank row |

### One of these is a file split, and it needs its own pull request

`2098d922` took the colour arithmetic out of `vt100.py` into
`vt100_colors.py`: three name tables, the nearest-colour search and
two caches, about two thirds of the file, sharing nothing with the
driver beside them.

**It sends alone** -- it came after the palette work and depends on
none of it, and nothing in section 4 touches `vt100_colors.py`. But
the patch a maintainer sees is not this commit: ours moved the file as
this fork had already changed it. Upstream's split is the same idea
over their own lines, so it has to be made again against their tree.

## 4. Fork: prompt-toolkit is not a terminal emulator

**425 lines of `src/`, six commits.** These carry terminal state
through a library that has no reason to want it. Upstream draws
prompts; it does not have a program's screen to be faithful to. Expect
these to stay, and keep them small.

| commit | `src/` | what |
| --- | --- | --- |
| `c2a828aa` | +139 -8 | Carry a colour of the palette as its number |
| `50b490b5` | +68 -8 | Carry the id of a hyperlink |
| `a80dcf69` | +35 -16 | Keep a blank cell that a program wrote |
| `3a393377` | +31 | Raise and lower a glyph with "SGR 73" to "SGR 75" |
| `73b147af` | +94 -1 | Carry the shape and the colour of an underline on a cell |
| `dc1de7fb` | +58 | Carry a hyperlink on a cell |

Each one is the same shape: a cell or a style has to carry one more
thing, because a terminal wrote it and a pane has to write it out
again unchanged.

## 5. Packaging: never upstream, and no burden

`1d625b65` `25f5b7cb` `767939b6` `5d368a4a` `afd58c59` `0a8a546d`
`8e6dfa50` `2284ce7c` `061051af`.

The nix package, the suite that judges this fork, and this ledger.
They touch no library code.

`061051af` is the one that is not only ours: `nix/suite.nix` is the
same file in all seven repositories of the collection, and it changed
in all seven at once. A run that could not run -- a picture suite
whose display server never came up -- now fails its run derivation
instead of pinning a red that only store surgery clears.
Lillecarl/pymux#216.

## The rule from here

A change to this repository says which of the five it is, in the commit
message, before it lands. A change that is none of them does not belong
here: look for the answer in `pymux` or `ptterm` first, and say why
that route was worse.
