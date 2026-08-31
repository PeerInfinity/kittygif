"""The v16 container -- what the web Maker Mall editor writes.

``tests/data/webeditor-v16.kitty`` is a level AUTHORED FOR THIS PROJECT in the
official editor at robotwantskitty.com/web on 2026-08-31 and read back out of the
page's IndexedDB (S5's measurement of the export path).  It is our own content,
not a shipped game level -- the no-originals guard hashes it like everything else
and it is not one of the 35.

It matters that this fixture is a REAL file rather than one this package
synthesised: the v16 child order and metadata field list are read from
``WorldEditor::Save``, and a fixture built by our own writer through our own
table could not tell a wrong layout from a right one.  This one can.
"""

import os

import pytest

from kittygif import convert, gifio, kittyio
from kittygif.kittyio import KittyFormatError

import fixtures

WEB_EDITOR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "webeditor-v16.kitty")


@pytest.fixture
def web_level(table):
    return kittyio.read(WEB_EDITOR, table)


def test_the_web_editor_file_reads_as_version_16(web_level):
    assert web_level.file_version == 16
    assert web_level.width, web_level.height


def test_the_level_name_survives_the_wider_metadata_chunk(web_level):
    """v16 puts a 4-byte mUploadID in front of the name; v1's offset would read junk."""
    assert web_level.name == "KITTYGIF DEMO"


def test_the_authored_content_is_there(web_level, table):
    counts = {}
    for _x, _y, tile in web_level.cells():
        counts[tile] = counts.get(tile, 0) + 1
    solid = [kid for kid, n in counts.items() if kid != table.kitty_empty and n]
    assert solid, "the level was authored with terrain in it"
    assert web_level.robot and web_level.kitty
    # the editor places entities on half-tiles; positions travel as floats
    assert web_level.robot != web_level.kitty


def test_v16_carries_the_level_map_and_the_radio_sub_chunk(web_level):
    """Both are things v1 files never have -- reading them is the whole delta."""
    assert web_level.level_map is not None
    assert len(web_level.level_map) == web_level.width * web_level.height


def test_a_v16_level_converts_to_a_gif(web_level, table):
    gif, report = convert.kitty_to_gif(web_level, table)
    assert gif.width == web_level.width and gif.height == web_level.height
    assert report.counts()["a"] == web_level.width * web_level.height


def test_a_v16_level_writes_a_readable_gif(web_level, table, palette, tmp_path):
    gif, _ = convert.kitty_to_gif(web_level, table)
    path = str(tmp_path / "web.gif")
    gifio.write(gif, path, palette)
    assert gifio.read(path).tiles == gif.tiles


def test_the_v16_extra_chunk_is_not_carried_into_a_v1_file(web_level, table, tmp_path):
    """v16's extra chunk is a WIDER field list, so a v1 write must use the donor."""
    assert len(web_level.settings_chunk) != table.settings["chunk_bytes"]
    path = str(tmp_path / "asv1.kitty")
    kittyio.write(web_level, path, table)
    back = kittyio.read(path, table)
    assert back.file_version == table.file_version
    assert len(back.settings_chunk) == table.settings["chunk_bytes"]
    assert back.tiles == web_level.tiles


# --------------------------------------------------------------- the mutants
def test_reading_v16_at_v1s_NAME_OFFSET_is_caught(tmp_path, table):
    """The one judgement in the v16 layout: where the name starts."""
    path = fixtures.mutant_table(
        tmp_path, table,
        lambda raw: raw["kitty_file"]["read_layouts"]["16"].update(name_offset=0))
    mutant = kittyio.read(WEB_EDITOR, table.__class__.load(path))
    assert mutant.name != "KITTYGIF DEMO"


def test_reading_v16_at_v1s_CHILD_ORDER_is_caught(tmp_path, table):
    """v1's grid child is index 1 too, but its editor chunk at 5 does not exist here."""
    path = fixtures.mutant_table(
        tmp_path, table,
        lambda raw: raw["kitty_file"]["read_layouts"]["16"].update(child_count=6, editor=5))
    with pytest.raises(KittyFormatError, match="child chunks"):
        kittyio.read(WEB_EDITOR, table.__class__.load(path))


def test_the_v16_grid_sub_chunk_count_is_load_bearing(tmp_path, table):
    path = fixtures.mutant_table(
        tmp_path, table,
        lambda raw: raw["kitty_file"]["read_layouts"]["16"].update(grid_subchunks=0))
    with pytest.raises(KittyFormatError, match="sub-chunk"):
        kittyio.read(WEB_EDITOR, table.__class__.load(path))
