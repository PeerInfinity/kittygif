"""``.kitty`` container I/O."""

import struct

import pytest

import fixtures
from kittygif import kittyio
from kittygif.kittyio import KittyFormatError, UnsupportedVersionError, pack_cell, unpack_cell


def test_cell_bitfield_round_trips():
    values = (73, 469, 1, 63, 500)
    assert unpack_cell(pack_cell(*values)) == values


def test_cell_bitfield_refuses_an_overflowing_field():
    with pytest.raises(KittyFormatError, match="7 bits"):
        pack_cell(layout=128)


def test_settings_block_matches_the_donor_byte_count(table):
    """Serialised from the field LIST, not copied: it must land on the measured size."""
    block = kittyio.settings_chunk(table)
    assert len(block) == table.settings["chunk_bytes"]


def test_optional_settings_field_is_what_makes_the_longer_variant(table):
    optional = [f for f in table.settings["fields"] if f.get("optional")]
    assert optional, "the donor records the longer variant's extra field"


def test_write_read_round_trip(tmp_path, table):
    level = fixtures.all_layouts_kitty(table)
    level.paint = [0] * len(level.tiles)
    level.paint_id = [0] * len(level.tiles)
    path = str(tmp_path / "synth.kitty")
    kittyio.write(level, path, table)
    back = kittyio.read(path, table)

    assert (back.width, back.height) == (level.width, level.height)
    assert back.tiles == level.tiles
    assert back.name == level.name
    assert back.robot == pytest.approx(level.robot)
    assert back.kitty == pytest.approx(level.kitty)
    assert back.file_version == table.file_version


def test_written_bytes_are_stable(tmp_path, table):
    """A read/write cycle of OUR OWN file is byte-exact -- the container is preserved."""
    level = fixtures.all_layouts_kitty(table)
    first = str(tmp_path / "a.kitty")
    kittyio.write(level, first, table)
    again = str(tmp_path / "b.kitty")
    kittyio.write(kittyio.read(first, table), again, table)
    assert open(first, "rb").read() == open(again, "rb").read()


def test_grid_chunk_is_exactly_8_plus_wh4(tmp_path, table):
    level = fixtures.all_layouts_kitty(table)
    path = str(tmp_path / "synth.kitty")
    kittyio.write(level, path, table)
    data = open(path, "rb").read()
    main, _ = kittyio._read_chunk(data, 4)
    assert len(main.children) == len(table.container["children"])
    assert len(main.children[1].payload) == 8 + level.width * level.height * 4
    assert data[-4:] == b"\0\0\0\0"          # the nested-savegame count


def test_an_unknown_savegame_version_is_refused_naming_the_ones_we_read(tmp_path, table):
    level = fixtures.all_layouts_kitty(table)
    path = str(tmp_path / "newer.kitty")
    kittyio.write(level, path, table)
    data = bytearray(open(path, "rb").read())
    data[0:4] = struct.pack("<i", 0x0011)          # one past the current SAVEGAME_VERSION
    open(path, "wb").write(bytes(data))
    with pytest.raises(UnsupportedVersionError, match="version 17") as exc:
        kittyio.read(path, table)
    # it must SAY what it can read, so the message is actionable
    for known in table.read_layouts:
        assert str(known) in str(exc.value)


def test_the_readable_versions_are_data_not_code(table):
    """Which containers this reader accepts is a table fact, and both are named."""
    assert set(table.read_layouts) == {1, 16}
    assert table.file_version == 1, "the WRITER stays on the campaign container"


def _repack(tmp_path, table, main, name):
    path = str(tmp_path / name)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<i", table.file_version) + main.to_bytes()
                 + struct.pack("<i", 0))
    return path


def test_the_mLevelMap_grid_variant_is_accepted_and_preserved(tmp_path, table):
    """5 of the 11 campaign levels append mLevelMap inside the grid chunk.

    (S1 recorded that no v1 file did; measured in S2, five of them do.  Both
    shapes are file version 1 and both load, so the reader takes either and hands
    the array back unchanged.)
    """
    level = fixtures.all_layouts_kitty(table)
    main, _ = kittyio._read_chunk(kittyio.to_bytes(level, table), 4)
    level_map = bytes(range(256)) * (level.width * level.height // 256 + 1)
    level_map = level_map[: level.width * level.height]
    main.children[1].payload += level_map
    path = _repack(tmp_path, table, main, "withmap.kitty")

    back = kittyio.read(path, table)
    assert back.level_map == level_map
    assert back.tiles == level.tiles
    again = str(tmp_path / "withmap2.kitty")
    kittyio.write(back, again, table)
    assert open(path, "rb").read() == open(again, "rb").read()


def test_a_writer_emits_the_SHORTER_grid_shape(tmp_path, table):
    level = fixtures.all_layouts_kitty(table)
    main, _ = kittyio._read_chunk(kittyio.to_bytes(level, table), 4)
    assert len(main.children[1].payload) == 8 + level.width * level.height * 4


def test_a_grid_chunk_of_neither_length_is_refused(tmp_path, table):
    level = fixtures.all_layouts_kitty(table)
    main, _ = kittyio._read_chunk(kittyio.to_bytes(level, table), 4)
    main.children[1].payload += b"\0" * 7           # neither shape
    path = _repack(tmp_path, table, main, "odd.kitty")
    with pytest.raises(KittyFormatError, match=r"not a\s+grid chunk this reader knows"):
        kittyio.read(path, table)


def test_a_grid_chunk_with_a_sub_chunk_is_refused(tmp_path, table):
    """The radio-text sub-chunk belongs to the v16 container, never to v1."""
    level = fixtures.all_layouts_kitty(table)
    main, _ = kittyio._read_chunk(kittyio.to_bytes(level, table), 4)
    main.children[1].children.append(kittyio.Chunk(b"\0\0\0\0"))
    path = _repack(tmp_path, table, main, "radio.kitty")
    with pytest.raises(KittyFormatError, match="sub-chunk"):
        kittyio.read(path, table)


def test_custom_draw_and_extra_data_are_written_zero(tmp_path, table):
    """They are computed at load in every campaign level, so a writer emits 0."""
    level = fixtures.all_layouts_kitty(table)
    level.custom_draw = [1] * len(level.tiles)
    level.extra_data = [63] * len(level.tiles)
    path = str(tmp_path / "zeroed.kitty")
    kittyio.write(level, path, table)
    back = kittyio.read(path, table)
    assert set(back.custom_draw or []) == {0}
    assert set(back.extra_data or []) == {0}
