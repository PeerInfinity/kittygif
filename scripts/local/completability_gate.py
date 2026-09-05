#!/usr/bin/env python3
"""Every sample is COMPLETABLE -- proven in the engine, not asserted.

LOCAL ONLY: it needs a headless build of the C++ game, which this repository
does not ship and CI cannot run.  What ships instead is everything needed to
re-run it: the levels, the input tapes that solve them, and the expected
observation digests in ``samples/oracle-expected.json``.

For each sample it loads ``<name>.kitty`` in the engine's ``--oracle`` mode,
replays ``<name>.tape.csv``, and requires:

  * the engine's own **win flag** (``World::mWin``, the last column of the
    observation stream) to go true -- ``World::Win()`` is reached from exactly
    one place in the game, ``Kitty::Update`` when the robot is within 35 px, so
    the flag IS "the robot reached the kitty";
  * the robot never to die on the way (the ``died`` column stays 0), because a
    walkthrough that dies proves the level is survivable, not that the intended
    solution works;
  * the observation digest to match the recorded one, which turns the tapes into
    a regression gate on the whole chain -- table, writer, container, engine.

⚠ **The digest is not perfectly reproducible, and that was measured, not
assumed.**  Over eight consecutive runs on one box (2026-09-04, load 6.6-10.6,
``--seed=1`` as always), six agreed with every recorded value and two came back
with ONE sample's win one or two ticks early -- ``corridor-rwk`` at 2420 instead
of 2422 in one run, ``corridor`` at 1033 instead of 1034 in another, each with
the digest that follows from it.  It was a different sample each time, the two
longest tapes, and no run ever reported a DEATH or a failure to win.  So the
recorded numbers are the modal values and the win/no-death verdict is solid,
while a lone off-by-one-tick digest on a long tape is this box, not a
regression: re-run before believing one.  Reproducing it exactly is an engine
timing question and lives in the engine's own tree, not here.

    python3 scripts/local/completability_gate.py
    python3 scripts/local/completability_gate.py --write     # re-record digests
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, HERE)

from l2_oracle_gate import DEFAULTS, ROBOT_LINE, run_oracle    # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")

#: the observation stream's columns, as the driver's own header names them
WIN, DIED, TICK, X = -1, -2, 0, 2


def load_manifest(samples: str) -> list:
    with open(os.path.join(samples, "samples.json"), encoding="utf-8") as fh:
        return json.load(fh)["samples"]


def replay(args, entry: dict, tmp: str) -> dict:
    name = entry["name"]
    level = os.path.join(args.samples, name, name + ".kitty")
    tape = os.path.join(args.samples, name, name + ".tape.csv")
    out = os.path.join(tmp, name + ".obs.csv")
    stderr, rows = run_oracle(args, level, tape, entry["ticks"], out, seed=args.seed)

    match = ROBOT_LINE.search(stderr)
    if not match:
        raise SystemExit("%s: could not read the oracle's load line:\n%s" % (name, stderr))
    grid = [int(match.group(1)), int(match.group(2))]

    data = [r.rstrip("\n").split(",") for r in rows if not r.startswith(("#", "tick"))]
    won_at = next((int(r[TICK]) for r in data if r[WIN] == "1"), None)
    died_at = next((int(r[TICK]) for r in data if r[DIED] == "1"), None)
    return {
        "name": name,
        "grid": grid,
        "ticks_run": len(data),
        "won_at": won_at,
        "died_at": died_at,
        "final_x": float(data[-1][X]) if data else None,
        # the stream up to and including the winning tick: the ticks AFTER a win
        # belong to the win transition tearing the world down, not to the level
        "digest": hashlib.md5(
            "".join(rows[: (won_at + 3) if won_at is not None else len(rows)]).encode()
        ).hexdigest(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--oracle", default=DEFAULTS["oracle"])
    ap.add_argument("--sandbox", default=DEFAULTS["sandbox"])
    ap.add_argument("--write", action="store_true",
                    help="record the results as the expected ones")
    ap.add_argument("--samples", default=SAMPLES,
                    help="the sample tree to replay (a MUTANT copy proves the gate discriminates)")
    ap.add_argument("--seed", type=int, default=1,
                    help="the engine PRNG seed the recorded digests were taken at")
    ap.add_argument("--only", action="append")
    args = ap.parse_args()

    if not os.path.exists(args.oracle):
        raise SystemExit("missing the local engine build: %s" % args.oracle)

    expected_path = os.path.join(args.samples, "oracle-expected.json")
    expected = {}
    if os.path.exists(expected_path):
        with open(expected_path, encoding="utf-8") as fh:
            expected = json.load(fh).get("samples", {})

    entries = [e for e in load_manifest(args.samples) if not args.only or e["name"] in args.only]
    failures, results = [], {}

    with tempfile.TemporaryDirectory() as tmp:
        for entry in entries:
            got = replay(args, entry, tmp)
            name = got["name"]
            results[name] = got
            print("%-13s %3dx%-3d  won_at=%-6s died_at=%-6s final_x=%-9s %s"
                  % (name, got["grid"][0], got["grid"][1], got["won_at"],
                     got["died_at"], got["final_x"], got["digest"]))

            if got["won_at"] is None:
                failures.append("%s: the win flag never went true in %d ticks -- the "
                                "tape does not solve the level" % (name, entry["ticks"]))
            if got["died_at"] is not None:
                failures.append("%s: the robot died at tick %d; the intended solution "
                                "must not need a death" % (name, got["died_at"]))
            if got["grid"] != entry["grid"]:
                failures.append("%s: the engine loaded %s, the manifest says %s"
                                % (name, got["grid"], entry["grid"]))

            want = expected.get(name)
            if args.write:
                continue
            if want is None:
                failures.append("%s has no recorded expectation; run with --write" % name)
            elif want.get("digest") != got["digest"]:
                failures.append(
                    "%s: observation digest %s, recorded %s -- something in the chain "
                    "(table, writer, container, engine) moved"
                    % (name, got["digest"], want.get("digest")))
            elif want.get("won_at") != got["won_at"]:
                failures.append("%s: won at tick %s, recorded %s"
                                % (name, got["won_at"], want.get("won_at")))

    if args.write:
        with open(expected_path, "w", encoding="utf-8") as fh:
            json.dump({
                "_doc": "Expected oracle results for samples/*, recorded by "
                        "scripts/local/completability_gate.py --write.  The engine "
                        "is not in this repository; these are the numbers a local "
                        "run must reproduce.",
                "_oracle": os.path.basename(args.oracle),
                "_seed": args.seed,
                "samples": results,
            }, fh, indent=1)
            fh.write("\n")
        print("\nrecorded %d sample(s) in %s" % (len(results), expected_path))
        return 0

    if failures:
        print("\nCOMPLETABILITY FAILED:")
        for line in failures:
            print("  - " + line)
        return 1
    print("\nCOMPLETABILITY PASSED -- every sample's tape reaches the kitty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
