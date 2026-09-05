"""The DATA has to hold together before any gate that reads it means anything.

Since this package ships more than one dialect, the arms that are about the
table's SHAPE run over every packaged dialect (the ``any_table`` fixture), and
the arms that are about a particular dialect's CONTENT name it.  ⛔ No arm may
be about "the table" without saying which -- a shape check that quietly only
ever ran on the default table is a gate the second dialect does not have.
"""

import json

import pytest

import fixtures
from kittygif.table import CLASS_ORDER, IdTable, TableError


def test_shipped_table_is_consistent(any_table):
    assert any_table.check() == [], any_table.path


def test_every_id_has_a_RULE_or_a_REFUSAL(any_table):
    """No id may be silently unconvertible: a gap would show up as a crash on
    real data.  A REFUSAL is an answer -- the table saying this id must not be
    translated, with the line that says so -- and a gap is not."""
    refused = set(any_table.refused_gif_ids)
    assert set(any_table.gif_ids) == set(any_table.forward) | refused
    assert not (set(any_table.forward) & refused), \
        "an id cannot be both ruled and refused"
    assert set(any_table.kitty_ids) == set(any_table.reverse)


def test_classes_and_names(any_table):
    for rule in list(any_table.forward.values()) + list(any_table.reverse.values()):
        assert rule.cls in CLASS_ORDER
        assert rule.source_name and rule.target_name


def test_every_refusal_carries_its_reason(any_table):
    """A refusal with no reason is an unexplained crash waiting to happen."""
    for gid in any_table.refused_gif_ids:
        reason = any_table.refusal(gid)
        assert isinstance(reason, str) and len(reason) > 40, gid


def test_position_fields_are_reachable_from_both_ends(any_table):
    for field_name in any_table.position_field_names:
        gid = any_table.position_source_gif_id(field_name)
        assert any_table.forward[gid].position_field == field_name
        assert any_table.position_rules[field_name].target_ids == (gid,)


def test_ambiguous_table_is_refused(tmp_path, table):
    """Two class-a rows for one source id is a DATA defect, and says so."""

    def mutate(raw):
        row = dict(raw["pairs"][1])
        row["cls"] = "a"
        raw["pairs"].append(row)

    path = fixtures.mutant_table(tmp_path, table, mutate)
    with pytest.raises(TableError, match="cannot say which"):
        IdTable.load(path)


def test_check_catches_an_id_that_is_not_in_the_space(tmp_path, table):
    def mutate(raw):
        raw["pairs"].append(
            {"gif": 200, "kitty": 0, "cls": "b", "directions": "gif->kitty", "note": ""}
        )

    path = fixtures.mutant_table(tmp_path, table, mutate)
    assert any("absent from gif.ids" in p for p in IdTable.load(path).check())


def test_vpair_targets_are_couples(any_table):
    for rule in any_table.forward.values():
        if rule.shape == "vpair":
            assert rule.target_ids is not None and len(rule.target_ids) == 2


def test_data_files_ship_with_the_package(any_table, palette):
    for path in (any_table.path, palette.path):
        with open(path, encoding="utf-8") as fh:
            json.load(fh)


def test_the_level_file_names_come_from_the_census(any_table):
    """The overwrite-slot list is DERIVED from the census, in EVERY dialect.

    ⚑ The two dialects have different answers and both are checked BY NAME
    rather than one of them being skipped:

    * **rwia** -- the game loads a level out of a set of shipped ``.gif`` files
      and a custom level is an overwrite of one of them, so the census keys ARE
      the slot list and it must be non-empty.
    * **flash** -- the game embeds exactly one map inside the SWF.  There are no
      level files, so there is no census to key on and the list is empty.  That
      is a measured fact about the game, not a gap in the table, and the table's
      own ``censuses._note`` has to say so.
    """
    files = any_table.gif_level_files
    counts = any_table.raw["censuses"]["gif_id_counts"]
    assert files == sorted(counts)

    if counts:
        assert all(f.endswith(".gif") for f in files)
        # every named file really was censused, i.e. the list is not decoration
        for name in files:
            assert counts[name]
    else:
        assert files == []
        assert any_table.raw["censuses"].get("_note"), (
            "%s ships an empty census with no explanation; empty has to be a "
            "stated fact, not a silence" % any_table.path)


def test_exactly_one_packaged_dialect_has_a_gif_census(table, flash):
    """The control that keeps the arm above from passing on two empty censuses."""
    assert table.raw["censuses"]["gif_id_counts"] != {}
    assert flash.raw["censuses"]["gif_id_counts"] == {}
