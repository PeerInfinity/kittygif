"""kittygif -- a level converter between the RWIA ``.gif`` dialect and the
``.kitty`` v1 level container.

Both directions are partial, so the converter always emits and always reports.
Every tile id, class tag, palette byte and default lives in ``data/id-table.json``
and ``data/palette.json``; the code knows packing formats only.
"""

from .convert import ConversionError, gif_to_kitty, kitty_to_gif
from .level import Level
from .report import Report
from .table import IdTable, Palette, TableError

__version__ = "0.1.0"

__all__ = [
    "ConversionError",
    "IdTable",
    "Level",
    "Palette",
    "Report",
    "TableError",
    "gif_to_kitty",
    "kitty_to_gif",
    "__version__",
]
