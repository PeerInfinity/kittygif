"""``kittygif`` -- the command line.

    kittygif gif2kitty LEVEL.gif OUT.kitty [--name NAME] [--paint-style panels]
    kittygif raw2kitty MAP.bin OUT.kitty --width W --height H [--dialect flash]
    kittygif kitty2gif LEVEL.kitty OUT.gif
    kittygif info FILE... [--width W --height H]
    kittygif emit-json LEVEL.{gif,bin,kitty} OUT_PREFIX

Two orthogonal choices run through all of these.  The SUBCOMMAND picks the
container -- an indexed gif's palette indices, one raw byte per cell, or the
``.kitty`` chunk tree -- and ``--dialect`` picks the id table that interprets
the cells.  ``--id-table PATH`` still outranks both, which is how the mutant
gates run without ever editing the shipped data.

⚠ ``raw2kitty``'s ``--width``/``--height`` are REQUIRED and are a claim about
the file, not a preference: a raw map states no dimensions of its own, so the
reader multiplies them out and refuses a file that is not exactly that many
bytes.  ``info`` wants the same two before it will read one.

Every subcommand writes its report: the human summary on stderr, and the
machine-readable JSON to ``--report PATH`` (or to stdout with ``--report -``).

``emit-json`` writes the two files Archipelago-CC's ``tileMapAnalyzer`` panel
loads -- ``<PREFIX>_tilemap.json`` and ``<PREFIX>_tiles.json``.  ⛔ THOSE TWO
SUFFIXES ARE THE CONTRACT, not decoration: the panel's data files are
deliberately gitignored on that side by exactly those two glob patterns, so a
prefix keeps a generated map out of a tracked tree by construction.  The same
pair can be written as a by-product of a conversion with ``--emit-json PREFIX``,
which emits the level the conversion PRODUCED.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__, gifio, kittyio, rawio, viewer
from .convert import ConversionError, gif_to_kitty, kitty_to_gif
from .report import Report
from .table import DEFAULT_DIALECT, DIALECTS, GIF, IdTable, Palette, TableError
from .viewer import ViewerTraits


def _table(args) -> IdTable:
    table = IdTable.load(args.id_table, dialect=args.dialect)
    problems = table.check()
    if problems:
        raise TableError(
            "%s is inconsistent:\n  %s" % (table.path, "\n  ".join(problems))
        )
    return table


#: the two suffixes tileMapAnalyzer's data files carry (and Archipelago-CC's
#: .gitignore excludes): `<prefix>_tilemap.json` and `<prefix>_tiles.json`.
TILEMAP_SUFFIX = "_tilemap.json"
CONFIG_SUFFIX = "_tiles.json"


def _viewer_paths(args, prefix: str):
    tilemap = getattr(args, "tilemap", None) or prefix + TILEMAP_SUFFIX
    config = getattr(args, "config", None) or prefix + CONFIG_SUFFIX
    return tilemap, config


def _emit_viewer(level, table, args, prefix: str, source: str) -> None:
    tilemap, config = _viewer_paths(args, prefix)
    summary = viewer.emit(
        level, table, tilemap, config,
        palette=Palette.load(args.palette),
        traits=ViewerTraits.load(args.viewer_traits),
        source=source,
    )
    if not args.quiet:
        print("emit-json: %s %dx%d -> %s + %s (%d categories, %d distinct ids)"
              % (summary["space"], summary["grid"][0], summary["grid"][1],
                 summary["tilemap"], summary["config"],
                 summary["categories"], summary["distinct_ids"]),
              file=sys.stderr)
        if summary["ids_without_a_category"]:
            print("emit-json: ⚠ ids the table does not cover, drawn as %r: %s"
                  % (viewer.ViewerTraits.load(args.viewer_traits).default_category,
                     summary["ids_without_a_category"]), file=sys.stderr)


def _emit_report(report: Report, args) -> None:
    if not args.quiet:
        print(report.to_text(), file=sys.stderr)
    if args.report:
        payload = json.dumps(report.to_json(), indent=1)
        if args.report == "-":
            print(payload)
        else:
            with open(args.report, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")


def _to_kitty(args, level) -> int:
    """The shared tail of every ``* -> .kitty`` conversion.

    Only the CONTAINER differs between ``gif2kitty`` and ``raw2kitty``: once the
    cells are in a ``gif``-space :class:`~kittygif.level.Level` there is one
    conversion, one report and one writer.  Keeping that in one place is what
    makes "the container and the dialect are orthogonal" a property of the code
    rather than a claim about it.
    """
    table = _table(args)
    name = args.name or os.path.splitext(os.path.basename(args.target))[0].upper()
    out, report = gif_to_kitty(
        level, table, name=name, paint_style=args.paint_style, paint=not args.no_paint
    )
    report.source, report.target = args.source, args.target
    kittyio.write(out, args.target, table)
    _emit_report(report, args)
    if args.emit_json:
        _emit_viewer(out, table, args, args.emit_json, args.target)
    return 0


def _cmd_gif2kitty(args) -> int:
    return _to_kitty(args, gifio.read(args.source))


def _cmd_raw2kitty(args) -> int:
    return _to_kitty(args, rawio.read(args.source, args.width, args.height))


def _cmd_kitty2gif(args) -> int:
    table = _table(args)
    level = kittyio.read(args.source, table)
    out, report = kitty_to_gif(level, table)
    report.source, report.target = args.source, args.target
    gifio.write(out, args.target, Palette.load(args.palette))
    _emit_report(report, args)
    if args.emit_json:
        _emit_viewer(out, table, args, args.emit_json, args.target)
    return 0


def _cmd_info(args) -> int:
    table = _table(args)
    for path in args.files:
        level = _read_any(path, table, args)
        counts: dict = {}
        for _x, _y, tile in level.cells():
            counts[tile] = counts.get(tile, 0) + 1
        namer = table.gif_name if level.space == GIF else table.kitty_name
        version = ("  container v%d" % level.file_version
                   if level.file_version is not None else "")
        print("%s  [%s]  %dx%d  name=%r%s" % (path, level.space, level.width,
                                              level.height, level.name, version))
        if level.robot:
            print("   robot %.3f,%.3f t   kitty %s"
                  % (level.robot[0], level.robot[1],
                     ("%.3f,%.3f t" % level.kitty) if level.kitty else "(none)"))
        if level.paint_id:
            painted = sum(1 for p in level.paint_id if p)
            styles: dict = {}
            for pid, p in zip(level.paint_id, level.paint or []):
                if pid:
                    name = table.paint_style_of(p)
                    styles[name] = styles.get(name, 0) + 1
            print("   painted %d  styles=%s" % (painted, styles))
        for tile, n in sorted(counts.items()):
            print("   %4d x %3d  %s" % (n, tile, namer(tile)))
    return 0


#: the container a path names, by extension.  ``.bin`` is the raw map; ``.gif``
#: the indexed gif; anything else is read as a ``.kitty``, which is what this
#: tool did before the raw container existed.
RAW_SUFFIX = ".bin"


def _read_any(path: str, table: IdTable, args=None):
    """Read a level from ANY of the three containers, by the path's extension.

    The raw container is the one that cannot state its own shape, so it is the
    one that needs an argument -- and refusing it here, by name, is better than
    handing the bytes to the ``.kitty`` parser and reporting a savegame version
    of 0 for a file that never claimed to be one.
    """
    if path.lower().endswith(".gif"):
        return gifio.read(path)
    if path.lower().endswith(RAW_SUFFIX):
        width = getattr(args, "width", None)
        height = getattr(args, "height", None)
        if not width or not height:
            raise ValueError(
                "%s is a raw map: one byte per cell and no dimensions of its "
                "own, so it cannot be read without --width and --height"
                % os.path.basename(path)
            )
        return rawio.read(path, width, height)
    return kittyio.read(path, table)


def _cmd_emit_json(args) -> int:
    table = _table(args)
    level = _read_any(args.source, table, args)
    if args.name:
        level.name = args.name
    _emit_viewer(level, table, args, args.prefix, args.source)
    return 0


#: options that work on either side of the subcommand name
_SHARED = {"id_table": None, "palette": None, "report": None, "quiet": False,
           "viewer_traits": None, "emit_json": None, "dialect": None,
           "width": None, "height": None, "paint_style": None, "no_paint": False}


def _add_shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dialect", metavar="NAME", default=argparse.SUPPRESS,
                        choices=sorted(DIALECTS),
                        help="which packaged id table interprets the cells: %s "
                             "(default: %s). The SUBCOMMAND picks the container; "
                             "this picks the meaning."
                             % (", ".join(sorted(DIALECTS)), DEFAULT_DIALECT))
    parser.add_argument("--id-table", metavar="PATH", default=argparse.SUPPRESS,
                        help="use another copy of the id table (outranks --dialect "
                             "and $KITTYGIF_ID_TABLE's default; this is the seam "
                             "the mutant gates run through)")
    parser.add_argument("--palette", metavar="PATH", default=argparse.SUPPRESS,
                        help="use another copy of palette.json")
    parser.add_argument("--report", metavar="PATH", default=argparse.SUPPRESS,
                        help="write the machine-readable JSON report here ('-' for stdout)")
    parser.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS,
                        help="do not print the human summary on stderr")
    parser.add_argument("--viewer-traits", metavar="PATH", default=argparse.SUPPRESS,
                        help="use another copy of viewer-traits.json")


def _add_raw_dimensions(parser: argparse.ArgumentParser) -> None:
    """The two dimensions a RAW input needs, optional on a subcommand that may
    also be handed a ``.gif`` or a ``.kitty`` (both of which state their own)."""
    parser.add_argument("--width", type=int, metavar="W", default=argparse.SUPPRESS,
                        help="cells per row, for a raw .bin input only")
    parser.add_argument("--height", type=int, metavar="H", default=argparse.SUPPRESS,
                        help="rows, for a raw .bin input only")


def _add_to_kitty(parser: argparse.ArgumentParser) -> None:
    """The flags every ``* -> .kitty`` subcommand takes, whatever it reads."""
    parser.add_argument("--name", help="level name written into the file "
                                       "(default: the output file's stem, upper-cased)")
    parser.add_argument("--paint-style", help="paint style for the bulk terrain "
                                              "(default: the table's ruled default)")
    parser.add_argument("--no-paint", action="store_true",
                        help="leave the terrain unpainted (every cell draws its "
                             "layout block)")
    parser.add_argument("--emit-json", metavar="PREFIX", default=argparse.SUPPRESS,
                        help="also write the tileMapAnalyzer pair for the CONVERTED "
                             "level: PREFIX%s + PREFIX%s"
                             % (TILEMAP_SUFFIX, CONFIG_SUFFIX))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kittygif", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version="kittygif %s" % __version__)
    _add_shared(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    g2k = sub.add_parser("gif2kitty", help="convert an RWIA level gif to a v1 .kitty")
    _add_shared(g2k)
    g2k.add_argument("source")
    g2k.add_argument("target")
    _add_to_kitty(g2k)
    g2k.set_defaults(func=_cmd_gif2kitty)

    r2k = sub.add_parser(
        "raw2kitty",
        help="convert a raw map (one byte per cell, row-major) to a v1 .kitty")
    _add_shared(r2k)
    r2k.add_argument("source", help="the raw map bytes")
    r2k.add_argument("target")
    # ⚠ REQUIRED, and not a convenience: the file states no dimensions, so these
    # two are a claim ABOUT it that rawio.read checks against the byte count.
    r2k.add_argument("--width", type=int, required=True, metavar="W",
                     help="cells per row (REQUIRED: a raw map carries no header, "
                          "and W x H is checked against the file's byte count)")
    r2k.add_argument("--height", type=int, required=True, metavar="H",
                     help="rows (REQUIRED, same check)")
    _add_to_kitty(r2k)
    r2k.set_defaults(func=_cmd_raw2kitty)

    k2g = sub.add_parser("kitty2gif", help="convert a v1 .kitty to an RWIA level gif")
    _add_shared(k2g)
    k2g.add_argument("source")
    k2g.add_argument("target")
    k2g.add_argument("--emit-json", metavar="PREFIX", default=argparse.SUPPRESS,
                     help="also write the tileMapAnalyzer pair for the CONVERTED "
                          "level: PREFIX%s + PREFIX%s" % (TILEMAP_SUFFIX, CONFIG_SUFFIX))
    k2g.set_defaults(func=_cmd_kitty2gif)

    info = sub.add_parser(
        "info", help="census a .gif, .bin or .kitty level through the table")
    _add_shared(info)
    info.add_argument("files", nargs="+")
    _add_raw_dimensions(info)
    info.set_defaults(func=_cmd_info)

    ej = sub.add_parser("emit-json",
                        help="write the tileMapAnalyzer tilemap + category config "
                             "for a level, in the level's OWN id space")
    _add_shared(ej)
    ej.add_argument("source", help="a .gif, a .bin or a .kitty")
    _add_raw_dimensions(ej)
    ej.add_argument("prefix", help="output prefix; the two files get the panel's own "
                                   "suffixes %s and %s" % (TILEMAP_SUFFIX, CONFIG_SUFFIX))
    ej.add_argument("--name", help="the level name written into the tilemap")
    ej.add_argument("--tilemap", metavar="PATH", default=argparse.SUPPRESS,
                    help="override the tilemap path (⚠ the panel's data files are "
                         "gitignored BY SUFFIX; a path that drops it can dirty a tree)")
    ej.add_argument("--config", metavar="PATH", default=argparse.SUPPRESS,
                    help="override the category config path (same warning)")
    ej.set_defaults(func=_cmd_emit_json)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    for name, default in _SHARED.items():
        if not hasattr(args, name):
            setattr(args, name, default)
    for name in ("tilemap", "config", "name"):
        if not hasattr(args, name):
            setattr(args, name, None)
    try:
        return args.func(args)
    except (ConversionError, TableError, ValueError) as exc:
        print("kittygif: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
