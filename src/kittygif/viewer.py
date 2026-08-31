"""Emit the tileMapAnalyzer's two JSON files from a :class:`Level`.

The viewer's contract lives in Archipelago-CC's
``frontend/modules/tileMapAnalyzer/tileMapDataManager.js``:

* a **tilemap** ``{tiles: [[id, ...] one list per ROW], map_width, map_height}``
* a **category config** ``{categories: {name: {...}}, tile_ids: {"<id>": name},
  default_category}``

and the consumers of the config's per-category flags are
``tileCategorizer.deriveFloorFlags`` (``solid`` / ``lethal`` / ``blocks_floor``)
and ``reachabilityAnalyzer`` (``is_region`` / ``is_location`` /
``is_player_start``).

**Nothing here names a tile id, a category or a colour.**  A category is
DERIVED from the id table's own measured per-id fields, and a colour from
``palette.json``:

``category name``
    the id's measured ``kind``.  A kind whose members disagree about ``solid``
    (the ``.kitty`` side's ``hazard`` and ``mechanism`` both do) would lose that
    distinction in one bucket, so such a kind SPLITS into ``<kind>_solid`` and
    ``<kind>_open``.  A uniform kind keeps its bare name, which is what makes
    the two id spaces comparable: ``pickup`` in a ``.gif`` grid and ``pickup``
    in a ``.kitty`` grid are the same word and the same colour.
``solid``
    the id's measured ``solid`` field (from each space's own ``solid_rule``).
``colour``
    the canonical RGB of the category's REPRESENTATIVE GIF ID -- itself for a
    gif id, and for a layout id the gif id its ``kitty->gif`` rule targets.  So
    the two spaces agree on colour wherever the table pairs them, which is the
    whole point of putting them side by side.  An id the palette never measured
    falls back to a colour derived from the category name.

Only the handful of viewer flags that cannot be derived from a measurement --
"is this kind lethal to touch", "does it block the floor", "is it a spawn" --
come from DATA, ``data/viewer-traits.json``, keyed on the table's own ``kind``
vocabulary (about twenty rows, against a hundred and thirty ids).  Point
``--viewer-traits`` at another copy to convert by another one, exactly as
``--id-table`` does for the table.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

from .level import Level
from .table import CLASS_ORDER, DATA_DIR, GIF, KITTY, IdTable, Palette

TRAITS_ENV = "KITTYGIF_VIEWER_TRAITS"

#: appended to a kind that is not uniform on ``solid``; see the module docstring.
SPLIT_SUFFIX = {True: "_solid", False: "_open"}


class ViewerTraits:
    """The small per-KIND flag table the viewer needs and no measurement gives."""

    def __init__(self, raw: dict, path: str) -> None:
        self.raw, self.path = raw, path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "ViewerTraits":
        path = path or os.environ.get(TRAITS_ENV) or os.path.join(
            DATA_DIR, "viewer-traits.json")
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh), path)

    @property
    def kinds(self) -> Dict[str, dict]:
        return self.raw["kind_traits"]

    @property
    def position_fields(self) -> Dict[str, dict]:
        return self.raw["position_field_traits"]

    @property
    def default_category(self) -> str:
        return self.raw["default_category"]

    def of_kind(self, kind: str) -> dict:
        return dict(self.kinds.get(kind, {}))

    def unknown_kinds(self, table: IdTable) -> List[str]:
        """Kinds the table carries that this file says nothing about."""
        seen = set()
        for ids in (table.gif_ids, table.kitty_ids):
            seen.update(meta.get("kind") for meta in ids.values())
        return sorted(k for k in seen if k and k not in self.kinds)


def slug(text: str) -> str:
    return text.replace("-", "_").replace(" ", "_")


def _mixed_kinds(ids: Dict[int, dict]) -> Dict[str, bool]:
    """Which kinds in one id space disagree about ``solid``."""
    seen: Dict[str, set] = {}
    for meta in ids.values():
        seen.setdefault(meta["kind"], set()).add(bool(meta.get("solid")))
    return {kind: len(vals) > 1 for kind, vals in seen.items()}


def _fallback_colour(name: str) -> str:
    """A stable colour for a category the palette never measured.

    Derived from the name so two runs (and the two id spaces) agree, and pushed
    into the light half of the wheel so it can never be confused with air.
    """
    h = 0
    for ch in name:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return "#%02x%02x%02x" % (0x60 + (h & 0x7F),
                              0x60 + ((h >> 8) & 0x7F),
                              0x60 + ((h >> 16) & 0x7F))


class CategoryScheme:
    """The derived id -> category assignment for ONE id space."""

    def __init__(self, table: IdTable, space: str, traits: ViewerTraits) -> None:
        self.table, self.space, self.traits = table, space, traits
        self.ids = table.gif_ids if space == GIF else table.kitty_ids
        self._mixed = _mixed_kinds(self.ids)

    # -------------------------------------------------------------- one id
    def position_field_of(self, sid: int) -> Optional[str]:
        """The spawn FIELD this id carries, if it carries one.

        Only the gif side can: on the ``.kitty`` side a spawn is a file field
        and no grid cell ever holds one, so a ``.kitty`` tilemap simply has no
        robot or kitty marker to draw.
        """
        if self.space != GIF:
            return None
        rule = self.table.forward.get(sid)
        return rule.position_field if rule else None

    def category_of(self, sid: int) -> Optional[str]:
        meta = self.ids.get(sid)
        if meta is None:
            return None
        field = self.position_field_of(sid)
        if field:
            return "%s_%s" % (slug(meta["kind"]), slug(field))
        kind = meta["kind"]
        if self._mixed.get(kind):
            return slug(kind) + SPLIT_SUFFIX[bool(meta.get("solid"))]
        return slug(kind)

    def representative_gif_id(self, sid: int) -> Optional[int]:
        """The gif id whose measured RGB stands for this id.

        ⛔ NOT the target of a LAST-CLASS rule.  The class tags are ordered
        most-faithful-first (``table.CLASS_ORDER``) and the last one means
        "unrepresentable, emitted as the nearest SAFE tile" -- a substitution
        chosen for safety, not for appearance.  Borrowing its colour would paint
        a solid conveyor in air's colour and hide it in the very picture the
        viewer exists to show, so those categories take the derived fallback and
        stay visible instead.
        """
        if self.space == GIF:
            return sid
        rule = self.table.reverse.get(sid)
        if rule is None or not rule.target_ids or rule.cls == CLASS_ORDER[-1]:
            return None
        rep = rule.target_ids[0]
        # ⛔ Nor the EMPTY id, for a cell that is not itself empty: "maps to air"
        # says this id has no gif appearance, and air's colour is the ground the
        # panel paints first -- so borrowing it would erase the cell from the
        # picture.  A .kitty music trigger is invisible IN GAME; it is not
        # invisible in a viewer whose job is to show what the file contains.
        if rep == self.table.gif_empty and sid != self.table.kitty_empty:
            return None
        return rep

    # ------------------------------------------------------------ the whole
    def build(self, palette: Palette) -> Tuple[Dict[str, dict], Dict[str, str]]:
        rgb = palette.rgb_by_id
        categories: Dict[str, dict] = {}
        tile_ids: Dict[str, str] = {}
        reps: Dict[str, int] = {}

        for sid in sorted(self.ids):
            meta = self.ids[sid]
            name = self.category_of(sid)
            tile_ids[str(sid)] = name
            cat = categories.setdefault(name, {
                "_ids": [],
                "_names": [],
                "walkable": True,
                "solid": False,
            })
            cat["_ids"].append(sid)
            cat["_names"].append(meta["name"])
            if meta.get("solid"):
                cat["solid"] = True
                cat["walkable"] = False
            rep = self.representative_gif_id(sid)
            if rep is not None and rep in rgb and name not in reps:
                reps[name] = rep

        for name, cat in categories.items():
            kind = self.ids[cat["_ids"][0]]["kind"]
            cat.update(self.traits.of_kind(kind))
            field = self.position_field_of(cat["_ids"][0])
            if field:
                cat.update(self.traits.position_fields.get(field, {}))
            rep = reps.get(name)
            cat["color"] = ("#%02x%02x%02x" % rgb[rep]) if rep is not None \
                else _fallback_colour(name)
            cat["_doc"] = "%s ids %s: %s" % (
                self.space,
                ", ".join(str(i) for i in cat.pop("_ids")),
                "; ".join(cat.pop("_names")),
            )
            if rep is not None:
                cat["_color_from"] = "palette.json canonical_rgb[%d]" % rep

        default = self.traits.default_category
        categories.setdefault(default, {
            "_doc": "an id no measurement in the table covers",
            "color": _fallback_colour(default),
            "walkable": True,
            "solid": False,
        })
        return categories, tile_ids


def category_config(table: IdTable, space: str, palette: Optional[Palette] = None,
                    traits: Optional[ViewerTraits] = None,
                    game: Optional[str] = None) -> dict:
    """The ``*_tiles.json`` half of the viewer's input, for one id space."""
    palette = palette or Palette.load()
    traits = traits or ViewerTraits.load()
    scheme = CategoryScheme(table, space, traits)
    categories, tile_ids = scheme.build(palette)
    tile_ids["_doc"] = ("raw tile id -> category name, DERIVED from "
                        "id-table.json's per-id 'kind' and 'solid'")
    return {
        "_doc": __doc__.strip().splitlines()[0],
        "_generated_by": "kittygif emit-json",
        "_id_space": space,
        "_id_table": table.path,
        "_palette": palette.path,
        "_viewer_traits": traits.path,
        "game": game or ("RWIA level gif (%s id space)" % space),
        "tile_size": table.tile_size_px,
        "categories": categories,
        "tile_ids": tile_ids,
        "default_category": traits.default_category,
    }


