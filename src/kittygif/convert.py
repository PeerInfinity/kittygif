"""Both directions, with the report.

``gif -> kitty`` is near-total: only RWIA's water and its Shooter enemy have no
C++ counterpart.  ``kitty -> gif`` is the heavier partial direction -- some forty
C++-only mechanics have to be substituted.  Neither direction ever refuses a
file; both say what they did (see ``report.py``).

The rules all come from the table.  This module knows only:

  * how to walk a grid,
  * that a ``shape: "vpair"`` target is a vertical door couple,
  * that a position row moves a spawn FIELD instead of a cell.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .level import Level
from .paint import autopaint
from .report import Report
from .table import GIF, GIF_TO_KITTY, KITTY, KITTY_TO_GIF, IdTable, Rule


class ConversionError(ValueError):
    pass


# --------------------------------------------------------------------- gif -> kitty
def gif_to_kitty(
    level: Level,
    table: Optional[IdTable] = None,
    name: str = "",
    paint_style: Optional[str] = None,
    paint: bool = True,
) -> Tuple[Level, Report]:
    table = table or IdTable.load()
    level.require_space(GIF)

    report = Report(
        direction=GIF_TO_KITTY,
        width=level.width,
        height=level.height,
        table_path=table.path,
    )
    empty = table.kitty_empty
    tiles = [empty] * (level.width * level.height)
    positions: Dict[str, Tuple[int, int]] = {}
    vpair_cells: Dict[int, List[Tuple[int, int]]] = {}
    unknown: List[Tuple[int, int, int]] = []

    for x, y, gid in level.cells():
        rule = table.forward.get(gid)
        if rule is None:
            unknown.append((x, y, gid))
            continue
        if rule.position_field:
            if rule.position_field in positions:
                first = positions[rule.position_field]
                raise ConversionError(
                    "gif id %d (%s) appears at (%d,%d) and again at (%d,%d); "
                    "a level has exactly one"
                    % (gid, rule.source_name, first[0], first[1], x, y)
                )
            positions[rule.position_field] = (x, y)
            report.record(rule.cls, gid, rule.source_name, None,
                          rule.target_name, rule.note, x, y)
            continue
        if rule.shape == "vpair":
            vpair_cells.setdefault(gid, []).append((x, y))
            continue
        target = rule.target_id
        tiles[y * level.width + x] = target
        report.record(rule.cls, gid, rule.source_name, target,
                      table.kitty_name(target), rule.note, x, y)

    if unknown:
        ids = sorted({gid for _x, _y, gid in unknown})
        raise ConversionError(
            "the gif carries %d cells with id(s) %s, which the table does not know. "
            "This is either a level from another RWIA game (another dialect needs "
            "another table) or a table gap -- fix the DATA, not the code."
            % (len(unknown), ", ".join(str(i) for i in ids))
        )

    for gid, cells in vpair_cells.items():
        _place_vpairs(level, tiles, table, table.forward[gid], gid, cells, report)

    out = Level(
        space=KITTY,
        width=level.width,
        height=level.height,
        tiles=tiles,
        name=name or level.name,
    )

    for field_name in table.position_field_names:
        cell = positions.get(field_name)
        if cell is None:
            # Not an unmappable-content case (which is always emitted with a
            # report): a level gif with no spawn pixel is MALFORMED input.  Every
            # measured RWK gif carries exactly one of each.
            raise ConversionError(
                "the gif carries no id-%d pixel, so the level has no %s"
                % (table.position_source_gif_id(field_name), field_name)
            )
        setattr(out, _position_attr(out, field_name), (float(cell[0]), float(cell[1])))

    if paint:
        painted = autopaint(out, table, style=paint_style)
        report.notes.append(
            "paint: %d cells painted as one region in the %r style (the ruled default "
            "for this direction; a gif carries no paint information at all)"
            % (painted, paint_style or table.default_paint_style)
        )
    return out, report


def _position_attr(level: Level, field_name: str) -> str:
    """Bind a table position FIELD (``robot_xy``) to the Level attribute holding it."""
    attr = field_name[:-3] if field_name.endswith("_xy") else field_name
    if not hasattr(level, attr):
        raise ConversionError(
            "the table names a position field %r, but the level model has no %r to "
            "put it in" % (field_name, attr)
        )
    return attr


def _place_vpairs(level: Level, tiles: List[int], table: IdTable, rule: Rule,
                  gid: int, cells: List[Tuple[int, int]], report: Report) -> None:
    """Tile each vertical RUN of a gate id into (top, bottom) door couples.

    The gif gate is a run of one id, any height; a C++ door is exactly two cells,
    top and bottom, and opening one removes only its own partner.  Runs are
    therefore paired from the BOTTOM up, and a leftover single cell takes the TOP
    id -- a lone half opens by itself, so no cell is left permanently shut.
    """
    assert rule.target_ids is not None
    top_id, bottom_id = rule.target_ids
    columns: Dict[int, List[int]] = {}
    for x, y in cells:
        columns.setdefault(x, []).append(y)

    odd_runs = 0
    for x, ys in columns.items():
        for run in _runs(sorted(ys)):
            if len(run) % 2:
                odd_runs += 1
            # bottom-up: ..., (top,bottom), (top,bottom); an odd cell at the very
            # top is written as a lone top half.
            for offset, y in enumerate(reversed(run)):
                is_bottom = offset % 2 == 0
                target = bottom_id if is_bottom else top_id
                if offset == len(run) - 1 and len(run) % 2:
                    target = top_id
                tiles[y * level.width + x] = target
                report.record(rule.cls, gid, rule.source_name, target,
                              table.kitty_name(target), rule.note, x, y)
    if odd_runs:
        report.notes.append(
            "gate shape: %d run(s) of gif id %d (%s) are not two cells tall; a C++ door "
            "is exactly a top/bottom couple, so runs are paired bottom-up and an odd "
            "top cell becomes a lone top half (it opens on its own)"
            % (odd_runs, gid, rule.source_name)
        )


def _runs(ys: List[int]) -> List[List[int]]:
    out: List[List[int]] = []
    for y in ys:
        if out and out[-1][-1] == y - 1:
            out[-1].append(y)
        else:
            out.append([y])
    return out


# --------------------------------------------------------------------- kitty -> gif
def kitty_to_gif(level: Level, table: Optional[IdTable] = None) -> Tuple[Level, Report]:
    table = table or IdTable.load()
    level.require_space(KITTY)

    report = Report(
        direction=KITTY_TO_GIF,
        width=level.width,
        height=level.height,
        table_path=table.path,
    )
    empty = table.gif_empty
    tiles = [empty] * (level.width * level.height)
    unknown: List[int] = []

    for x, y, kid in level.cells():
        rule = table.reverse.get(kid)
        if rule is None:
            unknown.append(kid)
            continue
        assert rule.target_ids is not None
        target = rule.target_ids[0]
        tiles[y * level.width + x] = target
        report.record(rule.cls, kid, rule.source_name, target,
                      table.gif_name(target), rule.note, x, y)

    if unknown:
        raise ConversionError(
            "the level carries layout id(s) %s, which the table does not know -- "
            "fix the DATA, not the code." % ", ".join(str(i) for i in sorted(set(unknown)))
        )

    out = Level(space=GIF, width=level.width, height=level.height, tiles=tiles,
                name=level.name)

    for field_name in table.position_field_names:
        pos = getattr(level, _position_attr(level, field_name))
        if pos is None:
            continue
        gid = table.position_source_gif_id(field_name)
        x, y = int(round(pos[0])), int(round(pos[1]))
        if not out.in_bounds(x, y):
            report.notes.append(
                "%s sits at tile (%.2f,%.2f), outside the %dx%d grid; its pixel was "
                "not written" % (field_name, pos[0], pos[1], out.width, out.height)
            )
            continue
        replaced = tiles[y * out.width + x]
        out.set(x, y, gid)
        if replaced != empty:
            report.notes.append(
                "%s's pixel at (%d,%d) overwrote %s -- a spawn is a FIELD on the .kitty "
                "side but a CELL on the gif side, so the two cannot both be there"
                % (field_name, x, y, table.gif_name(replaced))
            )

    painted = sum(1 for pid in (level.paint_id or []) if pid)
    if painted:
        report.notes.append(
            "paint: %d painted cell(s) dropped -- a gif has no paint plane. Cosmetic "
            "only (a painted cell keeps its layout; only its appearance is lost)."
            % painted
        )
    for plane_name, plane in (("customDraw", level.custom_draw), ("extraData", level.extra_data)):
        set_cells = sum(1 for v in (plane or []) if v)
        if set_cells:
            report.notes.append(
                "%s was set on %d cell(s) and is dropped; it is computed at load anyway."
                % (plane_name, set_cells)
            )
    return out, report
