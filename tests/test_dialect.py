"""Two orthogonal axes: the CONTAINER a level is read from, and the DIALECT that
interprets its ids.

Until this slice the two were fused -- ``gif2kitty`` meant "an indexed gif, read
through the packaged table".  They are separate questions: an id space can be
delivered in a gif's palette indices or as raw bytes, and the same bytes mean
different things to the two engines that read this id space.  ``--dialect``
selects the table; the subcommand selects the container.

Resolution order is pinned here because it is the seam every mutant gate in this
suite runs through, and a dialect flag that quietly outranked ``--id-table``
would take that seam away.
"""

import json
import os

import pytest

import fixtures
from kittygif import gifio, rawio
from kittygif.cli import main
from kittygif.convert import gif_to_kitty
from kittygif.table import DATA_DIR, IdTable, TableError


# ------------------------------------------------------------------ resolution
def test_the_default_dialect_is_the_packaged_table():
    """No argument at all still loads exactly what it loaded before this slice."""
    assert IdTable.load().path == os.path.join(DATA_DIR, "id-table.json")
    assert IdTable.load(dialect=None).path == IdTable.load().path


def test_naming_the_default_dialect_is_the_same_file():
    assert IdTable.load(dialect="rwia").path == IdTable.load().path


def test_an_explicit_path_beats_the_dialect(tmp_path, table):
    """⛔ ``--id-table`` is the mutant seam; a dialect must never outrank it."""
    path = fixtures.mutant_table(tmp_path, table, lambda raw: None)
    assert IdTable.load(path, dialect="flash").path == path
    assert IdTable.load(path, dialect="rwia").path == path


def test_the_environment_variable_beats_the_dialect(tmp_path, table, monkeypatch):
    path = fixtures.mutant_table(tmp_path, table, lambda raw: None)
    monkeypatch.setenv("KITTYGIF_ID_TABLE", path)
    assert IdTable.load(dialect="flash").path == path
    assert IdTable.load().path == path


def test_an_unknown_dialect_is_refused_BY_NAME():
    with pytest.raises(TableError) as exc:
        IdTable.load(dialect="rwb")
    message = str(exc.value)
    assert "rwb" in message
    assert "rwia" in message and "flash" in message, \
        "the refusal must name the dialects there ARE, not just the one there is not"


def test_every_named_dialect_ships_a_table_that_loads_and_checks():
    """The dialect list is DATA-adjacent: each name must resolve to a real file."""
    from kittygif.table import DIALECTS

    assert DIALECTS, "there is at least one dialect"
    for name in DIALECTS:
        loaded = IdTable.load(dialect=name)
        assert loaded.check() == [], "%s: %r" % (name, loaded.check())
        assert loaded.dialect == name, (
            "%s's file declares _dialect %r -- the file and the name it is "
            "reached by must agree" % (name, loaded.dialect))


