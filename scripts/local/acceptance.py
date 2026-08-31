#!/usr/bin/env python3
"""Acceptance conversions on REAL data.  LOCAL ONLY -- this repo ships none of it.

  * every RWK level gif -> ``.kitty``, each one loaded in the headless oracle;
  * a campaign ``.kitty`` -> ``.gif``, exercising the class-(b)/(c) report;
  * the L1 masked round trip on each real gif: every cell whose id is in the
    MAPPABLE subset must come back byte-identical.  (Cells outside that subset
    are degraded on purpose -- the report says which, and how many.)

Outputs land in ``--out``, which is deliberately outside this repository:
converted originals are not ours to redistribute.

    python3 scripts/local/acceptance.py
    python3 scripts/local/acceptance.py --no-oracle      # skip the engine runs
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kittygif import gifio, kittyio                              # noqa: E402
from kittygif.convert import gif_to_kitty, kitty_to_gif          # noqa: E402
from kittygif.table import IdTable, Palette                      # noqa: E402
from l2_oracle_gate import DEFAULTS, ROBOT_LINE, run_oracle      # noqa: E402

HOME = os.path.expanduser("~")
GIF_DIR = os.path.dirname(DEFAULTS["gif"])
CAMPAIGN = HOME + "/CC/rwkgame-audio/RWK_Source/Games/RWK/Resources/data"


def mappable_gif_ids(table: IdTable):
    out = set()
    for gid, rule in table.forward.items():
        if rule.position_field or rule.target_ids is None:
            continue
        backs = {table.reverse[k].target_ids[0] for k in rule.target_ids
                 if k in table.reverse and table.reverse[k].target_ids}
        if backs == {gid}:
            out.add(gid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gif-dir", default=GIF_DIR)
    ap.add_argument("--campaign", default=CAMPAIGN)
    ap.add_argument("--out", default=DEFAULTS["out"])
    ap.add_argument("--oracle", default=DEFAULTS["oracle"])
    ap.add_argument("--sandbox", default=DEFAULTS["sandbox"])
    ap.add_argument("--ticks", type=int, default=300)
    ap.add_argument("--no-oracle", action="store_true")
    ap.add_argument("--kitty-source", default="FLASHLEVEL.kitty",
                    help="the campaign level converted in the kitty->gif direction")
    args = ap.parse_args()

    table = IdTable.load()
    palette = Palette.load()
    mappable = mappable_gif_ids(table)
    os.makedirs(args.out, exist_ok=True)
    failures = []
    summary = []

    # ------------------------------------------------------- gif -> .kitty
    for gif_path in sorted(glob.glob(os.path.join(args.gif_dir, "*.gif"))):
        name = os.path.splitext(os.path.basename(gif_path))[0].upper()
        out_kitty = os.path.join(args.out, name + ".kitty")
        source = gifio.read(gif_path)
        converted, report = gif_to_kitty(source, table, name=name)
        report.source, report.target = gif_path, out_kitty
        kittyio.write(converted, out_kitty, table)
        with open(os.path.join(args.out, name + ".gif2kitty.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(report.to_json(), fh, indent=1)

        # L1, masked to the mappable subset
        back, _rev = kitty_to_gif(kittyio.read(out_kitty, table), table)
        diffs = [(x, y, tile, back.at(x, y))
                 for x, y, tile in source.cells()
                 if tile in mappable and back.at(x, y) != tile]
        counts = report.counts()
        row = ("%-10s %3dx%-3d  mappable %5d  degraded %5d  substituted %4d  "
               "L1-masked %s" % (name, source.width, source.height,
                                 counts["a"], counts["b"], counts["c"],
                                 "GREEN" if not diffs else "RED (%d cells)" % len(diffs)))
        summary.append(row)
        print(row)
        if diffs:
            failures.append("%s: %d mappable cells did not round-trip, e.g. %s"
                            % (name, len(diffs), diffs[:4]))
        if report.solvability_at_risk:
            for entry in report.by_class("c"):
                print("    (c) %4d x %s -> %s" % (entry.count, entry.source_name,
                                                  entry.target_name))

        if not args.no_oracle:
            with tempfile.TemporaryDirectory() as tmp:
                stderr, rows = run_oracle(args, out_kitty, None, args.ticks,
                                          os.path.join(tmp, "obs.csv"))
            match = ROBOT_LINE.search(stderr)
            if not match:
                failures.append("%s: the oracle did not report a world" % name)
                continue
            w, h = int(match.group(1)), int(match.group(2))
            rx = float(match.group(3))
            px = next(x for x, y, t in source.cells()
                      if t == table.position_source_gif_id("robot_xy"))
            ok = (w, h) == (source.width, source.height) and rx == px * table.tile_size_px
            print("    oracle: %dx%d robot x=%.1f (pixel %d*%d)  %s"
                  % (w, h, rx, px, table.tile_size_px, "OK" if ok else "MISMATCH"))
            if not ok:
                failures.append("%s: oracle load mismatch" % name)
            if len(rows) < args.ticks:
                failures.append("%s: only %d observation rows" % (name, len(rows)))

    # ------------------------------------------------------- .kitty -> gif
    src_kitty = os.path.join(args.campaign, args.kitty_source)
    if os.path.exists(src_kitty):
        name = os.path.splitext(args.kitty_source)[0]
        out_gif = os.path.join(args.out, name + ".gif")
        level = kittyio.read(src_kitty, table)
        converted, report = kitty_to_gif(level, table)
        report.source, report.target = src_kitty, out_gif
        gifio.write(converted, out_gif, palette)
        with open(os.path.join(args.out, name + ".kitty2gif.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(report.to_json(), fh, indent=1)
        counts = report.counts()
        print("\n%-10s %3dx%-3d  mappable %5d  degraded %5d  substituted %4d"
              % (name, level.width, level.height, counts["a"], counts["b"], counts["c"]))
        print(report.to_text())
        if not report.by_class("b") and not report.by_class("c"):
            failures.append("%s reported nothing -- a campaign level carries C++-only "
                            "kinds by construction, so this direction cannot be clean"
                            % name)
        if gifio.read(out_gif).tiles != converted.tiles:
            failures.append("%s: the written gif does not read back identical" % name)
    else:
        print("\n(skipping the kitty->gif acceptance: %s not present)" % src_kitty)

    print()
    if failures:
        print("ACCEPTANCE FAILED:")
        for line in failures:
            print("  - " + line)
        return 1
    print("ACCEPTANCE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
