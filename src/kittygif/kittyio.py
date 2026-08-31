"""``.kitty`` container I/O -- the v1 level format.

Container (``SaveGame.cpp``)::

    int32 fileVersion
    chunk                       # the main chunk
    int32 nestedSaveGameCount   # always 0 in a level file

    chunk := int32 payloadLen, payload[payloadLen], int32 childCount, child*

The main chunk of a level carries no payload and six children, in ``World::Sync``
order: name, grid, robot xy, kitty xy, extra game data, editor tool chunk.  A
cell is a little-endian uint32 bitfield: ``layout:7 | paint:9 | customDraw:1 |
extraData:6 | paintID:9``.

The v1 grid child comes in **two measured shapes**: ``8 + w*h*4`` (the cells
alone) or ``8 + w*h*4 + w*h`` (the cells plus the ``mLevelMap`` byte array).
Six of the eleven campaign levels use the first, five the second, and the split
lines up exactly with the extra chunk's 71/72-byte split.  Neither shape carries
the radio-text sub-chunk the current engine writes.  The reader takes either and
preserves what it found; the writer emits the shorter one, which is the pinned
donor's.

Only file version 1 is in scope.  A newer savegame version is refused with a
message that says so rather than mis-parsing.

Every id, field name, field type and default in here comes from the table.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from .level import Level
from .table import KITTY, IdTable

# --- the cell bitfield, widths straight from paint.packing -------------------
_FIELDS = (("layout", 7), ("paint", 9), ("custom_draw", 1), ("extra_data", 6), ("paint_id", 9))


class KittyFormatError(ValueError):
    pass


class UnsupportedVersionError(KittyFormatError):
    pass


def pack_cell(layout: int = 0, paint: int = 0, custom_draw: int = 0,
              extra_data: int = 0, paint_id: int = 0) -> int:
    values = (layout, paint, custom_draw, extra_data, paint_id)
    word = shift = 0
    for value, (name, bits) in zip(values, _FIELDS):
        if not 0 <= value < (1 << bits):
            raise KittyFormatError("%s=%d does not fit in %d bits" % (name, value, bits))
        word |= value << shift
        shift += bits
    return word


def unpack_cell(word: int) -> Tuple[int, int, int, int, int]:
    out: List[int] = []
    shift = 0
    for _name, bits in _FIELDS:
        out.append((word >> shift) & ((1 << bits) - 1))
        shift += bits
    return tuple(out)  # type: ignore[return-value]


# --- primitives (rapt_iobuffer.cpp / SaveGame.cpp) ---------------------------
def _i32(value: int) -> bytes:
    return struct.pack("<i", value)


def _f32(value: float) -> bytes:
    return struct.pack("<f", value)


def _string(text: str) -> bytes:
    """int32 length INCLUDING the NUL, then the bytes."""
    raw = text.encode("latin1") + b"\0"
    return _i32(len(raw)) + raw


def _read_string(payload: bytes, offset: int) -> Tuple[str, int]:
    (length,) = struct.unpack_from("<i", payload, offset)
    offset += 4
    return payload[offset : offset + length - 1].decode("latin1"), offset + length


@dataclass
class Chunk:
    payload: bytes = b""
    children: List["Chunk"] = field(default_factory=list)

    def to_bytes(self) -> bytes:
        out = [_i32(len(self.payload)), self.payload, _i32(len(self.children))]
        out.extend(child.to_bytes() for child in self.children)
        return b"".join(out)


def _read_chunk(data: bytes, offset: int) -> Tuple[Chunk, int]:
    (length,) = struct.unpack_from("<i", data, offset)
    offset += 4
    if length < 0 or offset + length > len(data):
        raise KittyFormatError("chunk claims %d payload bytes, past the end of the file" % length)
    payload = data[offset : offset + length]
    offset += length
    (count,) = struct.unpack_from("<i", data, offset)
    offset += 4
    children = []
    for _ in range(count):
        child, offset = _read_chunk(data, offset)
        children.append(child)
    return Chunk(payload, children), offset


# --- level read / write ------------------------------------------------------
_NAME, _GRID, _ROBOT, _KITTY, _EXTRA, _EDITOR = range(6)


def read(path: str, table: Optional[IdTable] = None) -> Level:
    table = table or IdTable.load()
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 8:
        raise KittyFormatError("%s is %d bytes -- not a .kitty" % (path, len(data)))

    (version,) = struct.unpack_from("<i", data, 0)
    if version != table.file_version:
        raise UnsupportedVersionError(
            "%s is savegame version %d (0x%04x); this converter reads version %d only -- "
            "the v1 level container the campaign and the editor's v1 path write. "
            "A newer file carries an mLevelMap array and a radio-text sub-chunk that v1 has not."
            % (path, version, version, table.file_version)
        )
    main, offset = _read_chunk(data, 4)
    expected_children = len(table.container["children"])
    if len(main.children) < expected_children:
        raise KittyFormatError(
            "%s has %d child chunks; a v1 level has %d (%s)"
            % (path, len(main.children), expected_children,
               ", ".join(table.container["children"])) )

    name, _ = _read_string(main.children[_NAME].payload, 0)

    grid = main.children[_GRID].payload
    width, height = struct.unpack_from("<ii", grid, 0)
    if width <= 0 or height <= 0:
        raise KittyFormatError("%s declares a %dx%d grid" % (path, width, height))
    cells_bytes = 8 + width * height * 4
    # The v1 grid chunk comes in TWO measured shapes: the cells alone, or the
    # cells plus a trailing mLevelMap byte array (one MAPTYPE per cell, the
    # revealed-map state).  Both are file version 1 and both load.  Anything else
    # is a container this reader does not know.
    with_map = cells_bytes + width * height
    if len(grid) not in (cells_bytes, with_map):
        raise KittyFormatError(
            "%s: the grid chunk is %d bytes; a %dx%d v1 grid is %d (cells only) or "
            "%d (cells + the mLevelMap array).  Neither matches, so this is not a "
            "v1 grid chunk."
            % (path, len(grid), width, height, cells_bytes, with_map)
        )
    if main.children[_GRID].children:
        raise KittyFormatError(
            "%s: the grid chunk has %d sub-chunk(s); the v1 grid has none (the "
            "radio-text sub-chunk belongs to the newer container)."
            % (path, len(main.children[_GRID].children))
        )
    level_map = grid[cells_bytes:] or None
    cells = struct.unpack_from("<%dI" % (width * height), grid, 8)

    tile = float(table.tile_size_px)
    rx, ry = struct.unpack_from("<ff", main.children[_ROBOT].payload, 0)
    kx, ky = struct.unpack_from("<ff", main.children[_KITTY].payload, 0)

    planes = [list(plane) for plane in zip(*(unpack_cell(c) for c in cells))]
    return Level(
        space=KITTY,
        width=width,
        height=height,
        tiles=planes[0],
        name=name,
        robot=(rx / tile, ry / tile),
        kitty=(kx / tile, ky / tile),
        paint=planes[1],
        custom_draw=planes[2],
        extra_data=planes[3],
        paint_id=planes[4],
        level_map=level_map,
        settings_chunk=main.children[_EXTRA].payload,
        editor_chunk=main.children[_EDITOR].payload,
        file_version=version,
    )


def settings_chunk(table: IdTable) -> bytes:
    """The pinned donor settings block, serialised from the table's FIELD LIST.

    Not a copied blob: each field is written by its declared type in
    ``World::Sync`` order.  Fields marked ``optional`` belong to the longer
    variant and are left out, which is what reproduces the donor's byte count.
    """
    out = bytearray()
    for spec in table.settings["fields"]:
        if spec.get("optional"):
            continue
        kind, value = spec["type"], spec["value"]
        if kind == "String":
            out += _string(value)
        elif kind == "float":
            out += _f32(value)
        elif kind == "int":
            out += _i32(value)
        elif kind == "bool":
            out += bytes([1 if value else 0])
        elif kind == "Point":
            out += _f32(value[0]) + _f32(value[1])
        else:
            raise KittyFormatError("settings field %r has unknown type %r" % (spec["name"], kind))
    want = table.settings.get("chunk_bytes")
    if want is not None and len(out) != want:
        raise KittyFormatError(
            "the settings block serialised to %d bytes, but the donor is %d -- "
            "the field list and the measured chunk disagree" % (len(out), want)
        )
    return bytes(out)


def to_bytes(level: Level, table: Optional[IdTable] = None) -> bytes:
    table = table or IdTable.load()
    level.require_space(KITTY)

    paint = level.paint or level.blank_plane()
    paint_id = level.paint_id or level.blank_plane()
    # customDraw and extraData are computed at load in every campaign level, so a
    # writer emits zero (settings_donor.runtime_only_fields).
    custom_draw = level.blank_plane()
    extra_data = level.blank_plane()

    cells = [
        pack_cell(layout, p, cd, ed, pid)
        for layout, p, cd, ed, pid in zip(level.tiles, paint, custom_draw, extra_data, paint_id)
    ]
    grid = struct.pack("<ii", level.width, level.height) + struct.pack(
        "<%dI" % len(cells), *cells
    )
    if level.level_map is not None:
        # Carried through only when the source file had one; a converter WRITING a
        # level emits the shorter shape, which is what the donor uses.
        if len(level.level_map) != level.width * level.height:
            raise KittyFormatError(
                "the mLevelMap array is %d bytes, but the grid is %d cells"
                % (len(level.level_map), level.width * level.height)
            )
        grid += level.level_map

    tile = float(table.tile_size_px)
    robot = level.robot or (0.0, 0.0)
    kitty = level.kitty or (0.0, 0.0)

    editor = level.editor_chunk
    if editor is None:
        # mPaintID is the editor's NEXT paint-region id: it must stay above every
        # region this writer laid down.
        editor = _i32(max(paint_id) + 1 if paint_id else 0)

    main = Chunk(
        b"",
        [
            Chunk(_string(level.name)),
            Chunk(grid),
            Chunk(struct.pack("<ff", robot[0] * tile, robot[1] * tile)),
            Chunk(struct.pack("<ff", kitty[0] * tile, kitty[1] * tile)),
            Chunk(level.settings_chunk if level.settings_chunk is not None
                  else settings_chunk(table)),
            Chunk(editor),
        ],
    )
    # The trailing int32 is SaveGame's nested-savegame count (SaveGame.cpp:205-231).
    return _i32(table.file_version) + main.to_bytes() + _i32(0)


def write(level: Level, path: str, table: Optional[IdTable] = None) -> None:
    with open(path, "wb") as fh:
        fh.write(to_bytes(level, table))
