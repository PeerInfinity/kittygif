"""``kittygif`` -- the command line.

    kittygif gif2kitty LEVEL.gif OUT.kitty [--name NAME] [--paint-style panels]
    kittygif kitty2gif LEVEL.kitty OUT.gif
    kittygif info FILE...
    kittygif emit-json LEVEL.{gif,kitty} OUT_PREFIX

Every subcommand writes its report: the human summary on stderr, and the
machine-readable JSON to ``--report PATH`` (or to stdout with ``--report -``).
``--id-table PATH`` converts by another copy of the table, which is how the
mutant gates run without ever editing the shipped data.

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

from . import __version__, gifio, kittyio, viewer
from .convert import ConversionError, gif_to_kitty, kitty_to_gif
from .report import Report
from .table import GIF, IdTable, Palette, TableError
from .viewer import ViewerTraits


def _table(args) -> IdTable:
    table = IdTable.load(args.id_table)
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


def _cmd_gif2kitty(args) -> int:
    table = _table(args)
    level = gifio.read(args.source)
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
        if path.lower().endswith(".gif"):
            level = gifio.read(path)
        else:
            level = kittyio.read(path, table)
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


def _read_any(path: str, table: IdTable):
    """Read a level from either side, the way ``info`` does."""
    if path.lower().endswith(".gif"):
        return gifio.read(path)
    return kittyio.read(path, table)


def _cmd_emit_json(args) -> int:
    table = _table(args)
    level = _read_any(args.source, table)
    if args.name:
        level.name = args.name
    _emit_viewer(level, table, args, args.prefix, args.source)
    return 0


#: options that work on either side of the subcommand name
_SHARED = {"id_table": None, "palette": None, "report": None, "quiet": False,
           "viewer_traits": None, "emit_json": None}


def _add_shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id-table", metavar="PATH", default=argparse.SUPPRESS,
                        help="use another copy of id-table.json (default: the packaged one, "
                             "or $KITTYGIF_ID_TABLE)")
    parser.add_argument("--palette", metavar="PATH", default=argparse.SUPPRESS,
                        help="use another copy of palette.json")
    parser.add_argument("--report", metavar="PATH", default=argparse.SUPPRESS,
                        help="write the machine-readable JSON report here ('-' for stdout)")
    parser.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS,
                        help="do not print the human summary on stderr")
    parser.add_argument("--viewer-traits", metavar="PATH", default=argparse.SUPPRESS,
                        help="use another copy of viewer-traits.json")


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
    g2k.add_argument("--name", help="level name written into the file "
                                    "(default: the output file's stem, upper-cased)")
    g2k.add_argument("--paint-style", help="paint style for the bulk terrain "
                                           "(default: the table's ruled default)")
    g2k.add_argument("--no-paint", action="store_true",
                     help="leave the terrain unpainted (every cell draws its layout block)")
    g2k.add_argument("--emit-json", metavar="PREFIX", default=argparse.SUPPRESS,
                     help="also write the tileMapAnalyzer pair for the CONVERTED "
                          "level: PREFIX%s + PREFIX%s" % (TILEMAP_SUFFIX, CONFIG_SUFFIX))
    g2k.set_defaults(func=_cmd_gif2kitty)

    k2g = sub.add_parser("kitty2gif", help="convert a v1 .kitty to an RWIA level gif")
    _add_shared(k2g)
    k2g.add_argument("source")
    k2g.add_argument("target")
    k2g.add_argument("--emit-json", metavar="PREFIX", default=argparse.SUPPRESS,
                     help="also write the tileMapAnalyzer pair for the CONVERTED "
                          "level: PREFIX%s + PREFIX%s" % (TILEMAP_SUFFIX, CONFIG_SUFFIX))
    k2g.set_defaults(func=_cmd_kitty2gif)

    info = sub.add_parser("info", help="census a .gif or .kitty level through the table")
    _add_shared(info)
    info.add_argument("files", nargs="+")
    info.set_defaults(func=_cmd_info)

    ej = sub.add_parser("emit-json",
                        help="write the tileMapAnalyzer tilemap + category config "
                             "for a level, in the level's OWN id space")
    _add_shared(ej)
    ej.add_argument("source", help="a .gif or a .kitty")
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
