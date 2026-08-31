#!/usr/bin/env python3
"""Assert an assembled site is complete, before it is published.

    python scripts/check_site.py _site

A Pages deployment has no test that runs in the browser, so the failure this
guards against is the quiet one: a page that loads, boots Pyodide, and then 404s
on the wheel or a sample -- which looks like a broken converter, not a broken
build.  Everything the page fetches by name is checked here against the page's
own source, so adding a fetch without shipping the file is a red build.
"""

from __future__ import annotations

import json
import os
import re
import sys


def problems(site: str):
    def need(rel, why):
        if not os.path.exists(os.path.join(site, rel)):
            yield "missing %s (%s)" % (rel, why)

    for rel in ("index.html", "app.js", "config.js", "driver.py", "render.js",
                "style.css", "build.json"):
        yield from need(rel, "part of the page")

    build_path = os.path.join(site, "build.json")
    if not os.path.exists(build_path):
        return
    with open(build_path, encoding="utf-8") as fh:
        build = json.load(fh)
    yield from need(os.path.join("wheels", build["wheel"]), "the wheel the page installs")

    index_path = os.path.join(site, "samples", "samples.json")
    yield from need(os.path.join("samples", "samples.json"), "the gallery index")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as fh:
            index = json.load(fh)
        if not index["samples"]:
            yield "the gallery index is empty"
        for sample in index["samples"]:
            name = sample["name"]
            # Exactly what the gallery markup asks for, per sample.
            for suffix in (".preview.png", ".gif", ".kitty", ".report.json"):
                yield from need(os.path.join("samples", name, name + suffix),
                                "the gallery links it")

    # Whatever else the page fetches by literal name must exist too.
    with open(os.path.join(site, "app.js"), encoding="utf-8") as fh:
        app = fh.read()
    for rel in sorted(set(re.findall(r'fetch\("([^"${}]+)"\)', app))):
        yield from need(rel, "app.js fetches it")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    site = argv[0] if argv else "_site"
    found = list(problems(site))
    if found:
        print("site check FAILED over %s:" % site)
        for problem in found:
            print("  " + problem)
        return 1
    print("site check PASSED over %s" % os.path.abspath(site))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
