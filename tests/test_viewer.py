"""``emit-json``: the tileMapAnalyzer's two files, derived from the table.

The panel's own loader (``tileMapDataManager.js``) validates four things and
refuses the file otherwise; those four are the first tests here, spelled the way
that file spells them, so a drift on either side reds on this side.

Everything after them checks the DERIVATION -- that the category, the flag and
the colour of every id come from a measurement in ``id-table.json``/
``palette.json`` and not from a list in the code.  A test that only read the
emitter's own output back would agree with any list, so each of those compares
against the table, and the mutants at the bottom prove the comparison can fail.
"""

import json

import fixtures
import pytest

from kittygif import gifio, viewer
from kittygif.cli import main
from kittygif.table import CLASS_ORDER, GIF, KITTY, IdTable
from kittygif.viewer import CategoryScheme, ViewerTraits


@pytest.fixture
def traits():
    return ViewerTraits.load()


def _emit(tmp_path, level, table, prefix="v"):
    tilemap = str(tmp_path / (prefix + "_tilemap.json"))
    config = str(tmp_path / (prefix + "_tiles.json"))
    viewer.emit(level, table, tilemap, config)
    return json.load(open(tilemap, encoding="utf-8")), json.load(open(config, encoding="utf-8"))


# ─────────────────────────────────────────────── the panel's own four checks
def test_the_tilemap_passes_the_panels_loader(tmp_path, table):
    level = fixtures.l1_gif(table)
    tilemap, _ = _emit(tmp_path, level, table)
    # loadTileMap: tiles must be an array, map_width/map_height numbers.
    assert isinstance(tilemap["tiles"], list)
    assert isinstance(tilemap["map_width"], int)
    assert isinstance(tilemap["map_height"], int)
    # buildCategoryGrid indexes tiles[y][x] over exactly that rectangle.
    assert len(tilemap["tiles"]) == tilemap["map_height"] == level.height
    assert all(len(row) == tilemap["map_width"] == level.width for row in tilemap["tiles"])
    assert [c for row in tilemap["tiles"] for c in row] == level.tiles


def test_the_config_passes_the_panels_loader(tmp_path, table):
    _, config = _emit(tmp_path, fixtures.l1_gif(table), table)
    # loadCategoryConfig: categories and tile_ids must both be objects.
    assert isinstance(config["categories"], dict) and config["categories"]
    assert isinstance(config["tile_ids"], dict) and config["tile_ids"]
    # buildCategoryGrid's fallback.
    assert config["default_category"] in config["categories"]


def test_every_id_the_fixture_uses_resolves_to_a_real_category(tmp_path, table):
    level = fixtures.l1_gif(table)
    tilemap, config = _emit(tmp_path, level, table)
    for row in tilemap["tiles"]:
        for tile in row:
            name = config["tile_ids"].get(str(tile))
            assert name, "id %d has no category, so the panel would draw it %r" % (
                tile, config["default_category"])
            assert name in config["categories"]


def test_no_category_is_named_but_undefined(tmp_path, table):
    _, config = _emit(tmp_path, fixtures.all_layouts_kitty(table), table)
    named = {v for k, v in config["tile_ids"].items() if not k.startswith("_")}
    assert named <= set(config["categories"])
    assert set(config["categories"]) - named == {config["default_category"]}


# ────────────────────────────────────────────────────────── the derivation
@pytest.mark.parametrize("space", [GIF, KITTY])
def test_solid_is_the_tables_measured_solid_for_every_id(table, traits, space):
    config = viewer.category_config(table, space, traits=traits)
    ids = table.gif_ids if space == GIF else table.kitty_ids
    for sid, meta in ids.items():
        cat = config["categories"][config["tile_ids"][str(sid)]]
        assert bool(cat["solid"]) == bool(meta.get("solid")), \
            "%s id %d: the emitted category disagrees with the table" % (space, sid)


