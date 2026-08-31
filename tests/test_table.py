"""The DATA has to hold together before any gate that reads it means anything."""

import json

import pytest

import fixtures
from kittygif.table import CLASS_ORDER, IdTable, TableError


def test_shipped_table_is_consistent(table):
    assert table.check() == []


def test_every_id_in_both_spaces_has_a_rule(table):
    """No id may be silently unconvertible: a gap would show up as a crash on real data."""
    assert set(table.gif_ids) == set(table.forward)
    assert set(table.kitty_ids) == set(table.reverse)


def test_classes_and_names(table):
    for rule in list(table.forward.values()) + list(table.reverse.values()):
        assert rule.cls in CLASS_ORDER
        assert rule.source_name and rule.target_name


def test_position_fields_are_reachable_from_both_ends(table):
    for field_name in table.position_field_names:
        gid = table.position_source_gif_id(field_name)
        assert table.forward[gid].position_field == field_name
        assert table.position_rules[field_name].target_ids == (gid,)


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


def test_vpair_targets_are_couples(table):
    for rule in table.forward.values():
        if rule.shape == "vpair":
            assert rule.target_ids is not None and len(rule.target_ids) == 2


def test_data_files_ship_with_the_package(table, palette):
    for path in (table.path, palette.path):
        with open(path, encoding="utf-8") as fh:
            json.load(fh)


def test_the_level_file_names_come_from_the_census(table):
    """The overwrite-slot list is DERIVED: the census keys are the shipped level set."""
    files = table.gif_level_files
    assert files == sorted(table.raw["censuses"]["gif_id_counts"])
    assert files and all(f.endswith(".gif") for f in files)
    # every named file really was censused, i.e. the list is not decoration
    for name in files:
        assert table.raw["censuses"]["gif_id_counts"][name]
