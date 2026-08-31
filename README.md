# kittygif

A level converter between two tile-map formats: an indexed-GIF dialect in which
one pixel is one tile, and the `.kitty` v1 level container (a chunked binary
save-game format with a packed 32-bit cell bitfield).

```
.gif  <->  neutral grid model  <->  .kitty
```

Both directions are **partial**, so the converter never refuses a file: it always
emits, and it always reports what it could not carry across.

It is a bridge, not an editor. It exists so a level authored for one of these
engines can be opened, inspected and played in the other.

**▶ Try it in your browser: [peerinfinity.github.io/kittygif](https://peerinfinity.github.io/kittygif/)** — the
demo runs this same package under Pyodide, so nothing is uploaded: drop a level
in, read the report, download the converted file.

> **This project's code was written by AI (Claude), directed and reviewed by
> [PeerInfinity](https://github.com/PeerInfinity).** The file-format facts it
> encodes were measured — from decompiled bytecode, from C++ sources, and from a
> disassembly of the shipping reader — and every one of them carries its citation
> in `src/kittygif/data/id-table.json`. Where a fact could not be measured it is
> marked as a judgement call. Please read it the way you would read anything else
> on the internet: the gates below are what it is trusting, and they are all
> re-runnable.

## Install

```
pip install -e .
```

Python 3.9+, Pillow.

## Use

```
kittygif gif2kitty LEVEL.gif OUT.kitty [--name NAME] [--paint-style panels] [--no-paint]
kittygif kitty2gif LEVEL.kitty OUT.gif
kittygif info FILE...
kittygif emit-json LEVEL.{gif,kitty} OUT_PREFIX [--name NAME]

  --report PATH        write the machine-readable JSON report ('-' for stdout)
  --quiet              suppress the human summary on stderr
  --id-table PATH      convert by another copy of the id table
  --viewer-traits PATH use another copy of the viewer trait table
  --emit-json PREFIX   (on gif2kitty/kitty2gif) also write the viewer pair for
                       the level the conversion PRODUCED
```

As a library:

```python
from kittygif import IdTable, gif_to_kitty, kitty_to_gif
from kittygif import gifio, kittyio

table = IdTable.load()
level = gifio.read("mylevel.gif")
converted, report = gif_to_kitty(level, table, name="MYLEVEL")
kittyio.write(converted, "MYLEVEL.kitty", table)

print(report.to_text())          # human summary
report.to_json()                 # per-kind counts + coordinates
report.solvability_at_risk       # True if something unrepresentable was substituted
```

## The samples

`samples/` holds four levels, in both formats, with the viewer's JSON pair and
an input tape that solves each one. All four are **generated**, by
`samples/generate.py` — which is also the best worked example of the library
there is, and the reason the samples track the id table instead of drifting from
it: not one tile id is written down in that script. Every id is selected from
the table by the table's own `kind` vocabulary.

```
python3 samples/generate.py            # rewrite samples/<name>/
python3 samples/generate.py --check    # regenerate elsewhere and diff
```

| sample | grid | authored in | ids used | has class-(c) content | wins at tick |
|---|---|---|---|---|---|
| `minimal` | 12 x 6 | gif | 4 | no | 78 |
| `steps` | 47 x 12 | gif | 8 | no | 416 |
| `corridor` | 101 x 12 | gif | 39 | yes | 1034 |
| `corridor-rwk` | 231 x 12 | .kitty | 74 | yes | 2422 |

![corridor](samples/corridor/corridor.preview.png)

![corridor-rwk](samples/corridor-rwk/corridor-rwk.preview.png)

Those are the two showcases at five pixels per tile, in the colours the viewer
config derives — a flat map of the level, not a screenshot. The walking lane runs
across the middle: the powerup row on the left, the sealed cellar pockets below
it, the gates (pink) and the enemy pockets in the loft on the right. The second
picture has no player marker because a `.kitty` carries its spawns as *file
fields* rather than cells, which is one of the two formats' honest asymmetries.

The two are showcases, one per side of the table:

* **`corridor`** carries **every id the gif dialect can author** — all ten
  powerups and the six collectibles in a row you walk down, one of each of the
  five enemies in sealed pockets behind the three keycard gates, the checkpoint,
  the secret passage, the breakable brick, the decorations, an acid pool and a
  water column walled off under the floor, and all three bulk materials in the
  floor. Converting it to `.kitty` degrades 77 cells and substitutes 4 — the
  water and the one enemy the other engine never had.
* **`corridor-rwk`** carries **every layout id the `.kitty` side can author**,
  most of which the gif dialect has no way to express: conveyors, one-way walls,
  telematics, velcro, spikes, coins, bosses, hearts, a gold gate. Converting it
  the other way is the emit-with-report demonstration: 65 substituted cells,
  named and located in `corridor-rwk.report.json`.

**Completability is proven, not asserted.** Each sample ships
`<name>.tape.csv`, the button presses that solve it, and
`scripts/local/completability_gate.py` replays that tape in a real build of the
engine and requires the engine's own **win flag** — reached from exactly one
place in the game, when the robot comes within 35 px of the kitty — with no
death on the way. That gate needs the game and cannot run in CI, so its verdict
travels in `samples/oracle-expected.json`, and the test suite checks that every
sample carries one.

The showcases keep the enemies and the machinery in **sealed pockets** beside
the walking lane rather than on it. That is a deliberate design choice, not an
accident of generation: a showcase's job is to display the whole vocabulary, and
its intended solution should still be a walk anyone can follow.

## `emit-json` — a level as a viewable tile map

`emit-json` writes the two files a tile-map viewer wants, in the level's own id
space: `<PREFIX>_tilemap.json` (`{tiles, map_width, map_height}`, one list per
row) and `<PREFIX>_tiles.json` (`{categories, tile_ids, default_category}`).
The shape is [Archipelago-CC](https://github.com/PeerInfinity/Archipelago-CC)'s
`tileMapAnalyzer` contract, and **the two suffixes are part of it**: that project
gitignores its viewer data by exactly those globs, so a prefix keeps a generated
map out of a tracked tree by construction.

Nothing in the category config is written by hand. A category is the id's
measured `kind` (split by `solid` when a kind is not uniform on it, so the floor
derivation cannot lose the flag); a colour is the canonical RGB of the gif id the
table pairs it with — which is what lets a `.gif` grid and a `.kitty` grid be
read side by side in one palette. Only the handful of flags no measurement gives
(`lethal`, `blocks_floor`, `is_region`, `is_location`, `is_player_start`) come
from `data/viewer-traits.json`, keyed on that same `kind` vocabulary: nineteen
rows standing in for a hundred and thirty ids.

⛔ One derivation rule is worth stating because getting it wrong is invisible: a
layout id whose only gif target is a class-(c) **substitute** does NOT borrow
that substitute's colour. The substitute is chosen for SAFETY, and a solid
conveyor painted in air's colour would vanish from the picture the viewer exists
to draw. Those categories take a name-derived colour instead and stay visible.

## The report

Every converted cell falls into one of three classes, taken from the id table's
own tags:

| class | meaning | in the report |
|---|---|---|
| **a** | mappable — a table entry both formats agree on | counted |
| **b** | degraded — cosmetic only (a paint style, a decoration, a bonus pickup); solvability unchanged | listed with counts and coordinates |
| **c** | unrepresentable — a mechanic the other format has no way to express; emitted as the nearest safe tile | listed **prominently**, and `solvability_at_risk` goes true |

Both directions have class-(c) content. Going one way, a handful of mechanics
the other engine never had (water that changes the player's vertical motion, one
enemy type) become air. Going the other way, some forty mechanics — conveyors,
one-way walls, bosses, teleports, HP items — have no target id at all. The
report names each one, how many there were, and exactly where.

## The formats

Everything below is measured, and every claim in it is cited per-id or per-field
in `src/kittygif/data/id-table.json`. Neither format has published
documentation; this is what reading the two engines produced.

### The level gif

**One pixel is one tile, and the tile is the palette INDEX.** A level is a
single-frame indexed (mode `P`) GIF whose width and height are the grid's, and
whose pixel at `(col, row)` is the tile id at that cell. The palette is an
authoring **legend** — arbitrary distinct colours so a human can see what they
are drawing — and not the tile's appearance in game: bulk rock is white and air
is black in the file.

That the reader keys on the index rather than the colour is the evidence's
reading, not an assumption we like: two of the measured level gifs share a
palette in which the water id and the air id have the **same RGB**, yet one of
them places water in deliberate columns. Distinguishing those two cells is only
possible by index. (Our writer emits the canonical measured RGB per id anyway,
which is correct under either reading.)

Two ids are not tiles but **positions**: one pixel marks where the player
starts and one marks the goal. The world coordinate is `cell * 40` with no
half-tile offset — measured in the disassembly of the program that reads these
files, and confirmed end to end by the engine's own load.

Some ids are never authored: the engine generates them at load (decoration
quadrants, parallax backgrounds) or uses them as runtime state (an activated
checkpoint). The table marks them, and a census of real level files agrees
exactly with that marking — two independent derivations of "what a level file
may contain", which is what `samples/generate.py` builds `corridor` from.

Gates are the one shape the flat table cannot express. A gif gate is a vertical
run of one id, **any height**; the other format's door is exactly a top/bottom
couple, and opening one half removes only its own partner. Runs are therefore
tiled into couples from the **bottom up**, and an odd cell at the top becomes a
lone top half — which opens on its own, so no cell is ever left permanently
shut. A run that was not two tall is named in the report.

### The `.kitty` container (v1 and v16)

```
int32 fileVersion                       # 1 or 16; anything else is refused, not mis-parsed
chunk                                   # the level
int32 nestedSaveGameCount               # 0 in a level file

chunk := int32 payloadLen, payload[payloadLen], int32 childCount, child*
```

Two versions are readable. **v1** is the campaign container and the one this
converter writes. **v16** (`SAVEGAME_VERSION 0x0010`) is what the Maker Mall
editor at [robotwantskitty.com/web](https://www.robotwantskitty.com/web/) saves —
so a level authored in the official web editor converts here directly.

The body — grid, robot, kitty, extra game data — is written by one
version-independent routine, so the two versions differ only in the metadata
chunk in front of it and in whether an editor-tool chunk follows.

At **v1** the level chunk carries no payload and six children, in order:

| # | child | payload |
|---|---|---|
| 0 | name | `String` |
| 1 | grid | `int32 w, int32 h, uint32 cells[w*h]`, **optionally** `byte levelMap[w*h]` |
| 2 | robot | `float x, float y` |
| 3 | kitty | `float x, float y` |
| 4 | extra game data | 71 bytes of typed fields (or 72 with a trailing bool) |
| 5 | editor tool chunk | `int32 nextPaintRegionId`, optionally more |

At **v16** there are five children: child 0 is a wider metadata chunk —
`int32 uploadId, String name, int64 tags, uint32 paintId, bool testedOk, bool
testedNoDying, char flagBits` — then the same children 1–4, and no editor chunk.
Its grid chunk always carries the `levelMap` array *and* one sub-chunk (the
radio-text list: `int32 count`, then that many `Point, String` pairs), neither of
which a v1 file ever has. Its extra-game-data chunk is a longer field list than
v1's, so it is not carried into a v1 file — a v16 level written back out as v1
gets the pinned donor block.

Which child is which, per version, is a row in the id table
(`kitty_file.read_layouts`), not a branch in the reader: teaching this tool a
third container version is a data edit.

Primitives are little-endian; a `String` is an `int32` length **including its
NUL** followed by the bytes.

A cell is a little-endian `uint32` bitfield:

```
layout:7 | paint:9 | customDraw:1 | extraData:6 | paintID:9
```

`layout` is the tile id. `paint` is a cosmetic surface: `style = paint // 47`
over ten named styles, `blob = paint % 47` over the standard 47-tile blob
autotiler. `paintID` groups painted cells into regions and is the flag that says
a cell is painted at all. `customDraw` and `extraData` are computed at load, so
a writer emits zero.

⚠ **The v1 grid chunk has two shapes.** Six of the eleven measured levels are
`8 + w*h*4` bytes; the other five append a `w*h` byte array (the revealed-map
state left over from editing). Both are file version 1 and both load. The split
lines up exactly with the extra chunk's 71/72-byte split, which is what makes it
the shape of the format rather than a coincidence — a second variable
partitioning the corpus the same way. The reader takes either and preserves what
it found, so a `.kitty` round-trips byte-exact; the writer emits the shorter of
each.

### The id table

`src/kittygif/data/id-table.json` is the whole translation: 55 gif ids, 74
layout ids, 99 pair rows, the paint model, the container facts and a donor
settings block, each entry carrying its own provenance — a Flash source line, a
C++ source line, a disassembly address, an observed count in a real file, or a
note saying which of those it lacks. It is **our derived facts with citations**,
not anyone's code or content, which is why it can be published.

## Everything id-shaped is DATA

The code knows **packing formats only**: the chunk tree, the cell bitfield, the
palette layout, the blob autotiler's decision tree, and three structural rules
(a `vpair` target is a vertical door couple; a position row moves a spawn field;
class tags order `a < b < c`). Every tile id, class tag, substitute, palette
byte, container fact and default lives in `id-table.json` and `palette.json`.
Adding a dialect means adding a table, not editing the converter; correcting a
mapping means correcting one JSON row.

That is also what makes the gates testable: `--id-table` points the whole
converter at another copy, so a mutated table can be driven through the real code
path without touching the shipped data file.

## Validation

| layer | what it proves | where |
|---|---|---|
| **L1** | round-trip byte identity over the mappable subset, through real files | `tests/` (CI-able, synthetic + the samples) |
| mutants | each gate actually goes red on a broken table | `tests/test_mutants.py` |
| samples | the committed samples still regenerate, and each carries a completability verdict | `tests/test_samples.py` |
| guard | no original level file is in this repository | `tests/test_no_originals.py` |
| **L2** | the emitted file loads in the engine, at the right size, with the spawn where the source pixel said, and it steps | `scripts/local/` |
| **completability** | each sample's tape reaches the goal — the engine's own win flag, no death | `scripts/local/` |
| blob oracle | the autotiler transcription scored against real editor output | `scripts/local/` |
| **L3** | the emitted file RENDERS in the game build — geometry and appearance, never id semantics | manual, real-GPU browser |
| **L4** | the emitted `.gif` loaded **in the original game**, and played correctly | manual, done once |

```
pytest                                                # everything CI-able, no game files needed
python3 tests/test_no_originals.py [DIR]              # the guard, standalone, on any tree
python3 scripts/local/l2_oracle_gate.py --mutant      # needs a local engine build
python3 scripts/local/completability_gate.py          # needs a local engine build
python3 scripts/local/acceptance.py                   # needs local level files
python3 scripts/local/check_blob_autotiler.py         # needs local level files
```

**L1 is a self-consistency gate, and it has a known blind spot.** A table whose
pairs are consistently relabelled is still a bijection, so `gif -> kitty -> gif`
still closes while the emitted level has had two materials swapped. Only an
external oracle sees that class of defect; `l2_oracle_gate.py --mutant` is the
one that does. Both halves are pinned as tests. The same limit applies to L3: a
render eyeball proves geometry and appearance, never id semantics.

Each gate here was made to go red before it was believed. The no-originals guard
was run against a tree with a real level file dropped into it; the completability
gate was run against a sample with its keycards removed (the robot stops at the
first gate) and against a tape with its jumps removed (the robot stops at the
first step).

## What is NOT here

No level files, no game assets, no third-party source. The test suite generates
every fixture it needs from the table, so `pytest` runs on a bare checkout, and
`tests/test_no_originals.py` walks the tree on every CI run and fails if a file
ever matches one of the 35 originals this work was measured against (stored as
hashes only — a hash identifies a file without carrying any of it).

Converted originals are not here either, and that is a stricter promise than the
hash guard can enforce: a converted level is a *new* file with a *new* hash, so
what keeps it out is the rule, `.gitignore`, and working outside the tree. If you
convert someone's level, the result is still their level.

The scripts under `scripts/local/` are the only ones that touch real data; they
take paths on the command line and write outside this tree.

## Licence and scope

MIT — see `LICENSE`. The tool is ours and ships no one else's bytes.

This project is **compatible with the `.kitty` level format** and with the
indexed-gif level dialect. It is not affiliated with, endorsed by, or a product
of the authors of either game, it is not named after either of them, and it
redistributes nothing of theirs — no art, no audio, no level data, no source
text beyond quoted identifiers and line references in the citations.

### Credits and links

- **Robot Wants Kitty** and its web level editor — the source of the `.kitty`
  container — are by **Raptisoft**: <https://www.robotwantskitty.com/>
- **Robot Wants It All**, the compilation whose level files use the gif dialect,
  is by **Hamumu Software**:
  <https://store.steampowered.com/app/834760/Robot_Wants_It_All/>

Those names appear here to say which formats this tool reads and writes, and to
point at the games themselves. Nothing of theirs is redistributed.

### The demo

<https://peerinfinity.github.io/kittygif/> — built and published by `.github/workflows/pages.yml`. Build it locally
with:

```
python scripts/build_site.py -o _site && python -m http.server -d _site
```

The page loads a wheel built from the same commit, so the demo cannot drift
behind the code beside it. The no-originals guard runs a second time over the
assembled site, because a site directory is another way a level file could
reach the public.
