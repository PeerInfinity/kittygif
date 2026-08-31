"""The demo site's completeness check.

The site is published by a workflow, and its failure mode is quiet: a page that
loads, boots Python, and then 404s on the wheel.  ``scripts/check_site.py`` is
what makes that loud, so what these tests establish is that it can actually go
red -- an assembled-site check that passes on a broken tree is worse than none.

Building the real site takes ten seconds and a ``pip wheel`` run, so it happens
in the workflow (which then runs the same checker over its output).  Here the
trees are hand-built, one per way of being broken.
"""

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "scripts"))
import check_site  # noqa: E402

SAMPLE_FILES = (".preview.png", ".gif", ".kitty", ".report.json")


def make_site(root, wheel="kittygif-0.0.0-py3-none-any.whl", samples=("demo",),
              app_fetches=("build.json", "driver.py", "samples/samples.json")):
    os.makedirs(root, exist_ok=True)
    for name in ("index.html", "config.js", "render.js", "style.css"):
        open(os.path.join(root, name), "w").close()
    open(os.path.join(root, "driver.py"), "w").close()
    with open(os.path.join(root, "app.js"), "w", encoding="utf-8") as fh:
        fh.write("\n".join('await fetch("%s");' % rel for rel in app_fetches))
    with open(os.path.join(root, "build.json"), "w", encoding="utf-8") as fh:
        json.dump({"kittygif": "0.0.0", "wheel": wheel, "built": "today"}, fh)
    os.makedirs(os.path.join(root, "wheels"), exist_ok=True)
    open(os.path.join(root, "wheels", wheel), "w").close()
    os.makedirs(os.path.join(root, "samples"), exist_ok=True)
    with open(os.path.join(root, "samples", "samples.json"), "w", encoding="utf-8") as fh:
        json.dump({"samples": [{"name": n} for n in samples]}, fh)
    for name in samples:
        d = os.path.join(root, "samples", name)
        os.makedirs(d, exist_ok=True)
        for suffix in SAMPLE_FILES:
            open(os.path.join(d, name + suffix), "w").close()
    return root


def test_a_complete_site_passes(tmp_path):
    assert list(check_site.problems(make_site(str(tmp_path / "site")))) == []


def test_a_missing_wheel_is_caught(tmp_path):
    site = make_site(str(tmp_path / "site"))
    shutil.rmtree(os.path.join(site, "wheels"))
    found = list(check_site.problems(site))
    assert any("wheel" in p for p in found), found


def test_a_missing_sample_asset_is_caught(tmp_path):
    site = make_site(str(tmp_path / "site"))
    os.remove(os.path.join(site, "samples", "demo", "demo.preview.png"))
    assert any("demo.preview.png" in p for p in check_site.problems(site))


def test_a_missing_page_file_is_caught(tmp_path):
    site = make_site(str(tmp_path / "site"))
    os.remove(os.path.join(site, "render.js"))
    assert any("render.js" in p for p in check_site.problems(site))


def test_an_empty_gallery_is_caught(tmp_path):
    site = make_site(str(tmp_path / "site"), samples=())
    assert any("empty" in p for p in check_site.problems(site))


def test_a_fetch_the_build_did_not_ship_is_caught(tmp_path):
    """The check reads app.js, so a new fetch without a new file goes red."""
    site = make_site(str(tmp_path / "site"),
                     app_fetches=("build.json", "driver.py", "samples/samples.json",
                                  "something-nobody-built.json"))
    assert any("something-nobody-built.json" in p for p in check_site.problems(site))


def test_the_real_pages_workflow_runs_both_guards():
    """The site dir is a new way out for a level file; the guard must see it."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "pages.yml"),
              encoding="utf-8") as fh:
        workflow = fh.read()
    assert "tests/test_no_originals.py _site" in workflow
    assert "scripts/check_site.py _site" in workflow


def test_the_page_pins_an_exact_pyodide_version():
    """Which Pillow the page gets is a property of the Pyodide version."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "site", "config.js"), encoding="utf-8") as fh:
        config = fh.read()
    import re
    match = re.search(r'pyodideVersion:\s*"([^"]+)"', config)
    assert match, "the page must pin a Pyodide version"
    assert re.fullmatch(r"\d+\.\d+\.\d+", match.group(1)), match.group(1)