def test_the_cli_refuses_an_unknown_dialect(tmp_path, table, palette, capsys):
    """A usage error, and it must NAME the dialects there are.

    argparse settles this one before any file is opened, which is the right
    place: exit 2 with the choices printed, rather than a converter that starts
    work and then cannot find a table.
    """
    src = str(tmp_path / "src.gif")
    gifio.write(fixtures.l1_gif(table), src, palette)
    with pytest.raises(SystemExit) as exc:
        main(["gif2kitty", src, str(tmp_path / "o.kitty"), "--dialect", "rwb"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "rwb" in err and "rwia" in err and "flash" in err


def test_the_cli_dialect_flag_selects_the_table(tmp_path, table, palette, capsys):
    """``--dialect`` reaches the converter: the report records which file ran."""
    src = str(tmp_path / "src.gif")
    gifio.write(fixtures.l1_gif(table), src, palette)
    report = str(tmp_path / "r.json")
    assert main(["gif2kitty", src, str(tmp_path / "o.kitty"),
                 "--dialect", "rwia", "--report", report, "--quiet"]) == 0
    with open(report, encoding="utf-8") as fh:
        assert os.path.basename(json.load(fh)["id_table"]) == "id-table.json"


# --------------------------------------------------------------- raw2kitty CLI
def _raw(tmp_path, level, name="map.bin"):
    path = str(tmp_path / name)
    with open(path, "wb") as fh:
        fh.write(bytes(level.tiles))
    return path


def test_raw2kitty_matches_gif2kitty_ON_THE_SAME_CELLS(tmp_path, table, palette):
    """⚑ The measurement that the two axes really are orthogonal.

    One synthesised level, written into BOTH containers, converted by the same
    dialect: the two ``.kitty`` files must be byte-identical.  If they are not,
    something in the container reader is leaking into the meaning.
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
    level = fixtures.l1_gif(table)
    raw_path = _raw(tmp_path, level)
    assert main(["raw2kitty", raw_path, str(tmp_path / "x.kitty"),
                 "--width", str(level.width + 1),
                 "--height", str(level.height), "--quiet"]) == 1
    err = capsys.readouterr().err
    assert str(len(level.tiles)) in err
    assert str((level.width + 1) * level.height) in err


def test_raw2kitty_requires_both_dimensions(tmp_path, table):
    raw_path = _raw(tmp_path, fixtures.l1_gif(table))
    with pytest.raises(SystemExit):
        main(["raw2kitty", raw_path, str(tmp_path / "x.kitty"), "--width", "16"])


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
    raw_path = _raw(tmp_path, fixtures.l1_gif(table))
    assert main(["info", raw_path]) == 1
    assert "--width" in capsys.readouterr().err


def test_info_still_needs_no_dimensions_for_the_two_old_containers(
        tmp_path, table, palette, capsys):
    src = str(tmp_path / "s.gif")
    gifio.write(fixtures.l1_gif(table), src, palette)
    mid = str(tmp_path / "s.kitty")
    assert main(["gif2kitty", src, mid, "--quiet"]) == 0
    assert main(["info", src, mid]) == 0


# ------------------------------------------------------ the Flash table itself
def test_the_flash_table_is_consistent(flash):
    assert flash.check() == []


def test_every_gif_id_has_a_RULE_or_a_REFUSAL(flash, table):
    """No id may be silently unconvertible -- but a refusal is an ANSWER.

    The packaged table answers every id with a rule.  The Flash table answers
    eight of them with a refusal instead, which is still an answer: what must
    never happen is an id the table says nothing about at all.
    """
    for loaded in (table, flash):
        refused = {i for i, meta in loaded.gif_ids.items() if meta.get("refuse")}
        assert set(loaded.gif_ids) == set(loaded.forward) | refused
        assert set(loaded.kitty_ids) == set(loaded.reverse)


def test_the_packaged_table_refuses_NOTHING(table):
    """The negative control for the whole refusal seam."""
    assert [i for i, meta in table.gif_ids.items() if meta.get("refuse")] == []


def test_the_flash_table_refuses_exactly_the_lethal_range(flash):
    """⚑ 16..23, the WHOLE range, TIME ORB included.

    ``Player.update`` probes one tile and dies on any id in 16..23
    (FLASH_PL:377-380) -- it is a range test, not a list, so a table that
    refused seven of the eight would leave one lethal id mapping to a bonus.
    """
    refused = sorted(i for i, meta in flash.gif_ids.items() if meta.get("refuse"))
    assert refused == list(range(16, 24))
    for gid in refused:
        assert gid not in flash.forward
        reason = flash.gif_ids[gid]["refuse"]
        assert "377" in reason, "the refusal must carry the line that kills"


def test_a_refused_id_may_not_be_named_by_ANY_pair_row(flash):
    """Both directions.  A reverse row targeting a refused id would EMIT one."""
    for row in flash.raw["pairs"]:
        ids = row["gif"] if isinstance(row["gif"], list) else [row["gif"]]
        for gid in ids:
            assert not flash.gif_ids[gid].get("refuse"), row


def test_check_CATCHES_a_pair_row_that_names_a_refused_id(tmp_path, flash):
    """The mutant for the arm above: the integrity check has to see it."""
    def re_add(raw):
        raw["pairs"].append({"gif": 16, "kitty": 0, "cls": "b",
                             "directions": "gif->kitty", "note": "a re-added hazard"})

    path = fixtures.mutant_table(tmp_path, flash, re_add)
    problems = IdTable.load(path).check()
    assert any("refuse" in p for p in problems), problems


def test_the_flash_dialect_has_NO_class_c_forward_row(flash):
    """⚑ Nothing authorable in the Flash map is unrepresentable in a .kitty.

    Every byte the Flash game reads is special, decor or solid, and the .kitty
    side has all three -- so ``substitute_rule`` can never fire in this
    direction.  If a future row needs class (c), that is a finding about the
    two engines, and this arm is where it surfaces.
    """
    assert {rule.cls for rule in flash.forward.values()} <= {"a", "b"}


def test_the_flash_dialect_HAS_class_c_going_back(flash):
    """The other direction is still partial: the .kitty side is a bigger game."""
    assert any(rule.cls == "c" for rule in flash.reverse.values())


def test_the_secret_block_loses_its_flash_target_and_is_substituted(flash, table):
    """⚑ The consequence of refusing 23, traced to the reverse direction.

    In the packaged table the C++ SECRET_BLOCK and gif 23 are an exact
    functional match, a class-(a) ``both`` row.  In the Flash dialect gif 23 is
    lethal acid, so that row cannot survive -- and the block must NOT come back
    as 23, or converting a .kitty would write a death trap where the level meant
    walkable air.  It falls to the class-(c) substitute path instead, which is
    the path that reports.
    """
    secret = table.forward[23].target_id           # derived, not typed out
    assert table.reverse[secret].target_ids == (23,)
    assert table.reverse[secret].cls == "a"

    assert flash.reverse[secret].cls == "c"
    assert flash.reverse[secret].target_ids == (flash.gif_empty,)


# ------------------------------------------------------------- the drift gate
#: the blocks that describe the ``.kitty`` SIDE.  One game, so the two dialects
#: must never disagree about it; only the gif side is dialect-specific.
KITTY_SIDE = ("kitty", "kitty_file", "paint", "settings_donor", "substitute_rule")


@pytest.mark.parametrize("block", KITTY_SIDE)
def test_the_two_dialects_agree_BYTE_FOR_BYTE_about_the_kitty_side(block, table, flash):
    """⛔ The drift gate.

    Two tables describing one container is the standing hazard of this design:
    a fix applied to one file and not the other is invisible until a level comes
    out wrong.  These blocks are the ``.kitty`` side -- the layout ids, the chunk
    layouts, the paint model, the donor settings -- and they are ONE game's
    facts.  They are compared as serialised JSON, not field by field, so a new
    key cannot slip through an incomplete comparison.
    """
    assert json.dumps(table.raw[block], sort_keys=True) == \
        json.dumps(flash.raw[block], sort_keys=True)


def test_the_drift_gate_goes_RED_on_a_drifted_copy(tmp_path, table, flash):
    """A gate that cannot fail is not a gate: drift one block and watch it."""
    def drift(raw):
        raw["kitty_file"]["tile_size_px"] = raw["kitty_file"]["tile_size_px"] + 1

    drifted = IdTable.load(fixtures.mutant_table(tmp_path, flash, drift))
    assert drifted.check() == [], "the drifted copy is still a VALID table"
    same = [b for b in KITTY_SIDE
            if json.dumps(table.raw[b], sort_keys=True)
            == json.dumps(drifted.raw[b], sort_keys=True)]
    assert "kitty_file" not in same, "the gate did not see the drift"
    assert len(same) == len(KITTY_SIDE) - 1, "the mutant moved more than it claimed"


def test_the_gif_side_really_does_DIFFER_between_the_dialects(table, flash):
    """The control for the gate above: it must not be comparing two copies."""
    assert json.dumps(table.raw["gif"], sort_keys=True) != \
        json.dumps(flash.raw["gif"], sort_keys=True)


# ---------------------------------------------------------------- the census
def test_the_flash_table_has_no_gif_FILE_census_and_says_where_its_census_IS(flash):
    """An empty FILE census is a fact here; a missing census is not, any more.

    ``gif_level_files`` derives the overwrite-slot list from ``gif_id_counts``'
    keys.  A game whose map lives inside the SWF has no such slots, so the list
    is empty -- but its ids ARE censused, under the block keyed by the class
    that carries the map.  Both halves have to be true at once, or the empty
    list stops meaning "nothing to overwrite" and starts meaning "nobody
    looked", and the table has to say which in prose a reader can check.
    """
    assert flash.raw["censuses"]["gif_id_counts"] == {}
    assert flash.gif_level_files == []
    assert flash.gif_census_block == "embedded_map_id_counts"
    assert flash.gif_census, "the flash dialect's ids are censused somewhere"
    note = flash.raw["censuses"]["_note"]
    assert "embedded_map_id_counts" in note, \
        "the note must name the block the census actually lives in"
    assert "gif_id_counts" in note, \
        "...and the block it does NOT live in, since that is the surprising half"


def test_the_packaged_table_still_HAS_its_FILE_census(table):
    """The other half of the arm above: neither dialect is skipped silently."""
    assert table.raw["censuses"]["gif_id_counts"]
    assert table.gif_census_block == "gif_id_counts"
    assert table.gif_level_files and all(f.endswith(".gif") for f in table.gif_level_files)


# ------------------------------------------------------- refusal, end to end
def _raw(tmp_path, level, name="map.bin"):
    path = str(tmp_path / name)
    with open(path, "wb") as fh:
        fh.write(bytes(level.tiles))
    return path


def _flash_map(flash, gid):
    """A minimal synthesised Flash map: the two spawns, a floor, and ``gid``."""
    return fixtures.gif_grid(flash, [gid])


@pytest.mark.parametrize("gid", list(range(16, 24)))
def test_a_refused_id_stops_the_conversion_and_names_ITSELF(gid, flash):
    level = _flash_map(flash, gid)
    with pytest.raises(Exception) as exc:
        gif_to_kitty(level, flash, name="REFUSED")
    message = str(exc.value)
    assert str(gid) in message
    assert "377" in message, "the reason travels with the refusal"
    assert "1 cell" in message, "the refusal counts the cells it found"


def test_the_refusal_counts_cells_but_NEVER_locates_them(flash):
    """⛔ A raw map's cells are the game's; a count is derived, a map is content."""
    level = fixtures.gif_grid(flash, [], runs={})
    for x in range(3):
        level.set(x, 3, 16)
    with pytest.raises(Exception) as exc:
        gif_to_kitty(level, flash, name="REFUSED")
    message = str(exc.value)
    assert "3 cell" in message
    assert "(0,3)" not in message and "(2,3)" not in message


def test_a_refusal_beats_an_unknown_id(flash):
    """Both wrong at once: the LETHAL one is the one to say first."""
    level = fixtures.gif_grid(flash, [16])
    level.set(5, 3, 99)
    with pytest.raises(Exception, match="377"):
        gif_to_kitty(level, flash, name="BOTH")


def test_an_unknown_id_still_refuses_with_the_EXISTING_text(flash):
    """The refusal seam must not have moved the message that was already there."""
    level = fixtures.gif_grid(flash, [])
    level.set(5, 3, 99)
    with pytest.raises(Exception, match="which the table does not know"):
        gif_to_kitty(level, flash, name="UNKNOWN")


def test_NEGATIVE_CONTROL_the_rwia_dialect_still_maps_16_to_23(table):
    """⚑ The refusal is a property of the FLASH TABLE, not of the converter.

    The same eight ids are ordinary bonus collectibles in the RWIA dialect, and
    a level carrying them must still convert exactly as it did before this
    slice.
    """
    level = fixtures.gif_grid(table, list(range(16, 24)))
    out, report = gif_to_kitty(level, table, name="RWIA")
    assert out.tiles.count(table.kitty_empty) > 0
    converted = {e.source_id for e in report.entries}
    assert set(range(16, 24)) <= converted


def test_raw2kitty_refuses_a_flash_map_carrying_acid(tmp_path, flash, capsys):
    """The whole seam, through the command line, on the raw container."""
    raw_path = _raw(tmp_path, _flash_map(flash, 16))
    level = _flash_map(flash, 16)
    assert main(["raw2kitty", raw_path, str(tmp_path / "x.kitty"),
                 "--dialect", "flash", "--width", str(level.width),
                 "--height", str(level.height), "--quiet"]) == 1
    err = capsys.readouterr().err
    assert "16" in err and "377" in err
    assert not os.path.exists(str(tmp_path / "x.kitty"))


def test_the_same_bytes_convert_FINE_as_rwia(tmp_path, flash, table, capsys):
    """⚑ The dialect is the whole difference: same file, same command, two answers.

    This is the hazard the refusal exists for, stated as a measurement -- a map
    that is a bonus level in one dialect and a death trap in the other.
    """
    level = _flash_map(flash, 16)
    raw_path = _raw(tmp_path, level)
    dims = ["--width", str(level.width), "--height", str(level.height), "--quiet"]
    assert main(["raw2kitty", raw_path, str(tmp_path / "f.kitty"),
                 "--dialect", "flash"] + dims) == 1
    assert main(["raw2kitty", raw_path, str(tmp_path / "r.kitty"),
                 "--dialect", "rwia"] + dims) == 0


def test_a_flash_map_of_every_authorable_id_converts(tmp_path, flash):
    """The positive control: refusal is not the converter's answer to everything."""
    authorable = sorted(i for i, meta in flash.gif_ids.items()
                        if "observed" not in meta and not meta.get("refuse"))
    # the two spawn ids are placed BY the fixture, as the one-per-level fields
    # they are; laying them out again as ordinary cells is a malformed level.
    spawns = {flash.position_source_gif_id(f) for f in flash.position_field_names}
    laid_out = [g for g in authorable if g not in spawns]
    gates = [g for g in laid_out
             if g in flash.forward and flash.forward[g].shape == "vpair"]
    plain = [g for g in laid_out if g not in gates]
    level = fixtures.gif_grid(flash, plain + gates,
                              runs={g: [1, 2, 3, 4] for g in gates})
    out, report = gif_to_kitty(level, flash, name="ALL")
    assert not report.solvability_at_risk, \
        "the Flash dialect has no class-(c) forward row, so nothing is at risk"
    census = {e.source_id for e in report.entries}
    assert set(authorable) <= census | {flash.gif_empty}
