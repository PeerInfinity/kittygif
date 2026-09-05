"""The raw map-bytes container: one authored byte per cell, row-major.

The Flash build reads its level out of a ``DefineBinaryData`` blob with a plain
``readUnsignedByte`` loop (``FLASH_PS:170-176``), so the container carries the
grid and nothing else -- no dimensions, no palette, no header.  That absence is
the whole hazard this module is written around, and the tests below are about
it: the width and the height are the CALLER's claim about the file, and a claim
about a file has to be checked against the file.

Every fixture here is synthesised.  This repository ships no map bytes.
"""

import pytest

from kittygif import rawio
from kittygif.level import Level
from kittygif.table import GIF


def _write(tmp_path, data, name="map.bin"):
    path = str(tmp_path / name)
    with open(path, "wb") as fh:
        fh.write(bytes(data))
    return path


def test_row_major_order_is_the_flash_loop(tmp_path):
    """A 3x2 map whose six bytes are all DISTINCT pins the order, not just the size.

    ``LoadMap`` fills ``_loc2_[i]`` for i = 0..len-1 and indexes it as
    ``i % mapWidth, i / mapWidth`` -- row-major.  A fixture of repeated bytes
    would pass under either order, so every byte here is different.
    """
    path = _write(tmp_path, [10, 11, 12, 13, 14, 15])
    level = rawio.read(path, 3, 2)
    assert level.space == GIF
    assert (level.width, level.height) == (3, 2)
    assert level.tiles == [10, 11, 12, 13, 14, 15]
    assert level.at(0, 0) == 10 and level.at(2, 0) == 12
    assert level.at(0, 1) == 13 and level.at(2, 1) == 15


def test_the_whole_byte_range_survives(tmp_path):
    """The ids run to 255, so the reader must be unsigned and lossless."""
    path = _write(tmp_path, range(256))
    level = rawio.read(path, 16, 16)
    assert level.tiles == list(range(256))


def test_a_size_mismatch_is_refused_and_names_BOTH_numbers(tmp_path):
    """⚠ ``--width``/``--height`` are a CLAIM ABOUT THE FILE, so the file checks it.

    A raw map carries no dimensions.  Silently accepting a wrong pair would
    reshape someone's level -- the same cells, shifted one column per row -- and
    every downstream shape check would still pass.  So the refusal is by the
    numbers, and it prints the two it compared.
    """
    path = _write(tmp_path, range(100))
    with pytest.raises(ValueError) as exc:
        rawio.read(path, 10, 11)
    message = str(exc.value)
    assert "100" in message and "110" in message
    assert "10" in message and "11" in message


def test_a_short_file_is_refused_too(tmp_path):
    path = _write(tmp_path, range(99))
    with pytest.raises(ValueError, match="99"):
        rawio.read(path, 10, 10)


def test_a_zero_or_negative_dimension_is_refused(tmp_path):
    path = _write(tmp_path, [0])
    for width, height in ((0, 1), (1, 0), (-1, 1)):
        with pytest.raises(ValueError):
            rawio.read(path, width, height)


def test_the_name_is_carried_through(tmp_path):
    path = _write(tmp_path, [0, 0])
    assert rawio.read(path, 2, 1, name="MAP").name == "MAP"
    assert rawio.read(path, 2, 1).name == ""


def test_there_is_NO_raw_WRITER_and_that_is_deliberate(tmp_path):
    """⛔ A pin on an absence.

    Emitting Flash map bytes FROM a ``.kitty`` is the reverse converter this
    package deliberately does not have.  The Flash lethal range is ids 16..23
    (``FLASH_PL:377-380``), and 16 and 20 are exactly what the loader writes for
    an authored acid cell -- so a reverse converter would have to decide, per
    cell, between an id the loader generates and an id that kills on contact.
    Until that is measured rather than guessed, there is no writer to get it
    wrong.  A future slice that adds one deletes this test on purpose.
    """
    assert not hasattr(rawio, "write")
