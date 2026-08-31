"""The neutral grid model both formats read and write.

``.gif  <->  Level  <->  .kitty``.  A ``Level`` is always stamped with the id
SPACE its ``tiles`` are written in (``"gif"`` or ``"kitty"``) -- the two spaces
are different numberings of overlapping vocabularies, and silently mixing them
is the one mistake this model exists to make impossible.

Positions are in TILE units (floats), so a level is resolution-independent; the
``.kitty`` writer multiplies by ``tile_size_px`` on the way out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Pos = Tuple[float, float]


@dataclass
class Level:
    space: str
    width: int
    height: int
    tiles: List[int]
    name: str = ""
    robot: Optional[Pos] = None
    kitty: Optional[Pos] = None

    # ---- .kitty-only cell planes; None means "this level was never a .kitty"
    paint: Optional[List[int]] = None
    paint_id: Optional[List[int]] = None
    custom_draw: Optional[List[int]] = None
    extra_data: Optional[List[int]] = None

    #: the v1 grid chunk's OPTIONAL trailing mLevelMap byte array (one MAPTYPE per
    #: cell: the revealed-map state).  Present in 5 of the 11 campaign levels and
    #: absent in the other 6 -- see kitty_file.grid_chunk in the table.
    level_map: Optional[bytes] = None

    # ---- .kitty-only opaque chunks, preserved so a .kitty round-trips byte-exact
    settings_chunk: Optional[bytes] = None
    editor_chunk: Optional[bytes] = None
    file_version: Optional[int] = None

    #: anything the converter wants to say about how this level was produced
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.tiles) != self.width * self.height:
            raise ValueError(
                "tiles is %d cells, but the grid is %dx%d"
                % (len(self.tiles), self.width, self.height)
            )

    # ------------------------------------------------------------------ indexing
    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def at(self, x: int, y: int) -> int:
        return self.tiles[self.index(x, y)]

    def set(self, x: int, y: int, value: int) -> None:
        self.tiles[self.index(x, y)] = value

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def cells(self):
        for y in range(self.height):
            row = y * self.width
            for x in range(self.width):
                yield x, y, self.tiles[row + x]

    def require_space(self, space: str) -> None:
        if self.space != space:
            raise ValueError(
                "this level's tiles are in the %r id space, not %r" % (self.space, space)
            )

    def blank_plane(self) -> List[int]:
        return [0] * (self.width * self.height)
