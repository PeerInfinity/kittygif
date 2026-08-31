"""The page's Python side: the real ``kittygif`` package, nothing re-implemented.

Bytes cross the boundary through Pyodide's filesystem rather than through JSON,
so a 150 kB campaign level does not become a 200 kB base64 string.  Everything
else -- the report, the viewer pair the preview is drawn from, the level facts --
comes back as one JSON document.
"""

import json
import os

from kittygif import __version__, convert, gifio, kittyio, viewer
from kittygif.table import IdTable, Palette
from kittygif.viewer import ViewerTraits

TABLE = IdTable.load(None)
PALETTE = Palette.load(None)
TRAITS = ViewerTraits.load(None)

GIF_MAGIC = (b"GIF87a", b"GIF89a")


def boot_info():
    """What the page needs before any file is dropped."""
    return json.dumps({
        "kittygif": __version__,
        "table": os.path.basename(TABLE.path),
        # The overwrite slots are the dialect's own level files, read off the
        # table's census -- not a list typed into this page.
        "slots": TABLE.gif_level_files,
        "readable_versions": sorted(TABLE.read_layouts),
        "written_version": TABLE.file_version,
        "tile_size_px": TABLE.tile_size_px,
    })


def detect(path):
    with open(path, "rb") as fh:
        head = fh.read(6)
    return "gif" if head in GIF_MAGIC else "kitty"


def run(in_path, out_path, filename):
    """Convert ``in_path`` -> ``out_path``; return the page's JSON payload."""
    space = detect(in_path)
    # The CLI names a .kitty after its output file; do the same here so the page
    # and the command line put the same name inside the container.
    stem = os.path.splitext(os.path.basename(filename))[0].upper()

    if space == "gif":
        level = gifio.read(in_path)
        produced, report = convert.gif_to_kitty(level, TABLE, name=stem)
        with open(out_path, "wb") as fh:
            fh.write(kittyio.to_bytes(produced, TABLE))
        out_ext, direction = ".kitty", "gif2kitty"
    else:
        level = kittyio.read(in_path, TABLE)
        produced, report = convert.kitty_to_gif(level, TABLE)
        gifio.write(produced, out_path, PALETTE)
        out_ext, direction = ".gif", "kitty2gif"

    tilemap = viewer.tilemap_json(produced, TABLE, source=filename)
    config = viewer.category_config(TABLE, produced.space, palette=PALETTE,
                                    traits=TRAITS, game=tilemap["game"])
    return json.dumps({
        "direction": direction,
        "out_ext": out_ext,
        "source": {
            "space": level.space,
            "name": level.name,
            "grid": [level.width, level.height],
            "file_version": level.file_version,
            "robot": list(level.robot) if level.robot else None,
            "kitty": list(level.kitty) if level.kitty else None,
        },
        "produced": {"space": produced.space, "name": produced.name},
        "report": report.to_json(),
        "report_text": report.to_text(),
        "tilemap": tilemap,
        "config": config,
    })
