#!/usr/bin/env python3
"""Score the 47-blob transcription against REAL editor output.  LOCAL ONLY.

``paint.blob_index`` is a transcription of ``WorldEditor::GetTileMatch47``, and a
transcription deserves an oracle.  Campaign levels are painted by that very
function, so recomputing each painted cell's blob from the FINAL paint plane and
comparing to the stored value scores the transcription directly.

It also scores two rival readings of "same material", because the discriminator
is only worth anything if the alternatives lose:

  * same paintID   -- what ``WorldEditor::IsTileMatch`` actually compares;
  * any painted    -- "is the neighbour painted at all";
  * same style     -- "is the neighbour the same paint STYLE".

An exact 100% is not expected and would be suspicious: the editor writes a
blob when the cell is painted and refreshes only its eight neighbours
(``PaintFix``), so overpainting a region leaves stale blobs two steps away.  The
stored plane is paint HISTORY; ours is a pure function of the final state, which
is the right thing for a writer.

    python3 scripts/local/check_blob_autotiler.py
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

from kittygif import kittyio                    # noqa: E402
from kittygif.paint import blob_index           # noqa: E402
from kittygif.table import IdTable              # noqa: E402

CAMPAIGN = os.path.expanduser("~/CC/rwkgame-audio/RWK_Source/Games/RWK/Resources/data")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", default=CAMPAIGN)
    ap.add_argument("--floor", type=float, default=90.0,
                    help="minimum agreement for the winning predicate (%%)")
    args = ap.parse_args()

    table = IdTable.load()
    totals = Counter()
    cells = 0
    unused = set(range(47))

    for name in sorted(os.listdir(args.campaign)):
        if not name.endswith(".kitty"):
            continue
        level = kittyio.read(os.path.join(args.campaign, name), table)
        assert level.paint and level.paint_id

        def region(x, y):
            return level.paint_id[level.index(x, y)] if level.in_bounds(x, y) else 0

        def style(x, y):
            if not level.in_bounds(x, y) or not level.paint_id[level.index(x, y)]:
                return -1
            return table.paint_style_of(level.paint[level.index(x, y)])

        here = Counter()
        n = 0
        for x, y, _tile in level.cells():
            i = level.index(x, y)
            pid = level.paint_id[i]
            if not pid:
                continue
            n += 1
            stored = level.paint[i] % 47
            unused.discard(stored)
            mine = blob_index(lambda dx, dy, x=x, y=y, p=pid: region(x + dx, y + dy) == p)
            here["same paintID"] += mine == stored
            here["any painted"] += blob_index(
                lambda dx, dy, x=x, y=y: region(x + dx, y + dy) != 0) == stored
            s = table.paint_style_of(level.paint[i])
            here["same style"] += blob_index(
                lambda dx, dy, x=x, y=y, s=s: style(x + dx, y + dy) == s) == stored
        print("%-22s %6d painted   same-paintID %6.2f%%"
              % (name, n, 100.0 * here["same paintID"] / n if n else 0.0))
        totals.update(here)
        cells += n

    print("\n%d painted cells across the campaign" % cells)
    scores = {k: 100.0 * v / cells for k, v in totals.items()}
    for key in ("same paintID", "any painted", "same style"):
        print("  %-14s %6.3f%%" % (key, scores[key]))
    print("  blob values never stored anywhere: %s" % sorted(unused))

    winner = max(scores, key=lambda k: scores[k])
    ok = winner == "same paintID" and scores[winner] >= args.floor
    print("\n%s: '%s' wins at %.3f%% (floor %.1f%%)"
          % ("PASSED" if ok else "FAILED", winner, scores[winner], args.floor))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
