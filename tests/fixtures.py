"""Synthetic fixtures.

This repository ships **no real level files** -- not one byte of anyone's game.
Every fixture below is generated here, from the table, so the suite is runnable
by anyone who checks the repo out.  Real-data runs live in ``scripts/local/``.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Set, Tuple

from kittygif.level import Level
from kittygif.table import GIF, KITTY, IdTable


def mappable_gif_ids(table: IdTable) -> Set[int]:
    """gif ids that survive ``gif -> kitty -> gif`` unchanged.

    Derived from the table, never listed by hand: a gif id is mappable iff its
    forward rule's target maps back to it.  A ``vpair`` target counts when EVERY
    half maps back (both door halves must return the same gate id).
    """
    out = set()
    for gid, rule in table.forward.items():
        if rule.position_field or rule.target_ids is None:
            continue
        backs = set()
        ok = True
        for kid in rule.target_ids:
            back = table.reverse.get(kid)
            if back is None or back.target_ids is None:
                ok = False
                break
            backs.add(back.target_ids[0])
        if ok and backs == {gid}:
            out.add(gid)
    return out


def gif_grid(table: IdTable, ids: List[int], width: int = 16,
             robot: Tuple[int, int] = (1, 1), kitty: Tuple[int, int] = (2, 1),
             runs: Optional[Dict[int, List[int]]] = None) -> Level:
    """A gif level carrying ``ids`` laid out row by row, plus the two spawns.

    ``runs`` gives a gif id a set of VERTICAL run lengths instead of single
    cells -- that is how the gate ids get exercised at 1, 2, 3 and 4 tall.
    """
    runs = runs or {}
    empty = table.gif_empty
    plain = [i for i in ids if i not in runs]
    tall = {i: runs[i] for i in ids if i in runs}

    plain_rows = (len(plain) + width - 1) // width
    tall_rows = sum(max(lengths) + 1 for lengths in tall.values())
    # two rows for the spawns, the plain rows, a blank row, then one band per
    # tall id, then a blank row so nothing touches the bottom edge.
    height = max(2 + plain_rows + 1 + tall_rows + 1, 6)
    level = Level(space=GIF, width=width, height=height,
                  tiles=[empty] * (width * height), name="SYNTH")

    level.set(*robot, table.position_source_gif_id("robot_xy"))
    level.set(*kitty, table.position_source_gif_id("kitty_xy"))

    y = 2
    x = 0
    for gid in plain:
        if x >= width:
            x, y = 0, y + 1
        level.set(x, y, gid)
        x += 1
    y += 2 if plain else 1
    for gid, lengths in tall.items():
        x = 0
        for length in lengths:
            for dy in range(length):
                level.set(x, y + dy, gid)
            x += 2
        y += max(lengths) + 1
    if y >= height:
        raise AssertionError("fixture overflowed its own grid (%d rows, y=%d)" % (height, y))
    return level


def l1_gif(table: IdTable) -> Level:
    """The L1 round-trip fixture: every mappable id, gates at 1..4 tall."""
    mappable = sorted(mappable_gif_ids(table))
    gates = sorted(g for g in mappable if table.forward[g].shape == "vpair")
    plain = [g for g in mappable if g not in gates]
    return gif_grid(table, plain + gates, runs={g: [1, 2, 3, 4] for g in gates})


def unmappable_gif(table: IdTable) -> Level:
    """A gif carrying the class-(b) and class-(c) gif ids -- the report fixture."""
    degraded = sorted(
        gid for gid, rule in table.forward.items()
        if rule.cls in ("b", "c") and not rule.position_field
    )
    return gif_grid(table, degraded)


def kitty_level(table: IdTable, layouts: List[int], width: int = 16) -> Level:
    """A .kitty level carrying ``layouts``, with a robot and a kitty."""
    empty = table.kitty_empty
    height = max(4, 3 + (len(layouts) + width - 1) // width)
    level = Level(space=KITTY, width=width, height=height,
                  tiles=[empty] * (width * height), name="SYNTHK",
                  robot=(1.0, 1.0), kitty=(2.0, 1.0))
    x = y = 0
    for kid in layouts:
        if x >= width:
            x, y = 0, y + 1
        level.set(x, y + 2, kid)
        x += 1
    return level


def all_layouts_kitty(table: IdTable) -> Level:
    return kitty_level(table, sorted(table.reverse))


def mutant_table(tmp_path, table: IdTable, mutate) -> str:
    """Write a MUTATED copy of the table and return its path.

    The shipped data file is never edited: every mutant is a copy, reached through
    ``--id-table`` / ``IdTable.load(path)``.
    """
    raw = json.loads(json.dumps(table.raw))
    mutate(raw)
    path = str(tmp_path / "mutant-id-table.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    return path