@pytest.mark.parametrize("space", [GIF, KITTY])
def test_a_kind_that_is_mixed_on_solid_splits_and_keeps_both(table, traits, space):
    """The one derivation rule that is not a straight copy of ``kind``.

    Found from the table rather than named: a kind whose members disagree about
    ``solid`` cannot be one category without losing the flag the floor
    derivation reads.  (The ``.kitty`` side has two such kinds; the gif side has
    none, which is why this is parametrised over both -- the gif half is a
    negative control that the split does NOT fire where it must not.)
    """
    ids = table.gif_ids if space == GIF else table.kitty_ids
    by_kind = {}
    for meta in ids.values():
        by_kind.setdefault(meta["kind"], set()).add(bool(meta.get("solid")))
    mixed = {k for k, v in by_kind.items() if len(v) > 1}

    config = viewer.category_config(table, space, traits=traits)
    scheme = CategoryScheme(table, space, traits)
    for kind, values in by_kind.items():
        # a spawn-carrying id names its FIELD, which is a second split and not
        # this one -- it is checked by its own test.
        names = {config["tile_ids"][str(sid)]
                 for sid, meta in ids.items()
                 if meta["kind"] == kind and not scheme.position_field_of(sid)}
        if not names:
            continue
        if kind in mixed:
            assert len(names) == len(values) == 2, (kind, names)
            assert {config["categories"][n]["solid"] for n in names} == {True, False}
        else:
            assert len(names) == 1, (kind, names)

    if space == GIF:
        assert not mixed          # negative control: no split to make here
    else:
        assert mixed              # ... and the split really is exercised


def test_a_colour_is_the_palettes_measurement_or_says_it_is_not(table, palette, traits):
    rgb = palette.rgb_by_id
    for space in (GIF, KITTY):
        config = viewer.category_config(table, space, palette=palette, traits=traits)
        for name, cat in config["categories"].items():
            assert len(cat["color"]) == 7 and cat["color"][0] == "#"
            int(cat["color"][1:], 16)
            if "_color_from" in cat:
                gid = int(cat["_color_from"].split("[")[1].rstrip("]"))
                assert cat["color"] == "#%02x%02x%02x" % rgb[gid]


def test_a_substituted_layout_never_borrows_its_substitutes_colour(table, traits):
    """⛔ trap-1022-adjacent: a class-(c) target is chosen for SAFETY.

    ``kitty->gif`` emits the nearest safe tile for an unrepresentable mechanic,
    so that target's colour describes the substitute, not the cell.  Painting a
    solid conveyor in air's colour would delete it from the picture the viewer
    exists to draw, so the emitter must fall back instead.
    """
    scheme = CategoryScheme(table, KITTY, traits)
    substituted = [kid for kid, rule in table.reverse.items()
                   if rule.cls == CLASS_ORDER[-1]]
    assert substituted, "no class-(c) layout ids -- this test would be vacuous"
    for kid in substituted:
        assert scheme.representative_gif_id(kid) is None
    # ... and the same for anything that maps onto air without BEING air.
    to_air = [kid for kid, rule in table.reverse.items()
              if rule.target_ids and rule.target_ids[0] == table.gif_empty
              and kid != table.kitty_empty]
    assert to_air, "nothing maps onto air -- this half would be vacuous"
    for kid in to_air:
        assert scheme.representative_gif_id(kid) is None


