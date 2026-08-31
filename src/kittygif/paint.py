"""The 47-tile cr31 "blob" autotiler, transcribed from the in-game editor.

``WorldEditor::GetTileMatch47`` (WorldEditor.cpp) picks one of 47 blob tiles from
the eight neighbours; ``WorldEditor::IsTileMatch`` decides "same material" by
**paintID equality, not layout** -- so a paint REGION, not the terrain, drives the
edges, and out-of-bounds counts as different.  ``mPaint = style_base + blob``,
where the base comes from the table (``GetPaintBase`` returns ``47*tool``).

The decision tree below is the editor's, node for node.  It is packing-format
knowledge; every id, style name and base it is fed comes from the table.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from .level import Level
from .table import KITTY, IdTable

#: neighbour offsets, named the way the editor's ``STEP`` arithmetic names them
_N, _S, _E, _W = (0, -1), (0, 1), (1, 0), (-1, 0)
_NE, _SE, _SW, _NW = (1, -1), (1, 1), (-1, 1), (-1, -1)

Same = Callable[[int, int], bool]


def blob_index(same: Same) -> int:
    """0..46, from a predicate that answers "is the cell at (dx,dy) the same region?"."""

    def m(offset) -> bool:
        return same(offset[0], offset[1])

    if m(_N):
        if m(_E):
            if m(_S):
                if m(_W):
                    if m(_NE):
                        if m(_SE):
                            if m(_SW):
                                return 43 if m(_NW) else 39
                            return 40 if m(_NW) else 33
                        if m(_SW):
                            return 41 if m(_NW) else 37
                        return 36 if m(_NW) else 29
                    if m(_SE):
                        if m(_SW):
                            return 42 if m(_NW) else 34
                        return 38 if m(_NW) else 30
                    if m(_SW):
                        return 35 if m(_NW) else 31
                    return 1 if m(_NW) else 28
                if m(_NE):
                    return 18 if m(_SE) else 16
                return 17 if m(_SE) else 12
            if m(_W):
                if m(_NE):
                    return 27 if m(_NW) else 25
                return 26 if m(_NW) else 15
            return 8 if m(_NE) else 4
        if m(_S):
            if m(_W):
                if m(_SW):
                    return 24 if m(_NW) else 22
                return 23 if m(_NW) else 14
            return 45
        if m(_W):
            return 11 if m(_NW) else 7
        return 0
    if m(_E):
        if m(_S):
            if m(_W):
                if m(_SE):
                    return 21 if m(_SW) else 19
                return 20 if m(_SW) else 13
            return 9 if m(_SE) else 5
        if m(_W):
            return 46
        return 1
    if m(_S):
        if m(_W):
            return 10 if m(_SW) else 6
        return 2
    if m(_W):
        return 3
    return 44


def autopaint(
    level: Level,
    table: Optional[IdTable] = None,
    style: Optional[str] = None,
    region_id: int = 1,
) -> int:
    """Paint every paintable layout cell as ONE region, autotiled.

    Returns the number of cells painted.  ``region_id`` must be non-zero -- a
    cell draws its paint only when ``paintID != 0`` (``World::GetDisplayTile``).
    """
    table = table or IdTable.load()
    level.require_space(KITTY)
    if region_id == 0:
        raise ValueError("region_id 0 means 'unpainted'; pick a non-zero paint region")

    style = style or table.default_paint_style
    base = table.paint_base(style)
    paintable = set(table.paintable_layouts)

    painted: List[bool] = [tile in paintable for tile in level.tiles]

    def same_at(x: int, y: int) -> Same:
        def same(dx: int, dy: int) -> bool:
            nx, ny = x + dx, y + dy
            if not level.in_bounds(nx, ny):
                return False
            return painted[level.index(nx, ny)]

        return same

    level.paint = level.blank_plane()
    level.paint_id = level.blank_plane()
    count = 0
    for x, y, _tile in level.cells():
        i = level.index(x, y)
        if not painted[i]:
            continue
        level.paint[i] = base + blob_index(same_at(x, y))
        level.paint_id[i] = region_id
        count += 1
    return count
