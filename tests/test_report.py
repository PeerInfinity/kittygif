"""The report is the deliverable for everything the grid cannot carry.

Emit-with-report is the ruling: neither direction ever refuses a file, so the
report is the ONLY place a caller learns that a level was degraded -- and the
only place they learn that its solvability may have moved.
"""

import fixtures
from kittygif.convert import gif_to_kitty, kitty_to_gif


def _entry(report, source_id):
    return next((e for e in report.entries if e.source_id == source_id), None)


def test_gif_to_kitty_reports_the_two_unrepresentable_kinds(table):
    """RWIA added water and the Shooter; neither has a C++ target."""
    unrepresentable = sorted(
        gid for gid, rule in table.forward.items() if rule.cls == "c"
    )
    assert unrepresentable, "the table must name the gif->kitty class-(c) kinds"

    level = fixtures.unmappable_gif(table)
    _out, report = gif_to_kitty(level, table, name="DEGRADE")

    for gid in unrepresentable:
        entry = _entry(report, gid)
        assert entry is not None and entry.cls == "c"
        assert entry.count == 1 and entry.coords
        assert entry.target_id == table.kitty_empty
    assert report.solvability_at_risk
    assert "SOLVABILITY MAY HAVE CHANGED" in report.to_text()


def test_gif_to_kitty_reports_cosmetic_degrades_separately(table):
    level = fixtures.unmappable_gif(table)
    _out, report = gif_to_kitty(level, table, name="DEGRADE")
    degraded = [e for e in report.entries if e.cls == "b"]
    assert degraded
    for entry in degraded:
        assert entry.count and entry.coords and entry.source_name


def test_kitty_to_gif_reports_every_cpp_only_mechanic(table):
    level = fixtures.all_layouts_kitty(table)
    _out, report = kitty_to_gif(level, table)

    expected = {kid for kid, rule in table.reverse.items() if rule.cls == "c"}
    reported = {e.source_id for e in report.entries if e.cls == "c"}
    assert reported == expected
    assert report.solvability_at_risk


def test_substitutes_come_from_the_table_not_from_the_code(table):
    """Every class-(c) substitute is whatever the table's row says it is."""
    level = fixtures.all_layouts_kitty(table)
    out, report = kitty_to_gif(level, table)
    for entry in report.entries:
        rule = table.reverse[entry.source_id]
        assert rule.target_ids is not None
        assert entry.target_id == rule.target_ids[0]
        for x, y in entry.coords:
            assert out.at(x, y) in (entry.target_id, table.position_source_gif_id("robot_xy"),
                                    table.position_source_gif_id("kitty_xy"))


def test_report_json_is_machine_readable_and_carries_coordinates(table):
    level = fixtures.all_layouts_kitty(table)
    _out, report = kitty_to_gif(level, table)
    payload = report.to_json()

    assert payload["direction"] == "kitty->gif"
    assert payload["solvability_at_risk"] is True
    assert payload["grid"] == {"width": level.width, "height": level.height}
    assert payload["cells"]["total"] == level.width * level.height
    total = sum(payload["cells"]["by_class"].values())
    assert total == level.width * level.height
    for entry in payload["entries"]:
        assert entry["class"] in ("a", "b", "c")
        assert len(entry["coords"]) == entry["count"]
        for x, y in entry["coords"]:
            assert 0 <= x < level.width and 0 <= y < level.height
    # class-(c) entries carry the per-kind counts and coords the ruling asks for
    cs = [e for e in payload["entries"] if e["class"] == "c"]
    assert cs and all(e["count"] and e["coords"] and e["note"] for e in cs)


def test_paint_loss_is_reported_as_cosmetic(table):
    level = fixtures.all_layouts_kitty(table)
    level.paint_id = [1] * len(level.tiles)
    level.paint = [table.paint_base(table.default_paint_style)] * len(level.tiles)
    _out, report = kitty_to_gif(level, table)
    assert any("paint" in note and "Cosmetic" in note for note in report.notes)


def test_gate_shape_degradation_is_reported(table):
    gate = next(g for g, r in table.forward.items() if r.shape == "vpair")
    level = fixtures.gif_grid(table, [gate], runs={gate: [3]})
    _out, report = gif_to_kitty(level, table, name="ODD")
    assert any("gate shape" in note for note in report.notes)


def test_an_even_gate_run_is_not_reported_as_a_shape_change(table):
    gate = next(g for g, r in table.forward.items() if r.shape == "vpair")
    level = fixtures.gif_grid(table, [gate], runs={gate: [2, 4]})
    _out, report = gif_to_kitty(level, table, name="EVEN")
    assert not any("gate shape" in note for note in report.notes)