def test_the_two_id_spaces_agree_where_the_table_pairs_them(table, palette, traits):
    """The property the side-by-side view depends on.

    A kind that both spaces carry uniformly is ONE word, and a pair the table
    calls faithful gets ONE colour -- so a gif grid and a .kitty grid can be
    read against each other.
    """
    gif_cfg = viewer.category_config(table, GIF, palette=palette, traits=traits)
    kit_cfg = viewer.category_config(table, KITTY, palette=palette, traits=traits)
    shared = set(gif_cfg["categories"]) & set(kit_cfg["categories"])
    assert {"empty", "pickup", "solid_bulk", "door"} <= shared

    agreed = 0
    for kid, rule in table.reverse.items():
        if rule.cls == CLASS_ORDER[-1] or not rule.target_ids:
            continue
        gid = rule.target_ids[0]
        if gid == table.gif_empty and kid != table.kitty_empty:
            continue
        k_name = kit_cfg["tile_ids"][str(kid)]
        g_name = gif_cfg["tile_ids"][str(gid)]
        if k_name in shared and g_name in shared and k_name == g_name:
            assert kit_cfg["categories"][k_name]["color"] == \
                gif_cfg["categories"][g_name]["color"]
            agreed += 1
    assert agreed >= 10, "only %d pairs agreed -- too few to call this a property" % agreed


def test_the_traits_file_covers_every_kind_the_table_names(table, traits):
    assert traits.unknown_kinds(table) == []


def test_the_spawns_are_cells_on_one_side_and_FIELDS_on_the_other(tmp_path, table):
    """A real asymmetry of the two formats, and it must survive the emit.

    A gif carries the robot and the kitty as two PIXELS, so they are cells with
    categories.  A ``.kitty`` carries them as float fields in the file, so no
    cell holds one and the .kitty grid has no marker to draw -- the position has
    to travel as metadata or it is lost.
    """
    gif_map, gif_cfg = _emit(tmp_path, fixtures.l1_gif(table), table, "g")
    starts = [n for n, c in gif_cfg["categories"].items() if c.get("is_player_start")]
    assert len(starts) == 1
    drawn = {gif_cfg["tile_ids"].get(str(t)) for row in gif_map["tiles"] for t in row}
    assert starts[0] in drawn

    kit_map, kit_cfg = _emit(tmp_path, fixtures.all_layouts_kitty(table), table, "k")
    assert not [n for n, c in kit_cfg["categories"].items() if c.get("is_player_start")]
    assert kit_map["robot_tile"] and kit_map["kitty_tile"]


# ──────────────────────────────────────────────────────────────── the CLI
def test_emit_json_reads_either_format(tmp_path, table, palette, capsys):
    gif = str(tmp_path / "src.gif")
    gifio.write(fixtures.l1_gif(table), gif, palette)
    assert main(["emit-json", gif, str(tmp_path / "a"), "--quiet"]) == 0
    assert json.load(open(str(tmp_path / "a_tilemap.json")))["_id_space"] == GIF

    kitty = str(tmp_path / "mid.kitty")
    assert main(["gif2kitty", gif, kitty, "--quiet"]) == 0
    assert main(["emit-json", kitty, str(tmp_path / "b"), "--quiet"]) == 0
    assert json.load(open(str(tmp_path / "b_tilemap.json")))["_id_space"] == KITTY


def test_the_conversion_flag_emits_the_CONVERTED_level(tmp_path, table, palette):
    """``gif2kitty --emit-json`` must describe the output, not the input.

    The two differ in id SPACE and in size-of-vocabulary, so reading the wrong
    end would produce a tilemap whose ids the config cannot name.
    """
    gif = str(tmp_path / "src.gif")
    gifio.write(fixtures.l1_gif(table), gif, palette)
    assert main(["gif2kitty", gif, str(tmp_path / "out.kitty"),
                 "--emit-json", str(tmp_path / "c"), "--quiet"]) == 0
    tilemap = json.load(open(str(tmp_path / "c_tilemap.json")))
    config = json.load(open(str(tmp_path / "c_tiles.json")))
    assert tilemap["_id_space"] == config["_id_space"] == KITTY
    for row in tilemap["tiles"]:
        for tile in row:
            assert str(tile) in config["tile_ids"]


