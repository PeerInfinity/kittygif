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

⚠ Every arm here reads a sample through ``generate.table_for(name)``, never
through "the table".  A sample is authored in ONE dialect's id space, and the
two dialects share their id NUMBERS -- so a sample read through the wrong table
does not raise, it quietly means something else.  ``corridor`` and
``flash-corridor`` are the same recipe over two tables, which is exactly the
pair that would hide such a mistake.
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


def _table(name):
    """The table a sample MUST be read with -- the generator's own answer."""
    return generate.table_for(name)


@pytest.fixture(scope="module")
def manifest():
    with open(os.path.join(SAMPLES, "samples.json"), encoding="utf-8") as fh:
        return {e["name"]: e for e in json.load(fh)["samples"]}


def _pixels(path):
    """Size plus every pixel of a PNG.

    Pillow 12 deprecates ``Image.getdata()`` in favour of
    ``get_flattened_data()``; the package supports both, so take whichever this
    Pillow has -- the same choice ``gifio`` makes.
    """
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        flatten = getattr(rgb, "get_flattened_data", None) or rgb.getdata
        return image.size, list(flatten())


def _paths(name):
    base = os.path.join(SAMPLES, name, name)
    return base + ".gif", base + ".kitty"


def _suffixes(name):
    """Every file a sample ships: the shared set plus its own containers."""
    return generate.containers_of(name) + (
        ".kitty", ".tape.csv", ".report.json",
        "_tilemap.json", "_tiles.json", ".preview.png")


# --------------------------------------------------------------- they are there
def test_every_sample_the_generator_knows_is_on_disk(manifest):
    assert sorted(manifest) == NAMES
    for name in NAMES:
        for suffix in _suffixes(name):
            path = os.path.join(SAMPLES, name, name + suffix)
            assert os.path.exists(path), path


def test_every_sample_records_the_dialect_it_was_authored_in(manifest):
    """⛔ Not inferable from the files: the two id spaces share their NUMBERS."""
    from kittygif.table import DIALECTS

    for name in NAMES:
        assert manifest[name]["dialect"] in DIALECTS
        assert manifest[name]["dialect"] == generate.dialect_of(name)


def test_the_raw_container_is_shipped_for_the_dialect_whose_game_READS_one(manifest):
    """The control that keeps ``_suffixes`` from being decoration.

    A ``.bin`` is not a file every sample happens to have: it is the container
    the Flash build actually reads.  If no sample ships one, ``raw2kitty`` has
    no committed subject at all.
    """
    with_raw = [n for n in NAMES if ".bin" in generate.containers_of(n)]
    assert with_raw, "no sample exercises the raw container"
    for name in with_raw:
        assert manifest[name]["dialect"] == "flash"


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
def test_the_generator_reproduces_the_committed_sample(name, tmp_path):
    from kittygif.table import Palette
    from kittygif.viewer import ViewerTraits

    out = str(tmp_path / name)
    generate.write_sample(name, out, _table(name), Palette.load(), ViewerTraits.load())

    byte_exact = [".kitty", ".tape.csv", ".report.json", "_tilemap.json", "_tiles.json"]
    byte_exact += [c for c in generate.containers_of(name) if c != ".gif"]
    for suffix in byte_exact:
        fresh = open(os.path.join(out, name + suffix), "rb").read()
        shipped = open(os.path.join(SAMPLES, name, name + suffix), "rb").read()
        assert fresh == shipped, "%s%s is not what the generator writes today" % (name, suffix)

    # The gif and the preview go through Pillow's own encoders, so their BYTES
    # belong to a Pillow version and not to us; what belongs to us is every pixel.
    a = gifio.read(os.path.join(out, name + ".gif"))
    b = gifio.read(os.path.join(SAMPLES, name, name + ".gif"))
    assert (a.width, a.height, a.tiles) == (b.width, b.height, b.tiles)

    assert _pixels(os.path.join(out, name + ".preview.png")) == \
        _pixels(os.path.join(SAMPLES, name, name + ".preview.png"))


