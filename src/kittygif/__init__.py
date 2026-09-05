"""kittygif -- a level converter between two tile-map dialects and the ``.kitty``
v1 level container.

Two things vary independently.  The CONTAINER is how cells come off disk: an
indexed gif's palette indices (``gifio``) or one raw byte per cell (``rawio``).
The DIALECT is which id table says what those cells mean (``IdTable.load(
dialect=...)``) -- two games share this id space and disagree about part of it.

Unmappable content is never a refusal: the converter always emits and always
reports.  A table may still mark an id ``refuse``, meaning translating it is
dangerous rather than lossy, and then the conversion stops with the reason.

Every tile id, class tag, palette byte, refusal and default lives in
``data/id-table.json`` / ``data/id-table-flash.json`` and ``data/palette.json``;
the code knows packing formats only.
"""

from . import gifio, kittyio, rawio
from .convert import ConversionError, gif_to_kitty, kitty_to_gif
from .level import Level
from .report import Report
from .table import IdTable, Palette, TableError

__version__ = "0.2.1"

__all__ = [
    "ConversionError",
    "gifio",
    "kittyio",
    "rawio",
    "IdTable",
    "Level",
    "Palette",
    "Report",
    "TableError",
    "gif_to_kitty",
    "kitty_to_gif",
    "__version__",
]