def test_the_two_suffixes_are_the_panels_own(tmp_path, table, palette):
    """⛔ The suffixes are a CONTRACT, not decoration.

    Archipelago-CC gitignores the panel's data by exactly these two globs
    (`*_tilemap.json`, `*_tiles.json`), so a prefix keeps a generated map out of
    a tracked tree by construction.  A rename here silently dirties that tree.
    """
    from kittygif import cli
    assert cli.TILEMAP_SUFFIX == "_tilemap.json"
    assert cli.CONFIG_SUFFIX == "_tiles.json"
    gif = str(tmp_path / "src.gif")
    gifio.write(fixtures.l1_gif(table), gif, palette)
    assert main(["emit-json", gif, str(tmp_path / "pfx"), "--quiet"]) == 0
    assert (tmp_path / "pfx_tilemap.json").exists()
    assert (tmp_path / "pfx_tiles.json").exists()


# ─────────────────────────────────────────────────────────────── mutants
def test_a_kind_mutant_moves_the_emitted_categories(tmp_path, table, traits):
    """The emitter reads the table's ``kind``; prove it by changing one.

    Without this the whole derivation could be a hardcoded list agreeing with
    the table by luck.
    """
    honest = viewer.category_config(table, GIF, traits=traits)
    victim = str(table.gif_empty + 0)

    def mutate(raw):
        raw["gif"]["ids"][victim]["kind"] = "not-a-kind-anyone-measured"

    path = fixtures.mutant_table(tmp_path, table, mutate)
    mutant = viewer.category_config(IdTable.load(path), GIF, traits=traits)
    assert honest["tile_ids"][victim] != mutant["tile_ids"][victim]
    assert mutant["tile_ids"][victim] == "not_a_kind_anyone_measured"


def test_a_solid_mutant_moves_the_emitted_flag(tmp_path, table, traits):
    honest = viewer.category_config(table, GIF, traits=traits)
    victim = str(table.gif_empty)
    assert honest["categories"][honest["tile_ids"][victim]]["solid"] is False

    def mutate(raw):
        raw["gif"]["ids"][victim]["solid"] = True

    path = fixtures.mutant_table(tmp_path, table, mutate)
    mutant = viewer.category_config(IdTable.load(path), GIF, traits=traits)
    assert mutant["categories"][mutant["tile_ids"][victim]]["solid"] is True


def test_a_traits_mutant_moves_the_emitted_flags(tmp_path, table):
    """The traits file is DATA too, and ``--viewer-traits`` re-points it."""
    honest = viewer.category_config(table, KITTY)
    lethal = [n for n, c in honest["categories"].items() if c.get("lethal")]
    assert lethal, "no lethal category -- the mutant would be vacuous"

    raw = json.loads(json.dumps(ViewerTraits.load().raw))
    for kind in raw["kind_traits"]:
        raw["kind_traits"][kind].pop("lethal", None)
    path = str(tmp_path / "mutant-viewer-traits.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)

    mutant = viewer.category_config(table, KITTY, traits=ViewerTraits.load(path))
    assert not [n for n, c in mutant["categories"].items() if c.get("lethal")]
    # ... and nothing else moved: the DERIVED half is untouched by the traits.
    assert set(mutant["categories"]) == set(honest["categories"])
    assert mutant["tile_ids"] == honest["tile_ids"]


def test_the_fixtures_discriminate(table):
    """A negative control for every assertion above that walks a fixture."""
    gif = fixtures.l1_gif(table)
    scheme = CategoryScheme(table, GIF, ViewerTraits.load())
    used = {scheme.category_of(t) for t in set(gif.tiles)}
    assert len(used) >= 5, "the gif fixture spans %d categories" % len(used)
    kit = fixtures.all_layouts_kitty(table)
    kscheme = CategoryScheme(table, KITTY, ViewerTraits.load())
    kused = {kscheme.category_of(t) for t in set(kit.tiles)}
    assert len(kused) >= 8, "the kitty fixture spans %d categories" % len(kused)
    assert {"mechanism_solid", "mechanism_open"} <= kused
