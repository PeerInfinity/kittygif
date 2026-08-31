"""Indexed-gif I/O: the INDEX is the payload, and it must survive a save."""

import pytest

import fixtures
from kittygif import gifio
from kittygif.gifio import GifFormatError


def test_write_read_preserves_every_index(tmp_path, table, palette):
    level = fixtures.l1_gif(table)
    path = str(tmp_path / "level.gif")
    gifio.write(level, path, palette)
    back = gifio.read(path)
    assert (back.width, back.height) == (level.width, level.height)
    assert back.tiles == level.tiles


def test_the_written_palette_is_the_measured_one(tmp_path, table, palette):
    from PIL import Image

    level = fixtures.l1_gif(table)
    path = str(tmp_path / "level.gif")
    gifio.write(level, path, palette)
    with Image.open(path) as im:
        raw = im.getpalette() or []
    for gid, rgb in palette.rgb_by_id.items():
        if gid in set(level.tiles):
            assert tuple(raw[gid * 3 : gid * 3 + 3]) == rgb, "id %d lost its colour" % gid


def test_a_truecolour_image_is_refused(tmp_path):
    from PIL import Image

    # A GIF is always indexed once PIL has saved it, so the truecolour case has to
    # arrive in a format that can carry one.
    path = str(tmp_path / "rgb.png")
    Image.new("RGB", (4, 4)).save(path)
    with pytest.raises(GifFormatError, match="INDEXED"):
        gifio.read(path)


def test_an_animation_is_refused(tmp_path, table, palette):
    from PIL import Image

    level = fixtures.l1_gif(table)
    frame = Image.new("P", (level.width, level.height))
    frame.putpalette(palette.flat())
    frame.putdata(level.tiles)
    path = str(tmp_path / "anim.gif")
    second = frame.copy()
    second.putdata(list(reversed(level.tiles)))
    frame.save(path, save_all=True, append_images=[second], optimize=False)
    with pytest.raises(GifFormatError, match="single frame"):
        gifio.read(path)


def test_the_whole_256_entry_colour_table_is_written(tmp_path, table, palette):
    """The regression pin for PIL's optimize= default.

    GifImagePlugin defaults ``optimize=True`` when no ``palette=`` is passed, and
    an optimised save RENUMBERS the palette down to the colours in use -- which
    rewrites every tile id in the file.  A short colour table is the symptom.
    """
    from PIL import Image

    level = fixtures.gif_grid(table, sorted(fixtures.mappable_gif_ids(table))[:4])
    path = str(tmp_path / "sparse.gif")
    gifio.write(level, path, palette)
    with Image.open(path) as im:
        assert len(im.getpalette() or []) // 3 == 256
    assert gifio.read(path).tiles == level.tiles