# -------------------------------------------------------------------------- L1
@pytest.mark.parametrize("name", NAMES)
def test_round_trip_through_the_committed_files(name):
    """gif -> kitty -> gif, on files, masked to the mappable subset."""
    table = _table(name)
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
def test_the_two_committed_formats_are_the_same_level(name, manifest):
    """The shipped ``.gif`` and ``.kitty`` are one level in two files."""
    table = _table(name)
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
def test_the_showcases_show_every_authorable_id():
    """Each showcase carries its whole side of ITS OWN dialect's vocabulary."""
    from build import Vocab  # the generator's own helper, on sys.path via generate

    for name, space in (("corridor", GIF), ("corridor-rwk", KITTY),
                        ("flash-corridor", GIF)):
        table = _table(name)
        vocab = Vocab(table, space)
        gif_path, kitty_path = _paths(name)
        level = (gifio.read(gif_path) if space == GIF
                 else kittyio.read(kitty_path, table))
        assert set(level.tiles) == set(vocab.authorable), (
            "%s no longer shows every authorable %s id" % (name, space))
        assert len(set(level.tiles)) > 30, "the showcase shrank to %d ids" % len(set(level.tiles))


def test_the_two_corridors_are_the_SAME_RECIPE_over_two_tables():
    """⚑ What a dialect IS, stated as a measurement.

    One recipe, two tables, two different levels -- different widths, different
    vocabularies, and neither one a subset of the other's cells.  If these ever
    came out identical the dialect axis would be decoration.
    """
    rwia = gifio.read(_paths("corridor")[0])
    flash = gifio.read(_paths("flash-corridor")[0])
    assert rwia.tiles != flash.tiles
    assert (rwia.width, rwia.height) != (flash.width, flash.height)
    assert set(rwia.tiles) != set(flash.tiles)
    # ...and they overlap heavily, because it IS one id space seen twice
    assert len(set(rwia.tiles) & set(flash.tiles)) > 20


def test_the_authorable_set_agrees_with_the_measured_census(any_table):
    """Each dialect against its OWN census -- including the one that has none."""
    from build import Vocab

    verdict = Vocab(any_table, GIF).check_against_census()
    if any_table.raw["censuses"]["gif_id_counts"]:
        assert "agrees exactly" in verdict
    else:
        assert "no census" in verdict
    Vocab(any_table, KITTY).check_against_census()


# ------------------------------------------------------------- the raw container
def test_the_committed_raw_map_is_the_committed_gif(manifest):
    """The two containers ship the SAME cells, and the ``.bin`` proves its shape."""
    from kittygif import rawio

    for name in [n for n in NAMES if ".bin" in generate.containers_of(n)]:
        base = os.path.join(SAMPLES, name, name)
        width, height = manifest[name]["grid"]
        from_gif = gifio.read(base + ".gif")
        from_raw = rawio.read(base + ".bin", width, height)
        assert from_raw.tiles == from_gif.tiles
        assert os.path.getsize(base + ".bin") == width * height


@pytest.mark.parametrize(
    "name", [n for n in NAMES if ".bin" in generate.containers_of(n)])
def test_raw2kitty_reproduces_the_committed_kitty_TWICE(name, tmp_path, manifest):
    """The committed sample, converted the way a consumer will convert a map.

    Twice, because a converter that is right once and different the second time
    is not a converter anyone can pin a SHA against.
    """
    from kittygif.cli import main

    base = os.path.join(SAMPLES, name, name)
    width, height = manifest[name]["grid"]
    shipped = open(base + ".kitty", "rb").read()
    for i in range(2):
        out = str(tmp_path / ("%s-%d.kitty" % (name, i)))
        assert main(["raw2kitty", base + ".bin", out,
                     "--width", str(width), "--height", str(height),
                     "--dialect", manifest[name]["dialect"],
                     "--name", name.upper(), "--quiet"]) == 0
        assert open(out, "rb").read() == shipped


def test_the_committed_flash_sample_carries_NO_refused_id(manifest):
    """A sample the converter would refuse is not a sample."""
    for name in NAMES:
        if generate.dialect_of(name) != "flash":
            continue
        table = _table(name)
        level = gifio.read(_paths(name)[0])
        assert not (set(level.tiles) & set(table.refused_gif_ids))


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
