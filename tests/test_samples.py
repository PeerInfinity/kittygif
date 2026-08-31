"""The sample levels are part of the contract, so they are part of the suite.

Three things are pinned here:

* **the samples still regenerate** -- ``samples/generate.py`` run again produces
  the committed files.  That is a self-consistency check and it is stated as one:
  it proves the generator and the shipped files agree, never that either is
  right.  What proves the levels are *playable* is the oracle
  (``scripts/local/completability_gate.py``), which needs the game and so cannot
  run here; its result travels as ``samples/oracle-expected.json``, and this file
  checks that every sample HAS one.
* **L1 on real sample files** -- the round trip through the two writers, over
  files on disk rather than in-memory fixtures.
* **the showcases still show everything** -- a sample that quietly stopped
  carrying an id would otherwise be invisible.
"""

from __future__ import annotations

import importlib.util
import json
import os

import pytest

from fixtures import mappable_gif_ids
from kittygif import gifio, kittyio
from kittygif.convert import gif_to_kitty, kitty_to_gif
from kittygif.table import GIF, KITTY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "kittygif_samples_generate", os.path.join(SAMPLES, "generate.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generate = _load_generator()
NAMES = sorted(generate.SAMPLES)


@pytest.fixture(scope="module")
def manifest():
    with open(os.path.join(SAMPLES, "samples.json"), encoding="utf-8") as fh:
        return {e["name"]: e for e in json.load(fh)["samples"]}


def _paths(name):
    base = os.path.join(SAMPLES, name, name)
    return base + ".gif", base + ".kitty"


# --------------------------------------------------------------- they are there
def test_every_sample_the_generator_knows_is_on_disk(manifest):
    assert sorted(manifest) == NAMES
    for name in NAMES:
        for suffix in (".gif", ".kitty", ".tape.csv", ".report.json",
                       "_tilemap.json", "_tiles.json", ".preview.png"):
            path = os.path.join(SAMPLES, name, name + suffix)
            assert os.path.exists(path), path


def test_every_sample_carries_a_completability_proof(manifest):
    """The oracle cannot run here, so its VERDICT has to travel with the samples."""
    with open(os.path.join(SAMPLES, "oracle-expected.json"), encoding="utf-8") as fh:
        expected = json.load(fh)["samples"]
    assert sorted(expected) == NAMES
    for name, got in expected.items():
        assert got["won_at"] is not None, "%s has no recorded win tick" % name
        assert got["died_at"] is None, "%s's recorded run dies on the way" % name
        assert got["grid"] == manifest[name]["grid"]


# ------------------------------------------------------------- they regenerate
@pytest.mark.parametrize("name", NAMES)
def test_the_generator_reproduces_the_committed_sample(name, tmp_path, table):
    from kittygif.table import Palette
    from kittygif.viewer import ViewerTraits

    out = str(tmp_path / name)
    generate.write_sample(name, out, table, Palette.load(), ViewerTraits.load())

    for suffix in (".kitty", ".tape.csv", ".report.json", "_tilemap.json", "_tiles.json"):
        fresh = open(os.path.join(out, name + suffix), "rb").read()
        shipped = open(os.path.join(SAMPLES, name, name + suffix), "rb").read()
        assert fresh == shipped, "%s%s is not what the generator writes today" % (name, suffix)

    # The gif and the preview go through Pillow's own encoders, so their BYTES
    # belong to a Pillow version and not to us; what belongs to us is every pixel.
    a = gifio.read(os.path.join(out, name + ".gif"))
    b = gifio.read(os.path.join(SAMPLES, name, name + ".gif"))
    assert (a.width, a.height, a.tiles) == (b.width, b.height, b.tiles)

    from PIL import Image
    with Image.open(os.path.join(out, name + ".preview.png")) as fresh, \
            Image.open(os.path.join(SAMPLES, name, name + ".preview.png")) as shipped:
        assert fresh.size == shipped.size
        assert list(fresh.convert("RGB").getdata()) == list(shipped.convert("RGB").getdata())


# -------------------------------------------------------------------------- L1
@pytest.mark.parametrize("name", NAMES)
def test_round_trip_through_the_committed_files(name, table):
    """gif -> kitty -> gif, on files, masked to the mappable subset."""
    gif_path, kitty_path = _paths(name)
    source = gifio.read(gif_path)
    converted, _report = gif_to_kitty(source, table, name=source.name)
    back, _report2 = kitty_to_gif(converted, table)

    mappable = mappable_gif_ids(table) | {
        table.position_source_gif_id(f) for f in table.position_field_names}
    checked = 0
    for x, y, gid in source.cells():
        if gid in mappable:
            assert back.at(x, y) == gid, "(%d,%d) came back as %d, not %d" % (
                x, y, back.at(x, y), gid)
            checked += 1
    assert checked > 0, "%s exercises no mappable id at all" % name


@pytest.mark.parametrize("name", NAMES)
def test_the_two_committed_formats_are_the_same_level(name, table, manifest):
    """The shipped ``.gif`` and ``.kitty`` are one level in two files."""
    gif_path, kitty_path = _paths(name)
    from_gif = gifio.read(gif_path)
    from_kitty = kittyio.read(kitty_path, table)
    assert (from_gif.width, from_gif.height) == (from_kitty.width, from_kitty.height)
    assert [from_gif.width, from_gif.height] == manifest[name]["grid"]

    # A gif carries no level NAME -- the .kitty does, and the converter is told
    # one.  The samples name a level after its directory.
    assert from_kitty.name == name.upper()

    if manifest[name]["authored_in"] == GIF:
        # the .kitty is what converting the .gif produces, byte for byte
        converted, _r = gif_to_kitty(from_gif, table, name=from_kitty.name)
        assert kittyio.to_bytes(converted, table) == open(kitty_path, "rb").read()
    else:
        # the .gif is what converting the .kitty produces, pixel for pixel
        converted, _r = kitty_to_gif(from_kitty, table)
        assert converted.tiles == from_gif.tiles

    # the spawns agree across the two files however each one carries them
    for field in table.position_field_names:
        attr = "robot" if field.startswith("robot") else "kitty"
        gid = table.position_source_gif_id(field)
        cell = next(((x, y) for x, y, t in from_gif.cells() if t == gid), None)
        assert cell is not None, "%s has no %s pixel" % (name, field)
        assert getattr(from_kitty, attr) == (float(cell[0]), float(cell[1]))


# ------------------------------------------------------------- they still show
def test_the_showcases_show_every_authorable_id(table):
    """Both showcases carry their whole side of the vocabulary."""
    from build import Vocab  # the generator's own helper, on sys.path via generate

    for name, space in (("corridor", GIF), ("corridor-rwk", KITTY)):
        vocab = Vocab(table, space)
        gif_path, kitty_path = _paths(name)
        level = (gifio.read(gif_path) if space == GIF
                 else kittyio.read(kitty_path, table))
        assert set(level.tiles) == set(vocab.authorable), (
            "%s no longer shows every authorable %s id" % (name, space))
        assert len(set(level.tiles)) > 30, "the showcase shrank to %d ids" % len(set(level.tiles))


def test_the_authorable_set_agrees_with_the_measured_census(table):
    from build import Vocab

    assert "agrees exactly" in Vocab(table, GIF).check_against_census()
    Vocab(table, KITTY).check_against_census()


# ------------------------------------------------------------------ the tapes
@pytest.mark.parametrize("name", NAMES)
def test_the_tape_is_the_engine_format(name, manifest):
    """One span per line, ``button,from,to``, inside the run's tick budget."""
    buttons, spans = set(), 0
    with open(os.path.join(SAMPLES, name, name + ".tape.csv"), encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            button, lo, hi = line.strip().split(",")
            assert int(lo) <= int(hi) < manifest[name]["ticks"]
            buttons.add(button)
            spans += 1
    assert spans, "%s ships an empty tape" % name
    assert "right" in buttons, "%s never walks right" % name


# ----------------------------------------------------------- the viewer's pair
@pytest.mark.parametrize("name", NAMES)
def test_the_viewer_pair_loads(name):
    """The four checks ``tileMapDataManager`` makes, spelled the way it spells them."""
    base = os.path.join(SAMPLES, name, name)
    with open(base + "_tilemap.json", encoding="utf-8") as fh:
        tilemap = json.load(fh)
    with open(base + "_tiles.json", encoding="utf-8") as fh:
        config = json.load(fh)
    assert isinstance(tilemap["tiles"], list)
    assert isinstance(tilemap["map_width"], int) and isinstance(tilemap["map_height"], int)
    assert isinstance(config["categories"], dict) and isinstance(config["tile_ids"], dict)
    assert config.get("default_category") is not None
    assert len(tilemap["tiles"]) == tilemap["map_height"]
    assert all(len(row) == tilemap["map_width"] for row in tilemap["tiles"])


@pytest.mark.parametrize("name", NAMES)
def test_the_committed_config_carries_no_machine_path(name):
    """A committed sample must not record where it happened to be generated."""
    with open(os.path.join(SAMPLES, name, name + "_tiles.json"), encoding="utf-8") as fh:
        config = json.load(fh)
    for key in ("_id_table", "_palette", "_viewer_traits"):
        assert config[key] == os.path.basename(config[key])
        assert os.sep not in config[key]
    with open(os.path.join(SAMPLES, name, name + ".report.json"), encoding="utf-8") as fh:
        assert os.sep not in json.load(fh)["id_table"]
