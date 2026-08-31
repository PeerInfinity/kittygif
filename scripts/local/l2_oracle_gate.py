#!/usr/bin/env python3
"""L2 -- the ORACLE gate.  LOCAL ONLY: it needs game files this repo does not ship.

Converts a level gif to ``.kitty`` and loads the result in a headless build of
the C++ game, driven by its ``--oracle`` mode.  What it proves that L1 cannot:

  * the file we write is one the ENGINE accepts (L1 only proves we agree with
    ourselves);
  * the grid arrives at the right size;
  * the robot spawns where the source pixel said, by the measured formula
    ``world = cell * tile_size_px`` (the engine then drops it to the floor with
    ``Robot::FixPosition``, which moves Y and never X);
  * the world actually STEPS -- a few hundred ticks of "hold right" move the
    robot, so the level is not a degenerate load.

``--mutant`` additionally closes mutant (i): a SYMMETRIC table transposition is
invisible to L1 by construction (see ``tests/test_mutants.py``), and this is the
gate that sees it -- the same gif, converted through a relabelled table, steps
differently in the engine.

Nothing here writes into the game tree: the converted level is loaded by absolute
path (``Common::FixPath`` passes a path with no ``scheme://`` through unchanged).

    python3 scripts/local/l2_oracle_gate.py
    python3 scripts/local/l2_oracle_gate.py --mutant
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

from kittygif import gifio, kittyio                      # noqa: E402
from kittygif.convert import gif_to_kitty                # noqa: E402
from kittygif.table import IdTable                       # noqa: E402

HOME = os.path.expanduser("~")
DEFAULTS = {
    "gif": "/mnt/c/Program Files (x86)/Steam/steamapps/common/"
           "Robot Wants It All/Images/RWK/classic.gif",
    "oracle": HOME + "/CC/rwkgame-audio/RWK_Source/Games/RWK/Resources/RWKAUD",
    "sandbox": HOME + "/.local/share/.raptisoft/RWK_COM/_sandbox",
    "out": HOME + "/CC/Archipelago-CC/NewDocs/plans/kitty-gif-converter/converted",
}
ROBOT_LINE = re.compile(r"world (\d+)x(\d+), robot at \(([-\d.]+),([-\d.]+)\)")


def run_oracle(args, level_path: str, tape: str | None, ticks: int, out_csv: str,
               seed: int | None = None):
    """One oracle invocation.  Returns (stderr, observation rows).

    ``seed`` pins the engine's PRNG (``--seed``); the driver leaves it unseeded
    when it is None, which is what this gate has always done.
    """
    # The engine segfaults on any non-empty settings.txt it previously wrote
    # (P0' S1), so the sandbox settings file goes before every run.
    settings = os.path.join(args.sandbox, "settings.txt")
    if os.path.exists(settings):
        os.remove(settings)
    cmd = [args.oracle, "--oracle", "--level=" + level_path,
           "--ticks=%d" % ticks, "--out=" + out_csv]
    if tape:
        cmd.append("--tape=" + tape)
    if seed is not None:
        cmd.append("--seed=%d" % seed)
    env = dict(os.environ, SDL_VIDEODRIVER="offscreen", SDL_AUDIODRIVER="dummy")
    proc = subprocess.run(cmd, cwd=os.path.dirname(args.oracle), env=env,
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise SystemExit("oracle exited %d\n%s" % (proc.returncode, proc.stderr))
    with open(out_csv, encoding="utf-8") as fh:
        rows = [line for line in fh if line and not line.startswith("#")]
    return proc.stderr, rows


def convert(gif_path: str, out_path: str, table: IdTable, name: str):
    level = gifio.read(gif_path)
    converted, report = gif_to_kitty(level, table, name=name)
    kittyio.write(converted, out_path, table)
    return level, converted, report


def spawn_pixels(level, table):
    out = {}
    for field_name in table.position_field_names:
        gid = table.position_source_gif_id(field_name)
        out[field_name] = next((x, y) for x, y, t in level.cells() if t == gid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gif", default=DEFAULTS["gif"])
    ap.add_argument("--oracle", default=DEFAULTS["oracle"])
    ap.add_argument("--sandbox", default=DEFAULTS["sandbox"])
    ap.add_argument("--out", default=DEFAULTS["out"])
    ap.add_argument("--ticks", type=int, default=600)
    ap.add_argument("--mutant", action="store_true",
                    help="also run a symmetrically transposed table and require the "
                         "oracle to SEE the difference")
    args = ap.parse_args()

    for path in (args.gif, args.oracle):
        if not os.path.exists(path):
            raise SystemExit("missing local input: %s" % path)
    os.makedirs(args.out, exist_ok=True)

    table = IdTable.load()
    tile = table.tile_size_px
    name = os.path.splitext(os.path.basename(args.gif))[0].upper()
    kitty_path = os.path.join(args.out, name + ".kitty")

    level, converted, report = convert(args.gif, kitty_path, table, name)
    pixels = spawn_pixels(level, table)
    print("converted %s -> %s  (%dx%d)" % (args.gif, kitty_path, level.width, level.height))
    print("  spawn pixels: %s" % pixels)

    failures = []

    # -- the FILE says what the pixels said ---------------------------------
    written = kittyio.read(kitty_path, table)
    for field_name, (px, py) in pixels.items():
        attr = "robot" if field_name.startswith("robot") else "kitty"
        got = getattr(written, attr)
        want = (float(px), float(py))
        if got != want:
            failures.append("%s in the file is %s tiles, the pixel says %s" % (field_name, got, want))
        print("  file %-9s %s tiles = %s px" % (field_name, got, (got[0] * tile, got[1] * tile)))

    # -- the ENGINE loads it ------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        tape = os.path.join(tmp, "hold_right.csv")
        with open(tape, "w", encoding="utf-8") as fh:
            fh.write("right,0,%d\n" % args.ticks)
        stderr, rows = run_oracle(args, kitty_path, tape, args.ticks,
                                  os.path.join(tmp, "obs.csv"))
        match = ROBOT_LINE.search(stderr)
        if not match:
            raise SystemExit("could not read the oracle's load line:\n%s" % stderr)
        w, h, rx, ry = int(match.group(1)), int(match.group(2)), \
            float(match.group(3)), float(match.group(4))
        print("  engine: world %dx%d, robot at (%.1f,%.1f)" % (w, h, rx, ry))

        if (w, h) != (level.width, level.height):
            failures.append("engine loaded %dx%d, the gif is %dx%d"
                            % (w, h, level.width, level.height))
        px, py = pixels["robot_xy"]
        if rx != px * tile:
            failures.append("robot X is %.1f, the pixel formula says %d*%d = %d"
                            % (rx, px, tile, px * tile))
        drop = ry - py * tile
        print("  robot Y %.1f vs pixel %d*%d = %d  (FixPosition moved it %+.1f px)"
              % (ry, py, tile, py * tile, drop))
        if abs(drop) > tile:
            failures.append("FixPosition moved the robot %+.1f px, more than one tile -- "
                            "the spawn pixel is probably buried" % drop)

        if len(rows) < args.ticks:
            failures.append("only %d observation rows for %d ticks" % (len(rows), args.ticks))
        xs = [float(r.split(",")[2]) for r in rows[1:]]
        if xs and max(xs) - min(xs) < 1.0:
            failures.append("the robot never moved over %d ticks of 'hold right' -- "
                            "the world loaded but does not step" % args.ticks)
        else:
            print("  stepped %d ticks; robot X spanned %.1f px" % (len(rows) - 1,
                                                                   max(xs) - min(xs)))
        honest_digest = hashlib.md5("".join(rows).encode()).hexdigest()
        print("  observation digest %s" % honest_digest)

        # -- the mutant the round trip cannot see ---------------------------
        if args.mutant:
            raw = copy.deepcopy(table.raw)
            rows_ = [r for r in raw["pairs"]
                     if r["cls"] == "a" and r["directions"] == "both"
                     and isinstance(r["gif"], int) and isinstance(r["kitty"], int)
                     and r["gif"] != 0]
            a, b = rows_[0], rows_[1]
            print("  mutant: transposing gif %d <-> gif %d (%s <-> %s)"
                  % (a["gif"], b["gif"], a["note"][:24], b["note"][:24]))
            a["gif"], b["gif"] = b["gif"], a["gif"]
            mut_table_path = os.path.join(tmp, "mutant-id-table.json")
            with open(mut_table_path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh)
            mutant = IdTable.load(mut_table_path)
            mut_kitty = os.path.join(tmp, name + "_MUTANT.kitty")
            convert(args.gif, mut_kitty, mutant, name)
            _stderr, mut_rows = run_oracle(args, mut_kitty, tape, args.ticks,
                                           os.path.join(tmp, "obs_mutant.csv"))
            mut_digest = hashlib.md5("".join(mut_rows).encode()).hexdigest()
            print("  mutant digest      %s" % mut_digest)
            if mut_digest == honest_digest:
                failures.append("the oracle cannot see a transposed table either -- "
                                "L2 does not discriminate on this level/tape")

    with open(os.path.join(args.out, name + ".report.json"), "w", encoding="utf-8") as fh:
        json.dump(report.to_json(), fh, indent=1)

    if failures:
        print("\nL2 FAILED:")
        for line in failures:
            print("  - " + line)
        return 1
    print("\nL2 PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
