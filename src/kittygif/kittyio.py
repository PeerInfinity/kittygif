"""``.kitty`` container I/O -- the v1 level format.

Container (``SaveGame.cpp``)::

    int32 fileVersion
    chunk                       # the main chunk
    int32 nestedSaveGameCount   # always 0 in a level file

    chunk := int32 payloadLen, payload[payloadLen], int32 childCount, child*

The main chunk of a level carries no payload and a handful of children.  A cell
is a little-endian uint32 bitfield: ``layout:7 | paint:9 | customDraw:1 |
extraData:6 | paintID:9``.

TWO container versions are readable, and which child is which comes from the
table (``kitty_file.read_layouts``), not from this file:

* **v1** -- six children: name, grid, robot xy, kitty xy, extra game data,
  editor tool chunk.  The 11 campaign levels and this converter's own output.
* **v16** (``SAVEGAME_VERSION 0x0010``) -- five children: a wider metadata chunk
  (upload id, name, tags, paint id, two test flags, flag bits) in place of the
  bare name, then the same four body chunks and no editor chunk.  This is what
  the Maker Mall editor at ``robotwantskitty.com/web`` writes.

``World::Sync`` -- the body -- is version-independent, so both versions share
one parser below the metadata chunk.  The WRITER only ever emits v1: that is the
shape proven against the engine oracle and the one RWIA-facing conversions need.

The v1 grid child comes in **two measured shapes**: ``8 + w*h*4`` (the cells
alone) or ``8 + w*h*4 + w*h`` (the cells plus the ``mLevelMap`` byte array).
Six of the eleven campaign levels use the first, five the second, and the split
lines up exactly with the extra chunk's 71/72-byte split.  At v1 neither shape
carries the radio-text sub-chunk; at v16 the grid chunk always does, and the
table says so per version.  The reader takes either and preserves what it found;
the writer emits the shorter one, which is the pinned donor's.

A version with no layout in the table is refused with a message naming the ones
there are, rather than mis-parsing.

Every id, field name, field type and default in here comes from the table.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from .level import Level
from .table import KITTY, IdTable, TableError

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


def read(path: str, table: Optional[IdTable] = None) -> Level:
    table = table or IdTable.load()
    with open(path, "rb") as fh:
        data = fh.read()
    return from_bytes(data, table, where=path)


def from_bytes(data: bytes, table: Optional[IdTable] = None,
               where: str = "<bytes>") -> Level:
    """Parse a ``.kitty`` already in memory.  ``read`` is this plus a file open."""
    table = table or IdTable.load()
    if len(data) < 8:
        raise KittyFormatError("%s is %d bytes -- not a .kitty" % (where, len(data)))

    (version,) = struct.unpack_from("<i", data, 0)
    try:
        layout = table.read_layout(version)
    except TableError as exc:
        raise UnsupportedVersionError(
            "%s is savegame version %d (0x%04x), which this converter does not read. %s"
            % (where, version, version, exc)
        )
    main, _ = _read_chunk(data, 4)
    want = int(layout["child_count"])
    if len(main.children) < want:
        raise KittyFormatError(
            "%s has %d child chunks; a version-%d level has %d"
            % (where, len(main.children), version, want)
        )

    # Where the level name sits inside the metadata chunk: v1's metadata chunk IS
    # the name, v16's puts a 4-byte mUploadID in front of it.
    meta = main.children[int(layout["name_child"])].payload
    name, _ = _read_string(meta, int(layout["name_offset"]))

    grid_chunk = main.children[int(layout["grid"])]
    grid = grid_chunk.payload
    width, height = struct.unpack_from("<ii", grid, 0)
    if width <= 0 or height <= 0:
        raise KittyFormatError("%s declares a %dx%d grid" % (where, width, height))
    cells_bytes = 8 + width * height * 4
    # The grid chunk comes in TWO measured shapes: the cells alone, or the cells
    # plus a trailing mLevelMap byte array (one MAPTYPE per cell, the revealed-map
    # state).  Both load.  Anything else is a container this reader does not know.
    with_map = cells_bytes + width * height
    if len(grid) not in (cells_bytes, with_map):
        raise KittyFormatError(
            "%s: the grid chunk is %d bytes; a %dx%d grid is %d (cells only) or "
            "%d (cells + the mLevelMap array).  Neither matches, so this is not a "
            "grid chunk this reader knows."
            % (where, len(grid), width, height, cells_bytes, with_map)
        )
    # The radio-text list is a sub-chunk of the grid chunk, and whether the version
    # writes one is a table fact -- v1 never does, v16 always does.
    allowed = int(layout["grid_subchunks"])
    if len(grid_chunk.children) != allowed:
        raise KittyFormatError(
            "%s: the grid chunk has %d sub-chunk(s); a version-%d grid has %d "
            "(the radio-text sub-chunk)."
            % (where, len(grid_chunk.children), version, allowed)
        )
    level_map = grid[cells_bytes:] or None
    cells = struct.unpack_from("<%dI" % (width * height), grid, 8)

    tile = float(table.tile_size_px)
    rx, ry = struct.unpack_from("<ff", main.children[int(layout["robot"])].payload, 0)
    kx, ky = struct.unpack_from("<ff", main.children[int(layout["kitty"])].payload, 0)

    editor_index = layout["editor"]
    editor_chunk = (None if editor_index is None
                    else main.children[int(editor_index)].payload)

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
        settings_chunk=main.children[int(layout["extra"])].payload,
        editor_chunk=editor_chunk,
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

    settings = level.settings_chunk
    if settings is not None and level.file_version not in (None, table.file_version):
        # A newer container's extra chunk is a WIDER field list (v16 adds coins,
        # the conveyor speeds and the custom-song slots -- World::Sync grew), so it
        # cannot be carried into a v1 file.  Fall back to the pinned donor block.
        settings = None

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
            Chunk(settings if settings is not None else settings_chunk(table)),
            Chunk(editor),
        ],
    )
    # The trailing int32 is SaveGame's nested-savegame count (SaveGame.cpp:205-231).
    return _i32(table.file_version) + main.to_bytes() + _i32(0)


def write(level: Level, path: str, table: Optional[IdTable] = None) -> None:
    with open(path, "wb") as fh:
        fh.write(to_bytes(level, table))
