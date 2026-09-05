#!/usr/bin/env python3
"""Build the sample levels -- and, incidentally, the best worked example of the
library there is.

    python3 samples/generate.py            # rewrite samples/<name>/
    python3 samples/generate.py --check    # regenerate elsewhere and DIFF

Four levels, all built here in Python and all deterministic; nothing in this
directory came out of anyone's game.  Two are showcases:

``corridor``
    every id the ``.gif`` dialect can author, in one walkable level.
``corridor-rwk``
    every id the ``.kitty`` side can author -- most of which the gif dialect
    cannot express, so converting it the other way is the class-(b)/(c)
    emit-with-report demonstration.

and two are small:

``minimal``
    a robot, a floor and a kitty.
``steps``
    jump platforms, a key gate and an enemy.

Each is written in BOTH formats plus the viewer's JSON pair, and each ships an
input tape that walks the robot to the kitty.  ``scripts/local/completability_gate.py``
replays those tapes in the engine and requires the win flag: the samples are
proven completable, not asserted to be.

**No tile id appears in this file.**  Every id is selected from
``id-table.json`` by the table's own ``kind`` vocabulary (see ``build.Vocab``),
so the samples track the table.  What IS written here is level design -- where a
thing goes and why -- which is exactly the part a table cannot know.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import sys
from typing import Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)

from build import Corridor, Sketch, Vocab                      # noqa: E402
from kittygif import gifio, kittyio, viewer                     # noqa: E402
from kittygif.convert import gif_to_kitty, kitty_to_gif         # noqa: E402
from kittygif.level import Level                                # noqa: E402
from kittygif.report import Report                              # noqa: E402
from kittygif.table import GIF, KITTY, IdTable, Palette         # noqa: E402
from kittygif.viewer import ViewerTraits                        # noqa: E402

#: the two packaged dialects, named the way ``--dialect`` names them
RWIA, FLASH = "rwia", "flash"

#: One tape line is ``button,fromTick,toTick`` (inclusive), the format the
#: engine's own oracle driver reads.  A span's FIRST tick is the button's
#: press edge, which is what a jump listens for.
Tape = List[Tuple[str, int, int]]


# ---------------------------------------------------------------- the recipes
def build_minimal(table: IdTable):
    """A robot, a floor and a kitty.  The smallest level that can be won."""
    v = Vocab(table, GIF)
    s = Sketch(6, v.empty)
    solid = v.kind("solid-bulk")[0]

    s.row(4, 0, 11, solid)                       # the floor
    s.row(5, 0, 11, solid)                       # a second course, so nothing falls out
    s.column(0, solid, 0, 3)                     # the two end walls
    s.column(11, solid, 0, 3)
    s.set(2, 3, v.table.position_source_gif_id("robot_xy"))
    s.set(9, 3, v.table.position_source_gif_id("kitty_xy"))

    level = s.to_level(GIF, "MINIMAL")
    return level, [("right", 0, 200)], 250


def build_steps(table: IdTable):
    """Jump platforms, one key gate, one enemy.

    A staircase of one-cell risers: the robot needs the jump powerup (the first
    thing it walks into) but never a double jump, so the intended solution is
    "hold right, tap jump" and nothing else.
    """
    v = Vocab(table, GIF)
    solid = v.kind("solid-bulk")[0]
    s = Sketch(Corridor.HEIGHT, v.empty)
    floor, walk = Corridor.FLOOR, Corridor.WALK

    s.set(2, walk, v.table.position_source_gif_id("robot_xy"))

    gate = v.kind("door")[0]
    key = _key_for(v)[gate]
    s.set(4, walk, v.kind("pickup")[0])          # the jump powerup, first thing out

    # the enemy, sealed in a loft box: seen from the run-up, never met
    s.rect(5, Corridor.CAP, 9, Corridor.CAP, solid)
    s.rect(5, Corridor.CEILING, 9, Corridor.CEILING, solid)
    s.column(5, solid, Corridor.CAP, Corridor.CEILING)
    s.column(9, solid, Corridor.CAP, Corridor.CEILING)
    s.set(7, Corridor.LOFT[1], v.kind("spawn")[0])

    # three risers, each a cell taller than the last and flush against it, so a
    # missed jump never drops the robot into a hole it cannot climb out of
    base = 12
    for step in range(1, 4):
        s.rect(base + 2 * (step - 1), floor - step, base + 2 * step - 1, floor - 1, solid)
    top = floor - 3

    # The landing carries the key, the gate and the kitty -- spread out, because
    # the tape stops jumping once the climb is done and the robot needs a stretch
    # of ground to come down on.  A robot that is still mid-jump sails OVER the
    # kitty: the win test is a 35 px radius, and a jump clears the level's ceiling.
    landing0, landing1 = base + 6, base + 32
    s.rect(landing0, top, landing1, floor - 1, solid)
    s.set(landing0 + 6, top - 1, key)
    gate_x = landing0 + 12
    s.set(gate_x, top - 1, gate)
    s.set(gate_x, top - 2, gate)
    s.set(landing0 + 22, top - 1, v.table.position_source_gif_id("kitty_xy"))

    width = landing1 + 3
    s.row(floor, 0, width - 1, solid)
    s.rect(0, floor + 1, width - 1, Corridor.HEIGHT - 1, solid)
    s.column(0, solid)
    s.column(width - 1, solid)

    level = s.to_level(GIF, "STEPS")
    tape = [("right", 0, 500)] + _tap_tape("jump", first=30, every=25, hold=6, until=200)
    return level, tape, 600


def build_corridor(table: IdTable, name: str = "corridor", ticks: int = 1500):
    """Every authorable id of THIS dialect's gif id space, in one walkable level.

    One recipe, both dialects.  The layout is level DESIGN -- where a thing goes
    and why -- and that reasoning does not change between two games that share
    an id space: powerups in a row you walk down, hazards sealed in the cellar,
    enemies in loft pockets behind the gates their keycards open.  What changes
    is the VOCABULARY, and the vocabulary comes from the table.

    So the kinds a dialect may not have are asked for with ``Vocab.maybe`` (the
    Flash build has no collectibles, no secret-passage air and no water), and
    the kinds every dialect must have are asked for with ``kind``/``one``, which
    raise.  ``_assert_complete`` then requires the finished level to carry every
    authorable id of whichever table it was handed -- so neither showcase can
    quietly stop showing something, and adding a row to either table makes the
    next run lay it out.
    """
    v = Vocab(table, GIF)
    materials = v.kind("solid-bulk")
    s = Sketch(Corridor.HEIGHT, v.empty)
    c = Corridor(s, materials[0])
    walk = Corridor.WALK

    x = 2
    s.set(x, walk, v.table.position_source_gif_id("robot_xy"))
    x += 2

    # -- every collectable thing the dialect can name, in a row you walk down.
    #    The three keycards are in here, and every gate is further right, so the
    #    "keys before their gates" constraint holds by construction.
    for gid in v.kind("pickup") + v.maybe("collectible"):
        s.set(x, walk, gid)
        x += 2

    # -- the things you walk past or through
    s.set(x, walk, v.one("checkpoint"))
    x += 2
    for gid in v.maybe("secret-air"):         # walkable, never drawn, no respawn
        s.set(x, walk, gid)
        s.set(x + 1, walk, gid)
        x += 3
    for gid in v.kind("decor"):               # non-solid scenery, at head height
        s.set(x, walk - 1, gid)
        x += 2
    for gid in v.maybe("solid-decor") + v.kind("solid-breakable"):
        s.set(x, Corridor.CEILING, gid)       # solid, so it hangs in the ceiling plane
        x += 2

    # -- the cellar: everything that would be lethal or awkward on the path goes
    #    under the floor, walled off, where it is visible but cannot be walked into.
    s.x = x + 1
    x0, x1 = c.pocket(Corridor.CELLAR, 3)
    s.row(Corridor.CELLAR[-1], x0, x1, v.one("hazard-source"))          # an acid pool
    for fluid in v.maybe("fluid"):                                       # a water column
        x0, x1 = c.pocket(Corridor.CELLAR, 3)
        for y in Corridor.CELLAR:
            s.set(x0 + 1, y, fluid)

    # -- the gated pens.  One gate per keycard, each a two-cell couple across the
    #    robot's body; the enemies live in sealed loft pockets inside the pens.
    gates = v.kind("door")
    pens = _deal(v.kind("spawn"), len(gates))
    for gate, pen in zip(gates, pens):
        gx = s.x + 1
        s.set(gx, walk, gate)
        s.set(gx, walk - 1, gate)
        s.x = gx + 2
        for enemy in pen:
            px0, _px1 = c.pocket(Corridor.LOFT, 3)
            s.set(px0 + 1, Corridor.LOFT[0], enemy)   # hung from the cap, like a dripper

    x = s.x + 2
    s.set(x, walk, v.table.position_source_gif_id("kitty_xy"))
    width = x + 3

    # -- the structure, last: the floor in three materials so each bulk id is
    #    used, then the cap/ceiling/base UNDER whatever was already painted.
    span = width // len(materials)
    for i, material in enumerate(materials):
        s.row(Corridor.FLOOR, i * span,
              width - 1 if i == len(materials) - 1 else (i + 1) * span - 1, material)
    for y in (Corridor.CAP, Corridor.CEILING, Corridor.BASE):
        for cx in range(width):
            s.cells.setdefault((cx, y), materials[0])
    s.column(0, materials[0])
    s.column(width - 1, materials[0])

    level = s.to_level(GIF, name.upper())
    _assert_complete(level, v, name)
    # Walk right, all the way.  The budget is per-sample and PINNED rather than
    # derived, because it is a claim the oracle checked against a real engine
    # run -- see samples/oracle-expected.json.  A table edit that lengthens a
    # corridor past its budget must fail the oracle, not quietly grow it.
    return level, [("right", 0, ticks - 100)], ticks


def build_corridor_rwk(table: IdTable):
    """Every authorable layout id of the ``.kitty`` side, in one walkable level.

    Most of this vocabulary has no gif counterpart at all, so converting the
    result the other way is what the class-(b)/(c) report was built for.
    """
    v = Vocab(table, KITTY)
    solid = v.one("solid-bulk")
    s = Sketch(Corridor.HEIGHT, v.empty)
    c = Corridor(s, solid)
    walk = Corridor.WALK

    robot_x = 2
    x = robot_x + 2

    # -- every pickup, in id order.  Four of them are keycards; every door
    #    couple is further right.
    for kid in v.kind("pickup"):
        s.set(x, walk, kid)
        x += 2

    # -- the non-solid furniture you can walk straight through
    for kid in [v.one("checkpoint")] + v.kind("secret-air") + v.kind("trigger"):
        s.set(x, walk, kid)
        x += 2
    for kid in v.kind("decor"):
        s.set(x, walk - 1, kid)
        x += 2
    for kid in v.kind("solid-breakable"):
        s.set(x, Corridor.CEILING, kid)
        x += 2

    # -- the cellar: the hazards
    s.x = x + 1
    for kid in v.kind("hazard"):
        x0, x1 = c.pocket(Corridor.CELLAR, 3)
        s.row(Corridor.CELLAR[-1], x0, x1, kid)

    # -- the cellar again: the mechanisms and the one-way walls.  Conveyors and
    #    one-ways move whatever stands on them, so a showcase puts them where the
    #    walker cannot be standing.
    for kid in v.kind("mechanism") + v.kind("one-way"):
        x0, x1 = c.pocket(Corridor.CELLAR, 2)
        s.set(x0, Corridor.CELLAR[-1], kid)
        s.set(x1, Corridor.CELLAR[-1], kid)

    # -- the gated pens: one per door couple that a keycard opens.  The doors
    #    with no key (a boss block, a virus door, a computer door, a coin door)
    #    are display pieces in sealed loft pockets -- they would be dead ends.
    couples, singles = _door_couples(table, v)
    pens = _deal(v.kind("spawn"), len(couples))
    extras = _deal(singles, len(couples))
    for (top, bottom), pen, extra in zip(couples, pens, extras):
        gx = s.x + 1
        s.set(gx, walk - 1, top)
        s.set(gx, walk, bottom)
        s.x = gx + 2
        for kid in list(pen) + list(extra):
            px0, _px1 = c.pocket(Corridor.LOFT, 3)
            s.set(px0 + 1, Corridor.LOFT[0], kid)

    width = s.x + 3
    s.row(Corridor.FLOOR, 0, width - 1, solid)
    for y in (Corridor.CAP, Corridor.CEILING, Corridor.BASE):
        for cx in range(width):
            s.cells.setdefault((cx, y), solid)
    s.column(0, solid)
    s.column(width - 1, solid)

    # A .kitty carries its spawns as FILE FIELDS, not as cells: there is no
    # robot tile and no kitty tile to place.
    level = s.to_level(KITTY, "CORRIDOR-RWK",
                       robot=(float(robot_x), float(walk)),
                       kitty=(float(width - 3), float(walk)))
    _assert_complete(level, v, "corridor-rwk")
    return level, [("right", 0, 3000)], 3200


# --------------------------------------------------------------- small helpers
def _deal(items: Sequence[int], buckets: int) -> List[List[int]]:
    """Spread ``items`` over ``buckets`` as evenly as the count allows."""
    out: List[List[int]] = [[] for _ in range(buckets)]
    for i, item in enumerate(items):
        out[i % buckets].append(item)
    return out


def _tap_tape(button: str, first: int, every: int, hold: int, until: int) -> Tape:
    """Repeated presses: the engine reads the first tick of a span as the edge."""
    return [(button, t, t + hold - 1) for t in range(first, until, every)]


def _key_for(v: Vocab) -> Dict[int, int]:
    """Pair each gate with the pickup that opens it, using the words the table's
    own measured NAMES do not share with anything else of their kind.

    "RED gate (opened by the red key)" and "powerup: red key (RED ACCESS CARD)"
    both keep exactly one word no other door and no other pickup has.  That is
    the pairing, and it is asserted to be a bijection rather than assumed: a
    table edit that broke it fails here instead of shipping a level whose gate
    cannot be opened.
    """
    def distinctive(ids: Sequence[int]) -> Dict[int, set]:
        words = {i: set(re.findall(r"[a-z]+", v.name(i).lower())) for i in ids}
        return {i: w - set().union(*(words[j] for j in ids if j != i)) for i, w in words.items()}

    doors, pickups = v.kind("door"), v.kind("pickup")
    dd, dp = distinctive(doors), distinctive(pickups)
    out: Dict[int, int] = {}
    for door in doors:
        hits = [p for p in pickups if dd[door] & dp[p]]
        if len(hits) != 1:
            raise AssertionError(
                "%s matches %d pickups by its distinctive words %s -- the gate/key "
                "pairing is not a bijection in this table"
                % (v.name(door), len(hits), sorted(dd[door])))
        out[door] = hits[0]
    return out


def _door_couples(table: IdTable, v: Vocab) -> Tuple[List[Tuple[int, int]], List[int]]:
    """Split the door ids into vertical couples and lone doors, from the table.

    The table states the couples it knows as ``shape: "vpair"`` rows, whose
    target is ``[top, bottom]``.  Every one of them is a CONSECUTIVE pair with
    the top half first -- asserted here, not assumed -- and that regularity is
    what identifies the remaining couples (a gold door has no gif counterpart,
    so no pair row names it).
    """
    doors = set(v.kind("door"))
    couples: List[Tuple[int, int]] = []
    for row in table.raw["pairs"]:
        if row.get("shape") != "vpair":
            continue
        top, bottom = row["kitty"]
        if bottom != top + 1:
            raise AssertionError(
                "pair row %r is a vpair whose halves are not consecutive; the "
                "couple-finding rule below rests on that regularity" % row)
        couples.append((top, bottom))
        doors -= {top, bottom}
    for kid in sorted(doors):
        if kid in doors and kid + 1 in doors:
            couples.append((kid, kid + 1))
            doors -= {kid, kid + 1}
    return sorted(couples), sorted(doors)


def _assert_complete(level: Level, v: Vocab, name: str) -> None:
    """A showcase that quietly stopped showing an id is the failure to catch."""
    # On the .kitty side the two spawns are FILE FIELDS rather than cells, and
    # ``Vocab`` already knows that: the table keeps them out of ``kitty.ids``'
    # integer keys, so the authorable set is the set a GRID can show either way.
    used = set(level.tiles)
    want = set(v.authorable)
    missing = sorted(want - used)
    extra = sorted(used - want)
    if missing or extra:
        raise AssertionError(
            "%s does not show every authorable %s id: missing %s (%s), unexpected %s"
            % (name, v.space, missing, ", ".join(v.name(i) for i in missing), extra))


# -------------------------------------------------------------------- writing
#: name -> (builder, blurb, DIALECT).  The dialect is the third column because
#: a sample is authored in one game's id space and cannot be read in another's:
#: `corridor` and `flash-corridor` run the SAME recipe over two tables and come
#: out as two different levels, which is the clearest statement of what a
#: dialect is that this repository can make.
SAMPLES = {
    "minimal": (build_minimal, "a robot, a floor and a kitty", RWIA),
    "steps": (build_steps, "jump platforms, one key gate, one enemy", RWIA),
    "corridor": (build_corridor, "every authorable id of the RWIA gif dialect", RWIA),
    "corridor-rwk": (build_corridor_rwk,
                     "every authorable layout id of the .kitty side", RWIA),
    "flash-corridor": (lambda table: build_corridor(table, "flash-corridor", 1200),
                       "every authorable id of the Flash dialect, as raw map bytes",
                       FLASH),
}


def dialect_of(name: str) -> str:
    """Which id space a sample is authored in.  Never guessed from the files."""
    return SAMPLES[name][2]


def table_for(name: str) -> IdTable:
    """The table a sample MUST be built and read with."""
    return IdTable.load(dialect=dialect_of(name))


def containers_of(name: str) -> Tuple[str, ...]:
    """The container suffixes a gif-space sample is written into.

    Both dialects are one pixel/byte per tile, so both can be written as an
    indexed gif -- and the site gallery, the preview and the round-trip tests
    all read that one.  The FLASH dialect gets the raw map bytes as well,
    because that is the container its game actually reads (a DefineBinaryData
    blob, not a file), and a Flash sample that could not be handed to
    ``raw2kitty`` would not be a sample of anything.
    """
    return (".gif", ".bin") if dialect_of(name) == FLASH else (".gif",)


def _relativise(path: str) -> None:
    """Rewrite the emitted config's provenance paths to bare file names.

    ``kittygif emit-json`` records which table, palette and traits file produced
    a config, as the paths it loaded them from.  That is the right answer for a
    one-off emit and the wrong one for a file committed to a repository: an
    absolute path would make these samples unreproducible on any other machine.
    """
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    for key in ("_id_table", "_palette", "_viewer_traits"):
        if payload.get(key):
            payload[key] = os.path.basename(payload[key])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
        fh.write("\n")


#: how many screen pixels one tile becomes in the README previews
PREVIEW_SCALE = 5


def _write_preview(level: Level, config: dict, path: str) -> None:
    """A flat picture of the level, in the colours the viewer config derived.

    Deliberately NOT a screenshot: it is the level's own authoring legend, one
    block per tile, which is what makes a showcase readable at a glance.  The
    colours come from the emitted category config rather than from the palette
    directly, so the one rule that would silently ruin the picture is already
    applied -- a layout id whose only gif target is a SAFETY substitute does not
    borrow that substitute's colour and does not disappear into the background.
    """
    from PIL import Image

    by_id = {}
    for raw_id, category in config["tile_ids"].items():
        if raw_id.startswith("_"):
            continue
        colour = config["categories"].get(category, {}).get("color")
        by_id[int(raw_id)] = _rgb(colour)
    ground = by_id.get(level.tiles[0], (0, 0, 0))

    image = Image.new("RGB", (level.width, level.height))
    image.putdata([by_id.get(t, ground) for t in level.tiles])
    image = image.resize((level.width * PREVIEW_SCALE, level.height * PREVIEW_SCALE),
                         Image.NEAREST)
    image.save(path, format="PNG", optimize=False)


def _rgb(colour) -> Tuple[int, int, int]:
    if isinstance(colour, str) and colour.startswith("#") and len(colour) == 7:
        return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
    if isinstance(colour, (list, tuple)) and len(colour) == 3:
        return tuple(int(c) for c in colour)
    return (0, 0, 0)


def _write_report(report: Report, path: str) -> None:
    payload = report.to_json()
    payload["id_table"] = os.path.basename(payload.get("id_table", "") or "")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
        fh.write("\n")


def write_sample(name: str, out_dir: str, table: Optional[IdTable] = None,
                 palette: Optional[Palette] = None,
                 traits: Optional[ViewerTraits] = None) -> dict:
    builder, blurb, dialect = SAMPLES[name]
    table = table if table is not None else table_for(name)
    if table.dialect != dialect:
        # A sample built through the wrong table is the quiet failure here: the
        # ids all exist in both spaces, so it would produce a plausible level
        # that means something else.  Refuse instead.
        raise SystemExit(
            "%s is a %r sample but was handed the %r table (%s)"
            % (name, dialect, table.dialect, table.path))
    palette = palette if palette is not None else Palette.load()
    traits = traits if traits is not None else ViewerTraits.load()

    level, tape, ticks = builder(table)
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, name)

    if level.space == GIF:
        converted, report = gif_to_kitty(level, table, name=level.name)
        gifio.write(level, base + ".gif", palette)
        if ".bin" in containers_of(name):
            # One byte per cell, row-major -- exactly what rawio.read expects,
            # and exactly what the Flash loader reads (FLASH_PS:170-176).
            # Written HERE and not by the package: kittygif deliberately ships
            # no raw WRITER (see src/kittygif/rawio.py), and a sample that
            # synthesised its own level is the one caller that already has the
            # cells in hand.
            with open(base + ".bin", "wb") as fh:
                fh.write(bytes(level.tiles))
        kittyio.write(converted, base + ".kitty", table)
        direction = "gif2kitty"
    else:
        converted, report = kitty_to_gif(level, table)
        kittyio.write(level, base + ".kitty", table)
        gifio.write(converted, base + ".gif", palette)
        direction = "kitty2gif"

    _write_report(report, base + ".report.json")
    viewer.emit(level, table, base + "_tilemap.json", base + "_tiles.json",
                palette=palette, traits=traits, source=name + ".authored")
    _relativise(base + "_tiles.json")
    with open(base + "_tiles.json", encoding="utf-8") as fh:
        _write_preview(level, json.load(fh), base + ".preview.png")

    with open(base + ".tape.csv", "w", encoding="utf-8") as fh:
        fh.write("# %s: the intended solution, as the engine's oracle tape\n" % name)
        fh.write("# button,fromTick,toTick  (inclusive); replayed by "
                 "scripts/local/completability_gate.py\n")
        for button, lo, hi in tape:
            fh.write("%s,%d,%d\n" % (button, lo, hi))

    return {
        "name": name,
        "blurb": blurb,
        "dialect": dialect,
        "authored_in": level.space,
        "converted_by": direction,
        "grid": [level.width, level.height],
        "distinct_ids": len(set(level.tiles)),
        "ticks": ticks,
        "solvability_at_risk": report.solvability_at_risk,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=HERE, help="where the <name>/ directories go")
    ap.add_argument("--check", metavar="DIR", nargs="?", const="",
                    help="regenerate into a scratch directory and diff against --out")
    ap.add_argument("--only", action="append", choices=sorted(SAMPLES))
    args = ap.parse_args()

    palette, traits = Palette.load(), ViewerTraits.load()
    tables = {}
    for dialect in sorted({d for _b, _t, d in SAMPLES.values()}):
        loaded = IdTable.load(dialect=dialect)
        problems = loaded.check()
        if problems:
            raise SystemExit("%s is inconsistent:\n  %s"
                             % (loaded.path, "\n  ".join(problems)))
        tables[dialect] = loaded
        for space in (GIF, KITTY):
            print("%-6s %s" % (dialect, Vocab(loaded, space).check_against_census()))

    names = args.only or sorted(SAMPLES)
    manifest = []
    target = args.out
    if args.check is not None:
        import tempfile
        target = args.check or tempfile.mkdtemp(prefix="kittygif-samples-")

    for name in names:
        summary = write_sample(name, os.path.join(target, name),
                               tables[dialect_of(name)], palette, traits)
        manifest.append(summary)
        print("%-15s %-6s %-8s %3dx%-3d %2d ids  -> %s/"
              % (name, summary["dialect"], summary["authored_in"],
                 summary["grid"][0], summary["grid"][1],
                 summary["distinct_ids"], os.path.join(target, name)))

    manifest_path = os.path.join(target, "samples.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"_doc": "written by samples/generate.py", "samples": manifest},
                  fh, indent=1)
        fh.write("\n")

    if args.check is not None:
        return _diff(args.out, target, names)
    return 0


def _diff(want_dir: str, got_dir: str, names: List[str]) -> int:
    bad = []
    for name in names + ["."]:
        a, b = os.path.join(want_dir, name), os.path.join(got_dir, name)
        if not os.path.isdir(a):
            bad.append("%s is missing from %s" % (name, want_dir))
            continue
        files = sorted(f for f in os.listdir(b) if os.path.isfile(os.path.join(b, f)))
        match, mismatch, errors = filecmp.cmpfiles(a, b, files, shallow=False)
        bad += ["%s/%s DIFFERS" % (name, f) for f in mismatch]
        bad += ["%s/%s is missing" % (name, f) for f in errors]
    if bad:
        print("\nsamples differ from a fresh generation:")
        for line in bad:
            print("  - " + line)
        return 1
    print("\nsamples are byte-identical to a fresh generation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
