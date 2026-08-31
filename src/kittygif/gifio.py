"""Indexed-GIF I/O.

A level gif is one pixel per tile, and the palette is an authoring LEGEND -- the
colours are arbitrary distinct markers, not the tile's appearance.  The reader
therefore keys on the palette INDEX and never looks at RGB; the writer emits the
canonical measured RGB per id anyway, which is correct under either reading
(``palette.json`` records the evidence and the one conflict).
"""

from __future__ import annotations

from typing import Optional

from PIL import Image

from .level import Level
from .table import GIF, Palette


class GifFormatError(ValueError):
    pass


def read(path: str, name: Optional[str] = None) -> Level:
    with Image.open(path) as im:
        if im.mode != "P":
            raise GifFormatError(
                "%s is mode %r; a level gif must be INDEXED (mode 'P')" % (path, im.mode)
            )
        frames = getattr(im, "n_frames", 1)
        if frames != 1:
            raise GifFormatError("%s has %d frames; a level gif is a single frame" % (path, frames))
        width, height = im.size
        # Pillow 12 deprecates Image.getdata() in favour of get_flattened_data();
        # the package supports both, so pick whichever this Pillow has.
        flatten = getattr(im, "get_flattened_data", None) or im.getdata
        tiles = list(flatten())  # type: ignore[arg-type]
    return Level(space=GIF, width=width, height=height, tiles=tiles, name=name or "")


def write(level: Level, path: str, palette: Optional[Palette] = None) -> None:
    level.require_space(GIF)
    palette = palette or Palette.load()
    im = Image.new("P", (level.width, level.height))
    im.putpalette(palette.flat())
    im.putdata(level.tiles)
    # optimize=False is LOAD-BEARING, not a tuning knob: GifImagePlugin._save
    # defaults optimize to True when no palette= is passed, and an optimised save
    # RENUMBERS the palette down to the colours actually used -- which silently
    # rewrites every tile id in the file.  No transparency either: the whole
    # 256-entry table goes out and every index survives unrenumbered.
    im.save(path, format="GIF", optimize=False)
