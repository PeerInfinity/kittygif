"""The command line, end to end on synthetic files."""

import json

import fixtures
from kittygif import gifio, kittyio
from kittygif.cli import main


def _make_gif(tmp_path, table, palette, name="src.gif"):
    path = str(tmp_path / name)
    gifio.write(fixtures.l1_gif(table), path, palette)
    return path


def test_gif2kitty_then_kitty2gif(tmp_path, table, palette, capsys):
    src = _make_gif(tmp_path, table, palette)
    mid = str(tmp_path / "out.kitty")
    dst = str(tmp_path / "back.gif")

    assert main(["gif2kitty", src, mid, "--name", "CLI"]) == 0
    assert main(["kitty2gif", mid, dst]) == 0
    assert open(src, "rb").read() == open(dst, "rb").read()
    assert kittyio.read(mid, table).name == "CLI"


def test_the_level_name_defaults_to_the_output_stem(tmp_path, table, palette):
    src = _make_gif(tmp_path, table, palette)
    mid = str(tmp_path / "mylevel.kitty")
    assert main(["gif2kitty", src, mid]) == 0
    assert kittyio.read(mid, table).name == "MYLEVEL"


def test_the_json_report_is_written(tmp_path, table, palette):
    src = _make_gif(tmp_path, table, palette)
    mid = str(tmp_path / "out.kitty")
    report = str(tmp_path / "report.json")
    assert main(["gif2kitty", src, mid, "--report", report, "--quiet"]) == 0
    with open(report, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["direction"] == "gif->kitty"
    assert payload["source"] == src and payload["target"] == mid


def test_shared_options_work_on_either_side_of_the_subcommand(tmp_path, table, palette):
    src = _make_gif(tmp_path, table, palette)
    mid = str(tmp_path / "out.kitty")
    report = str(tmp_path / "r.json")
    assert main(["--quiet", "--report", report, "gif2kitty", src, mid]) == 0
    assert main(["gif2kitty", src, mid, "--quiet", "--report", report]) == 0


def test_a_mutant_table_can_be_selected_from_the_command_line(tmp_path, table, palette):
    """``--id-table`` is what lets a gate run against a broken copy of the DATA."""
    def break_it(raw):
        raw["pairs"].append({"gif": 200, "kitty": 0, "cls": "b",
                             "directions": "gif->kitty", "note": ""})

    path = fixtures.mutant_table(tmp_path, table, break_it)
    src = _make_gif(tmp_path, table, palette)
    mid = str(tmp_path / "out.kitty")
    assert main(["gif2kitty", src, mid, "--id-table", path, "--quiet"]) == 1


def test_info_reads_both_formats(tmp_path, table, palette, capsys):
    src = _make_gif(tmp_path, table, palette)
    mid = str(tmp_path / "out.kitty")
    assert main(["gif2kitty", src, mid, "--quiet"]) == 0
    assert main(["info", src, mid]) == 0
    out = capsys.readouterr().out
    assert "[gif]" in out and "[kitty]" in out and "painted" in out


def test_a_bad_file_exits_nonzero_with_a_message(tmp_path, table, capsys):
    bad = str(tmp_path / "bad.kitty")
    open(bad, "wb").write(b"\0" * 4)
    assert main(["kitty2gif", bad, str(tmp_path / "x.gif")]) == 1
    assert "kittygif:" in capsys.readouterr().err
