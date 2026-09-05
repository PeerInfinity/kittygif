"""The raw map container, driven the way the command line drives it.

``tests/test_rawio.py`` is about the reader; this file is about the claim the
reader lets the CLI make -- that the CONTAINER a level arrives in does not
change what it MEANS.  One synthesised level, written into both containers,
converted by the same table, must produce the same ``.kitty`` byte for byte.

Everything here is synthesised from the id table.  No map bytes of anyone's
game are in this repository.
"""

import json
import os

import pytest

import fixtures
from kittygif import gifio
from kittygif.cli import main


def _raw(tmp_path, level, name="map.bin"):
    """Write a synthesised level as raw map bytes: one byte per cell, row-major.

    Written HERE rather than by the package on purpose -- ``kittygif`` reads
    this container and deliberately does not write it (see
    ``tests/test_rawio.py``'s pin on that absence).  A test that needs the
    bytes makes its own.
    """
    path = str(tmp_path / name)
    with open(path, "wb") as fh:
        fh.write(bytes(level.tiles))
    return path


def test_raw2kitty_matches_gif2kitty_ON_THE_SAME_CELLS(tmp_path, table, palette):
    """⚑ The measurement that the container really is orthogonal to the meaning.

    If these two files ever differ, something in a container reader is leaking
    into the conversion.
    """
    level = fixtures.l1_gif(table)
    gif_path, raw_path = str(tmp_path / "a.gif"), _raw(tmp_path, level)
    gifio.write(level, gif_path, palette)

    from_gif, from_raw = str(tmp_path / "g.kitty"), str(tmp_path / "r.kitty")
    assert main(["gif2kitty", gif_path, from_gif, "--name", "SAME", "--quiet"]) == 0
    assert main(["raw2kitty", raw_path, from_raw, "--width", str(level.width),
                 "--height", str(level.height), "--name", "SAME", "--quiet"]) == 0
    assert open(from_gif, "rb").read() == open(from_raw, "rb").read()


def test_raw2kitty_is_deterministic_twice(tmp_path, table):
    level = fixtures.l1_gif(table)
    raw_path = _raw(tmp_path, level)
    outs = []
    for i in range(2):
        out = str(tmp_path / ("d%d.kitty" % i))
        assert main(["raw2kitty", raw_path, out, "--width", str(level.width),
                     "--height", str(level.height), "--name", "DET", "--quiet"]) == 0
        outs.append(open(out, "rb").read())
    assert outs[0] == outs[1]


def test_raw2kitty_refuses_a_size_mismatch_by_the_numbers(tmp_path, table, capsys):
    """The refusal names the byte count and the claimed cell count, both."""
    level = fixtures.l1_gif(table)
    raw_path = _raw(tmp_path, level)
    assert main(["raw2kitty", raw_path, str(tmp_path / "x.kitty"),
                 "--width", str(level.width + 1),
                 "--height", str(level.height), "--quiet"]) == 1
    err = capsys.readouterr().err
    assert str(len(level.tiles)) in err
    assert str((level.width + 1) * level.height) in err
    assert not os.path.exists(str(tmp_path / "x.kitty")), \
        "a refused conversion must not leave a half-written level behind"


def test_raw2kitty_requires_both_dimensions(tmp_path, table, capsys):
    """Neither one alone: a raw map cannot be read on a guess.

    ⚠ This arm is only meaningful because ``raw2kitty`` EXISTS -- before it did,
    argparse rejected the subcommand itself and the test passed for the wrong
    reason.  The control below (the full pair works) is what keeps it honest.
    """
    level = fixtures.l1_gif(table)
    raw_path = _raw(tmp_path, level)
    out = str(tmp_path / "x.kitty")
    for partial in (["--width", str(level.width)], ["--height", str(level.height)], []):
        with pytest.raises(SystemExit) as exc:
            main(["raw2kitty", raw_path, out] + partial + ["--quiet"])
        assert exc.value.code != 0
    assert main(["raw2kitty", raw_path, out, "--width", str(level.width),
                 "--height", str(level.height), "--quiet"]) == 0


def test_raw2kitty_writes_its_report_and_viewer_pair(tmp_path, table):
    level = fixtures.l1_gif(table)
    raw_path = _raw(tmp_path, level)
    report, prefix = str(tmp_path / "r.json"), str(tmp_path / "v")
    assert main(["raw2kitty", raw_path, str(tmp_path / "o.kitty"),
                 "--width", str(level.width), "--height", str(level.height),
                 "--report", report, "--emit-json", prefix, "--quiet"]) == 0
    with open(report, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["direction"] == "gif->kitty" and payload["source"] == raw_path
    assert os.path.exists(prefix + "_tilemap.json")
    assert os.path.exists(prefix + "_tiles.json")


def test_raw2kitty_honours_the_name_and_the_paint_flags(tmp_path, table):
    """The flags are shared with ``gif2kitty`` because the tail is shared."""
    from kittygif import kittyio

    level = fixtures.l1_gif(table)
    raw_path = _raw(tmp_path, level)
    painted, bare = str(tmp_path / "p.kitty"), str(tmp_path / "b.kitty")
    common = ["--width", str(level.width), "--height", str(level.height), "--quiet"]
    assert main(["raw2kitty", raw_path, painted, "--name", "PAINTED"] + common) == 0
    assert main(["raw2kitty", raw_path, bare, "--name", "PAINTED", "--no-paint"]
                + common) == 0
    assert kittyio.read(painted, table).name == "PAINTED"
    assert sum(1 for p in kittyio.read(painted, table).paint_id if p) > 0
    assert sum(1 for p in kittyio.read(bare, table).paint_id if p) == 0


# --------------------------------------------------------------------- info
def test_info_reads_a_raw_map_when_given_its_dimensions(tmp_path, table, capsys):
    level = fixtures.l1_gif(table)
    raw_path = _raw(tmp_path, level)
    assert main(["info", raw_path, "--width", str(level.width),
                 "--height", str(level.height)]) == 0
    out = capsys.readouterr().out
    assert "[gif]" in out
    assert "%dx%d" % (level.width, level.height) in out


def test_info_refuses_a_raw_map_without_them(tmp_path, table, capsys):
    """⛔ Not "reported as a savegame version 0": named for what it is.

    Before this slice a ``.bin`` fell through to the ``.kitty`` parser, which
    read its first four bytes as a file version and complained about a savegame
    -- blaming the file for the caller's missing argument.
    """
    raw_path = _raw(tmp_path, fixtures.l1_gif(table))
    assert main(["info", raw_path]) == 1
    err = capsys.readouterr().err
    assert "--width" in err and "--height" in err
    assert "savegame" not in err


def test_info_still_needs_no_dimensions_for_the_two_old_containers(
        tmp_path, table, palette, capsys):
    """The control: the containers that DO state their own shape are untouched."""
    src = str(tmp_path / "s.gif")
    gifio.write(fixtures.l1_gif(table), src, palette)
    mid = str(tmp_path / "s.kitty")
    assert main(["gif2kitty", src, mid, "--quiet"]) == 0
    assert main(["info", src, mid]) == 0


def test_emit_json_reads_a_raw_map_too(tmp_path, table):
    level = fixtures.l1_gif(table)
    raw_path = _raw(tmp_path, level)
    prefix = str(tmp_path / "e")
    assert main(["emit-json", raw_path, prefix, "--width", str(level.width),
                 "--height", str(level.height), "--quiet"]) == 0
    with open(prefix + "_tilemap.json", encoding="utf-8") as fh:
        tilemap = json.load(fh)
    assert tilemap["map_width"] == level.width
    assert len(tilemap["tiles"]) == level.height
