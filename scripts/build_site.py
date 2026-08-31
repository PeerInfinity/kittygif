#!/usr/bin/env python3
"""Assemble the static demo site.

    python scripts/build_site.py [-o _site]

Puts together three things: the page in ``site/``, a wheel of THIS working tree
built with ``pip wheel`` (so the page always runs the code beside it, never a
release lagging behind), and the sample levels.  The result is a directory of
plain files -- no server side, because the conversion happens in the visitor's
browser.

⛔ Nothing here copies a level file that is not one of the repository's own
samples.  ``tests/test_no_originals.py`` runs over the output directory in CI
for exactly that reason.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(HERE, "site")
SAMPLES = os.path.join(HERE, "samples")

#: what a sample contributes to the page.  The two viewer files carry the suffixes
#: that ARE the emit-json contract, so they are named by rule, not listed.
SAMPLE_FILES = (".gif", ".kitty", ".preview.png", ".report.json",
                "_tilemap.json", "_tiles.json")


def _version() -> str:
    sys.path.insert(0, os.path.join(HERE, "src"))
    from kittygif import __version__
    return __version__


def build_wheel(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "wheel", HERE, "--no-deps",
                    "-w", out_dir, "-q"], check=True)
    wheels = [f for f in os.listdir(out_dir) if f.endswith(".whl")]
    if len(wheels) != 1:
        raise SystemExit("expected exactly one wheel in %s, found %r" % (out_dir, wheels))
    return wheels[0]


def copy_samples(dest: str) -> dict:
    with open(os.path.join(SAMPLES, "samples.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    ticks = {}
    expected = os.path.join(SAMPLES, "oracle-expected.json")
    if os.path.exists(expected):
        with open(expected, encoding="utf-8") as fh:
            for name, row in json.load(fh).get("samples", {}).items():
                ticks[name] = row.get("won_at")
    for sample in index["samples"]:
        name = sample["name"]
        out = os.path.join(dest, name)
        os.makedirs(out, exist_ok=True)
        for suffix in SAMPLE_FILES:
            src = os.path.join(SAMPLES, name, name + suffix)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(out, name + suffix))
        if name in ticks:
            sample["ticks_to_win"] = ticks[name]
    with open(os.path.join(dest, "samples.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=1)
    return index


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "_site"))
    args = ap.parse_args(argv)

    out = os.path.abspath(args.out)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)

    for entry in sorted(os.listdir(SITE)):
        src = os.path.join(SITE, entry)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(out, entry))

    wheel = build_wheel(os.path.join(out, "wheels"))
    index = copy_samples(os.path.join(out, "samples"))

    built = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    with open(os.path.join(out, "build.json"), "w", encoding="utf-8") as fh:
        json.dump({"kittygif": _version(), "wheel": wheel, "built": built}, fh, indent=1)

    print("site  -> %s" % out)
    print("wheel -> wheels/%s" % wheel)
    print("samples: %s" % ", ".join(s["name"] for s in index["samples"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
