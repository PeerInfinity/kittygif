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
from kittygif.table import (CLASS_ORDER, GIF_CENSUS_BLOCKS, UNREFERENCED_PROV,
                            IdTable, TableError)


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

    ⚑ Both dialects HAVE a gif-side census now, and they key it differently
    because their games differ.  Both answers are checked BY NAME rather than
    one of them being skipped:

    * **rwia** -- the game loads a level out of a set of shipped ``.gif`` files
      and a custom level is an overwrite of one of them, so ``gif_id_counts``'
      keys ARE the slot list and it must be non-empty.
    * **flash** -- the game embeds exactly one map inside the SWF.  Its census
      lives under ``embedded_map_id_counts``, keyed by the class that carries
      the map, and ``gif_id_counts`` stays empty -- so the overwrite-slot list
      is ``[]`` because there is nothing to overwrite, not because nobody
      counted.  The table's own ``censuses._note`` has to say which and why.
    """
    censuses = any_table.raw["censuses"]
    files = any_table.gif_level_files
    counts = censuses["gif_id_counts"]
    assert files == sorted(k for k in counts if not k.startswith("_"))

    if counts:
        assert all(f.endswith(".gif") for f in files)
        # every named file really was censused, i.e. the list is not decoration
        for name in files:
            assert counts[name]
    else:
        assert files == []
        assert censuses.get("_note"), (
            "%s derives no overwrite slots; which shape its census uses instead "
            "has to be a stated fact, not a silence" % any_table.path)
        embedded = censuses["embedded_map_id_counts"]
        keys = [k for k in embedded if not k.startswith("_")]
        assert keys, (
            "%s has neither a file census nor an embedded-map one; an empty "
            "overwrite-slot list must still be backed by counts" % any_table.path)
        assert embedded.get("_measured"), (
            "%s publishes an embedded-map census with no provenance" % any_table.path)
        for key in keys:
            # a class name, not a level file -- the shapes must not be confusable
            assert not key.endswith(".gif")
            assert embedded[key]


def test_each_packaged_dialect_uses_EXACTLY_ONE_census_shape(any_table):
    """The control that keeps the arm above from passing on two empty blocks.

    Both blocks empty would satisfy "the list equals the file census" trivially,
    and both blocks full would mean the table cannot say which one
    ``gif_level_files`` should believe.  Exactly one, for every dialect, by name.
    """
    censuses = any_table.raw["censuses"]
    used = [b for b in GIF_CENSUS_BLOCKS
            if [k for k in (censuses.get(b) or {}) if not k.startswith("_")]]
    assert used == [any_table.gif_census_block]
    assert len(used) == 1, (
        "%s counts its gif ids in %s; a dialect keys its census one way"
        % (any_table.path, used or "no block at all"))


def test_the_two_packaged_DIALECTS_key_their_censuses_DIFFERENTLY(table, flash):
    """...and they are not the same one block, which is the whole point."""
    assert table.gif_census_block == "gif_id_counts"
    assert flash.gif_census_block == "embedded_map_id_counts"
    assert flash.gif_level_files == []
    assert list(flash.gif_census) == ["xplor.PlayState_mapData"]
    counts = flash.gif_census["xplor.PlayState_mapData"]
    # the map is 188 x 84 one byte per cell, so the counts must exhaust it
    assert sum(counts.values()) == 188 * 84


def test_the_unreferenced_ids_are_DERIVED_and_each_line_names_its_own_row(any_table):
    """``gif_unreferenced_ids`` reads provenance; a drifted line is not trusted."""
    derived = any_table.gif_unreferenced_ids
    assert derived == sorted(set(derived))
    for gid in derived:
        assert any(UNREFERENCED_PROV.match(line) for line in any_table.gif_ids[gid]["prov"])
        # unreferenced is not the same distinction as ``observed``
        assert "observed" not in any_table.gif_ids[gid]


def test_an_unreferenced_prov_line_on_the_WRONG_ROW_is_a_table_error(tmp_path, flash):
    """Red-first: the derivation refuses a line that names another id."""
    victim = flash.gif_unreferenced_ids[0]

    def drift(raw):
        prov = raw["gif"]["ids"][str(victim)]["prov"]
        prov[:] = [UNREFERENCED_PROV.sub("no reference to id 9999 anywhere in the Flash sources", p)
                   if UNREFERENCED_PROV.match(p) else p for p in prov]

    drifted = IdTable.load(fixtures.mutant_table(tmp_path, flash, drift))
    with pytest.raises(TableError, match="unreferenced-provenance line of id 9999"):
        drifted.gif_unreferenced_ids
