# What this fork changes, and which parts should not stay a fork

`pyterm` carries a fork of prompt-toolkit because `ptterm` and `pymux`
need things the library does not do. Every commit here is written to be
upstreamable: minimal, in upstream's style, about one thing, with a
test. **None of them has been sent.** A patch that could go upstream
costs exactly as much to maintain as one that could not.

This file is the list, so that the sending can start. It is a judgement
about each commit, not an answer from a maintainer.

## How big the fork actually is

Measured against `dffde696`, the first commit of this fork, at
`e85b2ba8`. **Re-measure this table when the fork moves**; a ledger
that is one commit out of date on the day it is written is a ledger
nobody checks against.

| | insertions | deletions | files |
| --- | --- | --- | --- |
| `src/` | 1,315 | 509 | 26 |
| `tests/` | 1,088 | 6 | 10 |
| packaging | 196 | 0 | 4 |

Three of those numbers are smaller than they look.

- **The tests are not a burden.** They are ours, they are additions,
  and upstream would take them with the change they judge.
- **`vt100_colors.py` is a move, not new weight.** It is +269 lines,
  and `vt100.py` is -133 in the same period: the colour tables came
  out of it into a file of their own.
- **Two commits cancel.** `ac374ef9` added DEC line attributes (+282)
  and `15c72333` took them out again (-243). `line_attributes.py` does
  not exist. They are in the history and not in the tree.

**Four commits, 273 lines of `src/`, are the part that stays forked.**
That is the real answer to "do we maintain this forever".

## 1. Send: performance

Pure speed. No API changes, no behaviour changes, and each one carries
its measurement in the commit message. These are the easiest thing a
maintainer can say yes to, so send them first.

| commit | what |
| --- | --- |
| `badffa3c` `03fc5350` | Build the default key bindings once |
| `ad709cef` | Walk the layout without a generator frame per level |
| `26f5677c` | Build the control list without a generator |
| `a5e96381` | Resolve the merged key bindings once per matching step\* |
| `a3beab97` | Inline `restyled` into the innermost loop of a render |
| `40ec9267` | Name the position a full screen redraw starts from |
| `c6036f64` | Write nothing for a frame that changes nothing |
| `92dd52aa` | Carry the size handed out, instead of re-adding it |
| `f8e00986` | `take_using_weights`: 2x, and 25x for one item |
| `e85b2ba8` | Remember how a split divided its area (-29% of a render) |

**Send `f8e00986` and `e85b2ba8` first.** Both are self-contained, both
have a benchmark a maintainer can run, and together they are worth 29%
of a render. `92dd52aa` belongs in the same pull request as `f8e00986`:
they are the same loop.

\* `a5e96381` adds no public API, but it does add an **internal
contract**: `_CombinedRegistry.clear_step_cache()`, which
`KeyProcessor` has to call before each matching step. A maintainer
will ask about that coupling, so lead with it rather than let them
find it.

## 2. Send: a fix

Behaviour that looks wrong today, with a test that shows it.

| commit | what |
| --- | --- |
| `eb17fde2` | Stop taking the blinking of the cursor away |
| `a3546c10` | Count only the columns of the screen in a row |
| `f875779c` | Erase a row that holds nothing from its first column |
| `abecfd83` | Give the 256 colour table all 256 colours |
| `6aa30bff` | Up is "A" and down is "B", whatever is held down with it |
| `69a25452` | Repost a postponed callback with `call_soon` |
| `6f01ab07` `2c402785` | Draw a `ScrollablePane` where it goes, and 344 lines of tests that say what it puts on the screen |

## 3. Send: an application can ask for something it could not

Additive and opt-in. The default does not change, so the risk to
upstream is small -- but each needs a use case in the pull request,
because the answer is "why would anybody want this?"

| commit | what | why we want it |
| --- | --- | --- |
| `64b22b79` | Name the key that came back up | a pane needs key release |
| `35fe4bea` | Name control and shift on a letter | the kitty keyboard protocol |
| `19d4b73d` | Make a key name a type | so an application names its own keys |
| `2e43173d` | Let content say its characters are already decided | a pane draws another program's output, and must not have it rewritten |
| `0959e262` | Let an application give the cursor back | content that says nothing about the cursor follows content that did |
| `b4073f52` | Hold a frame back instead of hiding the cursor | showing a cursor restarts its blink |
| `3c317b87` | Let an application say it does not want SIGWINCH | a server holds several applications, and the handler is a stack |
| `4dca0301` | Let a display control omit the cursor padding | a full-width read-only line wrapped onto a blank row |

### One of these is a file split, and it needs its own pull request

`1f5fa9ef` took the colour arithmetic out of `vt100.py` into
`vt100_colors.py`: three name tables, the nearest-colour search and
two caches, about two thirds of the file, sharing nothing with the
driver beside them.

**It sends alone** -- it came after the palette work and depends on
none of it, and nothing in section 4 touches `vt100_colors.py`. But
the patch a maintainer sees is not this commit: ours moved the file as
this fork had already changed it. Upstream's split is the same idea
over their own lines, so it has to be made again against their tree.

## 4. Fork: prompt-toolkit is not a terminal emulator

**273 lines of `src/`, four commits.** These carry terminal state
through a library that has no reason to want it. Upstream draws
prompts; it does not have a program's screen to be faithful to. Expect
these to stay, and keep them small.

| commit | `src/` | what |
| --- | --- | --- |
| `8c8ec6cd` | +139 -8 | Carry a colour of the palette as its number |
| `b88e1d80` | +68 -8 | Carry the id of a hyperlink |
| `e738b6b5` | +35 -16 | Keep a blank cell that a program wrote |
| `4c5c88a8` | +31 | Raise and lower a glyph with "SGR 73" to "SGR 75" |

Each one is the same shape: a cell or a style has to carry one more
thing, because a terminal wrote it and a pane has to write it out
again unchanged.

## 5. Packaging: never upstream, and no burden

`dffde696` `9cf3245c` `c04710a3` `e583a425` `d4e05b48` `7f6fabaa`.

The nix package and the suite that judges this fork. They touch no
library code.

## The rule from here

A change to this repository says which of the five it is, in the commit
message, before it lands. A change that is none of them does not belong
here: look for the answer in `pymux` or `ptterm` first, and say why
that route was worse.
