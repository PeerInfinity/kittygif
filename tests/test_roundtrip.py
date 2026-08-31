"""L1 -- round-trip byte identity on the grid, over the mappable subset.

This is the automatable core gate: a gif whose ids are all mappable must come
back byte-identical after ``gif -> .kitty -> gif``, through real files.
"""

import fixtures
from kittygif import gifio, kittyio
from kittygif.convert import gif_to_kitty, kitty_to_gif


def _l1_files(tmp_path, table, level, palette, **kwargs):
    src = str(tmp_path / "src.gif")
    mid = str(tmp_path / "mid.kitty")
    dst = str(tmp_path / "dst.gif")
    gifio.write(level, src, palette)

    kitty_level, forward = gif_to_kitty(gifio.read(src), table, name="L1", **kwargs)
    kittyio.write(kitty_level, mid, table)
    back, reverse = kitty_to_gif(kittyio.read(mid, table), table)
    gifio.write(back, dst, palette)
    return src, mid, dst, forward, reverse


def test_l1_grid_is_byte_identical(tmp_path, table, palette):
    level = fixtures.l1_gif(table)
    src, _mid, dst, forward, reverse = _l1_files(tmp_path, table, level, palette)

    assert gifio.read(dst).tiles == gifio.read(src).tiles
    assert open(src, "rb").read() == open(dst, "rb").read(), "the whole gif, not just the grid"
    assert forward.counts()["b"] == forward.counts()["c"] == 0
    assert reverse.counts()["c"] == 0
    assert not forward.solvability_at_risk and not reverse.solvability_at_risk


def test_l1_holds_with_the_terrain_unpainted(tmp_path, table, palette):
    """Paint is cosmetic: turning it off must not move a single layout id."""
    level = fixtures.l1_gif(table)
    src, _mid, dst, _f, _r = _l1_files(tmp_path, table, level, palette, paint=False)
    assert open(src, "rb").read() == open(dst, "rb").read()


def test_spawns_survive_the_round_trip(tmp_path, table, palette):
    level = fixtures.l1_gif(table)
    _src, mid, _dst, _f, _r = _l1_files(tmp_path, table, level, palette)
    written = kittyio.read(mid, table)
    robot_id = table.position_source_gif_id("robot_xy")
    kitty_id = table.position_source_gif_id("kitty_xy")
    (rx, ry) = next((x, y) for x, y, t in level.cells() if t == robot_id)
    (kx, ky) = next((x, y) for x, y, t in level.cells() if t == kitty_id)
    assert written.robot == (float(rx), float(ry))
    assert written.kitty == (float(kx), float(ky))


def test_unmappable_ids_do_NOT_round_trip(tmp_path, table, palette):
    """The negative control: L1 would be vacuous if everything came back identical.

    Every class-(b)/(c) gif id is degraded on purpose, so at least one cell MUST
    differ -- otherwise the gate above is proving nothing about the table.
    """
    level = fixtures.unmappable_gif(table)
    src, _mid, dst, forward, _r = _l1_files(tmp_path, table, level, palette)
    assert gifio.read(dst).tiles != gifio.read(src).tiles
    assert forward.counts()["b"] + forward.counts()["c"] > 0


def test_gate_runs_pair_bottom_up(tmp_path, table, palette):
    """A run of N gate cells becomes couples from the bottom, odd cell on top."""
    gate = next(g for g, r in table.forward.items() if r.shape == "vpair")
    top_id, bottom_id = table.forward[gate].target_ids
    level = fixtures.gif_grid(table, [gate], runs={gate: [1, 2, 3, 4]})
    converted, _report = gif_to_kitty(level, table, name="GATES")

    columns = {}
    for x, y, tile in level.cells():
        if tile == gate:
            columns.setdefault(x, []).append(y)
    assert columns, "the fixture must actually contain gate cells"
    for x, ys in columns.items():
        ys = sorted(ys)
        got = [converted.at(x, y) for y in ys]
        expected = []
        for offset in range(len(ys)):
            from_bottom = len(ys) - 1 - offset
            expected.append(bottom_id if from_bottom % 2 == 0 else top_id)
        if len(ys) % 2:
            expected[0] = top_id
        assert got == expected, "run of %d at x=%d" % (len(ys), x)
        # every couple is adjacent and the right way up
        for i in range(len(got) - 1):
            if got[i] == top_id and got[i + 1] == bottom_id:
                break
        else:
            assert len(ys) == 1, "a run taller than one cell must contain a couple"
