"""Raw map-bytes I/O -- one authored byte per cell, row-major, and nothing else.

This is the second CONTAINER, beside the indexed gif.  The Flash build embeds
its level as a ``DefineBinaryData`` blob and reads it with a plain loop::

    _loc1_.position = 0;
    while(_loc5_ < _loc1_.length) { _loc2_[_loc5_] = int(_loc1_.readUnsignedByte()); ... }
                                                            -- FLASH_PS:170-176

and then indexes that array as ``i % mapWidth`` / ``i / mapWidth``
(FLASH_PS:194, :204, :271), which is row-major.  So the file is exactly
``width * height`` unsigned bytes in reading order: no header, no dimensions,
no palette, no terminator.

⚠ **The dimensions are not in the file.**  In the game they are two constants
beside the loader (``mapWidth = 188``, ``mapHeight = 84`` -- FLASH_PS:41, :17),
which is fine for a program that ships with its own map and useless for a
converter handed a file.  So the caller states them, and a stated dimension is a
CLAIM ABOUT THE FILE rather than a setting: ``read`` multiplies the two and
refuses anything that is not exactly that many bytes, printing both numbers.
Getting this wrong is silent otherwise -- a level read one column too narrow is
the same cells sheared one step per row, and it still loads, still converts and
still passes every shape check downstream.

There is deliberately **no writer** here; see ``convert.py`` and the README's
"What is NOT here" for the 16..23 hazard that a reverse converter has to settle
first.  Which id table INTERPRETS these bytes is the other axis entirely
(``--dialect``): this module reads cells, not meanings.
"""

from __future__ import annotations

import os
from typing import Optional

from .level import Level
from .table import GIF


class RawFormatError(ValueError):
    pass


def read(path: str, width: int, height: int, name: Optional[str] = None) -> Level:
    """One byte per cell, row-major, into a ``gif``-space :class:`Level`.

    ``width`` and ``height`` are the caller's claim about a file that cannot
    state its own shape; both are checked against the byte count before a
    single cell is interpreted.
    """
    if width <= 0 or height <= 0:
        raise RawFormatError(
            "a raw map needs a positive width and height, not %dx%d" % (width, height)
        )
    with open(path, "rb") as fh:
        data = fh.read()
    expected = width * height
    if len(data) != expected:
        raise RawFormatError(
            "%s is %d byte(s), but --width %d --height %d claims %d cells "
            "(%d x %d). A raw map carries one byte per cell and no dimensions of "
            "its own, so the two numbers are a claim about THIS file: a wrong "
            "pair would shear the level one column per row and still convert."
            % (os.path.basename(path), len(data), width, height,
               expected, width, height)
        )
    return Level(space=GIF, width=width, height=height, tiles=list(data),
                 name=name or "")
