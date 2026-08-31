# kittygif

A level converter between two tile-map formats: an indexed-GIF dialect in which
one pixel is one tile, and the `.kitty` v1 level container (a chunked binary
save-game format with a packed 32-bit cell bitfield).

```
.gif  <->  neutral grid model  <->  .kitty
```

Both directions are **partial**, so the converter never refuses a file: it always
emits, and it always reports what it could not carry across.

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

### `emit-json` — a level as a viewable tile map

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

## Everything id-shaped is DATA

The code knows **packing formats only**: the chunk tree, the cell bitfield, the
palette layout, the blob autotiler's decision tree. Every tile id, class tag,
substitute, palette byte, container fact and default lives in
`src/kittygif/data/id-table.json` and `palette.json`, each entry carrying its own
provenance. Adding a dialect means adding a table, not editing the converter;
correcting a mapping means correcting one JSON row.

That is also what makes the gates testable: `--id-table` points the whole
converter at another copy, so a mutated table can be driven through the real code
path without touching the shipped data file.

## Validation

| layer | what it proves | where |
|---|---|---|
| **L1** | round-trip byte identity over the mappable subset, through real files | `tests/` (CI-able, synthetic only) |
| mutants | each gate actually goes red on a broken table | `tests/test_mutants.py` |
| **L2** | the emitted file loads in the engine, at the right size, with the spawn where the source pixel said, and it steps | `scripts/local/` |
| blob oracle | the autotiler transcription scored against real editor output | `scripts/local/` |
| **L3** | the emitted file RENDERS in the game build — geometry and appearance, never id semantics | manual, real-GPU browser |

```
pytest                                             # L1 + mutants, no game files needed
python3 scripts/local/l2_oracle_gate.py --mutant   # needs a local engine build
python3 scripts/local/acceptance.py                # needs local level files
python3 scripts/local/check_blob_autotiler.py      # needs local level files
```

**L1 is a self-consistency gate, and it has a known blind spot.** A table whose
pairs are consistently relabelled is still a bijection, so `gif -> kitty -> gif`
still closes while the emitted level has had two materials swapped. Only an
external oracle sees that class of defect; `l2_oracle_gate.py --mutant` is the
one that does. Both halves are pinned as tests.

## What is NOT here

No level files, no game assets, no third-party source. The test suite generates
every fixture it needs from the table, so `pytest` runs on a bare checkout. The
scripts under `scripts/local/` are the only ones that touch real data; they take
paths on the command line and write outside this tree.

The id table is our own measured, cited facts about two file formats — not
anyone's code or content.

## Licence

MIT. See `LICENSE`.