def tilemap_json(level: Level, table: IdTable, source: Optional[str] = None) -> dict:
    """The ``*_tilemap.json`` half: the grid as one list per ROW."""
    rows = [level.tiles[y * level.width:(y + 1) * level.width]
            for y in range(level.height)]
    out = {
        "game": level.name or "(unnamed)",
        "_generated_by": "kittygif emit-json",
        "_id_space": level.space,
        "_source": source,
        "map_width": level.width,
        "map_height": level.height,
        "tiles": rows,
    }
    # A .kitty carries its spawns as FILE FIELDS, not as cells, so they cannot
    # appear in the grid; a gif carries them as two pixels and they do.  Either
    # way the measured tile position travels with the tilemap.
    for field, value in (("robot", level.robot), ("kitty", level.kitty)):
        if value is not None:
            out["%s_tile" % field] = list(value)
    if level.paint_id is not None:
        out["_painted_cells"] = sum(1 for p in level.paint_id if p)
    return out


def emit(level: Level, table: IdTable, tilemap_path: str, config_path: str,
         palette: Optional[Palette] = None, traits: Optional[ViewerTraits] = None,
         source: Optional[str] = None) -> dict:
    """Write both files; return a small summary of what was written."""
    tilemap = tilemap_json(level, table, source=source)
    config = category_config(table, level.space, palette=palette, traits=traits,
                             game=tilemap["game"])
    for path, payload in ((tilemap_path, tilemap), (config_path, config)):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1)
            fh.write("\n")
    used = sorted(set(level.tiles))
    unknown = [i for i in used if str(i) not in config["tile_ids"]]
    return {
        "tilemap": tilemap_path,
        "config": config_path,
        "space": level.space,
        "grid": [level.width, level.height],
        "distinct_ids": len(used),
        "categories": len(config["categories"]),
        "ids_without_a_category": unknown,
    }
