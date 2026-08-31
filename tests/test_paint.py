"""The 47-blob autotiler and the paint plane."""

import pytest

import fixtures
from kittygif.level import Level
from kittygif.paint import autopaint, blob_index
from kittygif.table import KITTY


def _same(neighbours):
    """Build a predicate from a set of (dx,dy) offsets."""
    return lambda dx, dy: (dx, dy) in neighbours


def test_an_isolated_cell_is_the_lone_tile():
    assert blob_index(_same(set())) == 44


def test_a_fully_surrounded_cell_is_the_interior_tile():
    everything = {(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)}
    assert blob_index(_same(everything)) == 43


def test_a_horizontal_run_reads_left_middle_right():
    assert blob_index(_same({(1, 0)})) == 1              # only an east neighbour
    assert blob_index(_same({(-1, 0), (1, 0)})) == 46    # both
    assert blob_index(_same({(-1, 0)})) == 3             # only a west neighbour


def test_a_vertical_run_reads_top_middle_bottom():
    assert blob_index(_same({(0, 1)})) == 2
    assert blob_index(_same({(0, -1), (0, 1)})) == 45
    assert blob_index(_same({(0, -1)})) == 0


def test_the_reachable_blob_set_is_the_editor_s_own():
    """46 of the 47 tiles, and blob 32 is the editor's own gap -- not ours.

    ``WorldEditor::GetTileMatch47`` has no ``aResultTile=32`` branch at all, so
    the shipped painter cannot emit that tile.  Corroborated on the other side:
    blob 32 occurs zero times across all eleven campaign levels.  Anything else
    missing here WOULD be a transcription defect.
    """
    seen = set()
    offsets = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
    for mask in range(256):
        neighbours = {offsets[i] for i in range(8) if mask & (1 << i)}
        seen.add(blob_index(_same(neighbours)))
    assert seen == set(range(47)) - {32}, \
        "unreachable blob tiles: %s" % sorted(set(range(47)) - {32} - seen)


def test_the_blob_only_depends_on_the_eight_neighbours():
    offsets = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
    for mask in range(256):
        neighbours = {offsets[i] for i in range(8) if mask & (1 << i)}
        with_self = neighbours | {(0, 0)}
        assert blob_index(_same(neighbours)) == blob_index(_same(with_self))


def test_autopaint_paints_exactly_the_paintable_layouts(table):
    layouts = sorted(table.reverse)
    level = fixtures.kitty_level(table, layouts)
    painted = autopaint(level, table)

    paintable = set(table.paintable_layouts)
    expected = sum(1 for t in level.tiles if t in paintable)
    assert painted == expected and painted > 0
    for i, tile in enumerate(level.tiles):
        assert bool(level.paint_id[i]) == (tile in paintable)


def test_autopaint_stays_inside_the_style_range(table):
    level = fixtures.kitty_level(table, sorted(table.reverse))
    autopaint(level, table)
    low, high = table.paint["style_paint_ranges"][table.default_paint_style][:2]
    for pid, paint in zip(level.paint_id, level.paint):
        if pid:
            assert low <= paint <= high


def test_a_named_style_moves_the_paint_values(table):
    styles = table.paint_styles
    other = next(s for s in styles if s != table.default_paint_style)
    a = fixtures.kitty_level(table, sorted(table.reverse))
    b = fixtures.kitty_level(table, sorted(table.reverse))
    autopaint(a, table)
    autopaint(b, table, style=other)
    assert a.paint != b.paint
    assert [p % 47 for p in a.paint] == [p % 47 for p in b.paint], "same blobs, different base"


def test_an_unknown_style_is_refused(table):
    from kittygif.table import TableError

    level = fixtures.kitty_level(table, sorted(table.reverse))
    with pytest.raises(TableError, match="unknown paint style"):
        autopaint(level, table, style="not-a-style")


def test_region_zero_is_refused_because_it_means_unpainted(table):
    """A cell draws its paint only when paintID != 0 (World::GetDisplayTile)."""
    level = fixtures.kitty_level(table, sorted(table.reverse))
    with pytest.raises(ValueError, match="unpainted"):
        autopaint(level, table, region_id=0)


def test_the_border_of_the_grid_counts_as_a_different_material(table):
    """Out of bounds is NOT the same region -- the map edge gets edge tiles."""
    solid = table.paintable_layouts[0]
    level = Level(space=KITTY, width=3, height=1, tiles=[solid] * 3,
                  robot=(0.0, 0.0), kitty=(0.0, 0.0))
    autopaint(level, table)
    base = table.paint_base(table.default_paint_style)
    assert [p - base for p in level.paint] == [1, 46, 3]
