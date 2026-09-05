"""The id table, loaded as DATA.

Nothing in this module (or anywhere else in the package) knows a tile id, a class
tag, a palette byte or a default.  Every one of those comes out of
``data/id-table.json`` and ``data/palette.json``; this module only knows their
*shape*.  Point ``KITTYGIF_ID_TABLE`` (or ``--id-table``) at another copy and the
converter converts by that copy -- which is how the mutant gates work.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Union

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ID_TABLE_ENV = "KITTYGIF_ID_TABLE"
PALETTE_ENV = "KITTYGIF_PALETTE"

#: The packaged DIALECTS: which id table interprets a level's cells.
#:
#: A dialect is not a container.  The same id space arrives either as an indexed
#: gif's palette indices or as one raw byte per cell (``rawio``), and the same
#: cell numbers mean different things to the two engines that read them -- so
#: which FILE is read and which TABLE reads it are two separate choices.  Adding
#: a dialect is adding a table and a row here; it is not a change to the
#: converter (see the README's "Everything id-shaped is DATA").
#:
#: ⛔ This mapping is a lookup of shipped file NAMES, not a place for id facts.
DIALECTS = {
    "rwia": "id-table.json",
    "flash": "id-table-flash.json",
}

#: what ``--dialect`` means when nobody says: the table this package always had.
DEFAULT_DIALECT = "rwia"

#: The two ends of the translation, named the way the table names them.
GIF = "gif"
KITTY = "kitty"

#: Direction tags as the table spells them.
GIF_TO_KITTY = "gif->kitty"
KITTY_TO_GIF = "kitty->gif"
BOTH = "both"

#: Class tags, most-faithful first.  A source id carried by several rows resolves
#: to the row with the best class (see ``_pick``); ties are a table defect.
CLASS_ORDER = ("a", "b", "c")


class TableError(ValueError):
    """The table is internally inconsistent -- a defect in the DATA, not the code."""


@dataclass(frozen=True)
class Rule:
    """One resolved source-id -> target rule, in one direction."""

    direction: str
    source_id: int
    source_name: str
    #: ``None`` for a position field (the robot/kitty spawn); otherwise one target
    #: id, or several when the row carries a ``shape``.
    target_ids: Optional[Tuple[int, ...]]
    target_name: str
    cls: str
    note: str
    shape: Optional[str] = None
    #: set for the rows whose kitty end is a position FIELD rather than a cell
    position_field: Optional[str] = None

    @property
    def target_id(self) -> int:
        if self.target_ids is None or len(self.target_ids) != 1:
            raise TableError(
                "rule %s %s has %r targets, not one"
                % (self.direction, self.source_id, self.target_ids)
            )
        return self.target_ids[0]


@dataclass
class IdTable:
    raw: dict
    path: str

    gif_ids: Dict[int, dict] = field(default_factory=dict)
    kitty_ids: Dict[int, dict] = field(default_factory=dict)
    position_fields: Dict[str, dict] = field(default_factory=dict)
    forward: Dict[int, Rule] = field(default_factory=dict)   # gif id -> rule
    reverse: Dict[int, Rule] = field(default_factory=dict)   # kitty id -> rule
    position_rules: Dict[str, Rule] = field(default_factory=dict)  # field name -> rule

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, path: Optional[str] = None,
             dialect: Optional[str] = None) -> "IdTable":
        """Resolve the table to read, in that order of precedence.

        An explicit ``path`` wins, then ``$KITTYGIF_ID_TABLE``, then the named
        ``dialect``'s packaged file.  ⛔ That order is load-bearing and not a
        preference: ``--id-table`` is the seam every mutant gate in the suite
        runs through (a mutated COPY, driven through the real code path), so a
        dialect flag that outranked it would quietly take the gates away.
        """
        path = (path or os.environ.get(ID_TABLE_ENV)
                or os.path.join(DATA_DIR, dialect_file(dialect)))
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        table = cls(raw=raw, path=path)
        table._build()
        return table

    def _build(self) -> None:
        for key, target in ((GIF, self.gif_ids), (KITTY, self.kitty_ids)):
            for sid, meta in self.raw[key]["ids"].items():
                try:
                    target[int(sid)] = meta
                except ValueError:            # the two kitty POSITION fields
                    self.position_fields[sid] = meta

        fwd: Dict[int, List[Rule]] = {}
        rev: Dict[int, List[Rule]] = {}
        for row in self.raw["pairs"]:
            for rule in self._rules_of(row):
                if rule.direction == KITTY_TO_GIF and rule.position_field:
                    # A spawn is a FIELD on the .kitty side, not a cell: it is not
                    # reachable by layout id, so it is not in the reverse cell map.
                    self.position_rules[rule.position_field] = rule
                    continue
                (fwd if rule.direction == GIF_TO_KITTY else rev).setdefault(
                    rule.source_id, []
                ).append(rule)
        self.forward = {sid: _pick(sid, rules) for sid, rules in fwd.items()}
        self.reverse = {sid: _pick(sid, rules) for sid, rules in rev.items()}

    def _rules_of(self, row: dict) -> List[Rule]:
        cls, note, shape = row["cls"], row.get("note", ""), row.get("shape")
        if cls not in CLASS_ORDER:
            raise TableError("pair %r carries unknown class %r" % (row, cls))
        directions = row["directions"]
        if directions not in (BOTH, GIF_TO_KITTY, KITTY_TO_GIF):
            raise TableError("pair %r carries unknown directions %r" % (row, directions))

        gif_ids = _as_ids(row["gif"])
        kitty_end = row["kitty"]
        position: Optional[str] = kitty_end if isinstance(kitty_end, str) else None
        kitty_ids: Tuple[int, ...] = () if isinstance(kitty_end, str) else _as_ids(kitty_end)

        out: List[Rule] = []
        if directions in (BOTH, GIF_TO_KITTY):
            for gid in gif_ids:
                out.append(
                    Rule(
                        direction=GIF_TO_KITTY,
                        source_id=gid,
                        source_name=self.gif_name(gid),
                        target_ids=None if position else kitty_ids,
                        target_name=(
                            self.position_fields[position]["name"]
                            if position
                            else " / ".join(self.kitty_name(k) for k in kitty_ids)
                        ),
                        cls=cls,
                        note=note,
                        shape=shape,
                        position_field=position,
                    )
                )
        if directions in (BOTH, KITTY_TO_GIF):
            if position:
                out.append(
                    Rule(
                        direction=KITTY_TO_GIF,
                        source_id=-1,
                        source_name=self.position_fields[position]["name"],
                        target_ids=tuple(gif_ids),
                        target_name=" / ".join(self.gif_name(g) for g in gif_ids),
                        cls=cls,
                        note=note,
                        shape=shape,
                        position_field=position,
                    )
                )
            else:
                for kid in kitty_ids:
                    out.append(
                        Rule(
                            direction=KITTY_TO_GIF,
                            source_id=kid,
                            source_name=self.kitty_name(kid),
                            target_ids=tuple(gif_ids),
                            target_name=" / ".join(self.gif_name(g) for g in gif_ids),
                            cls=cls,
                            note=note,
                            shape=shape,
                        )
                    )
        return out

    # -------------------------------------------------------------- refusals
    def refusal(self, gid: int) -> Optional[str]:
        """Why this dialect REFUSES to read gif id ``gid``, or ``None``.

        A refusal is a table FACT, not a code branch: some id in some dialect is
        dangerous to translate rather than merely lossy, and the honest answer is
        to stop and say which line says so.  The distinction from an unknown id
        matters -- an unknown id is a GAP in the table, a refused one is a
        DECISION in it -- and the two get different messages.

        ⛔ A refused id may not appear in any pair row, in EITHER direction; a
        reverse row targeting one would emit the hazard rather than read it.
        ``check()`` enforces that.
        """
        meta = self.gif_ids.get(gid)
        return meta.get("refuse") if meta else None

    @property
    def refused_gif_ids(self) -> Tuple[int, ...]:
        return tuple(sorted(i for i, meta in self.gif_ids.items() if meta.get("refuse")))

    # ------------------------------------------------------------- named lookups
    @property
    def dialect(self) -> Optional[str]:
        """Which dialect this FILE says it is, or ``None`` if it does not say.

        Informational: the loader never branches on it.  It exists so a table
        reached by ``--id-table`` can be identified in a report, and so the two
        packaged files can be asserted to be the ones their names claim.
        """
        return self.raw.get("_dialect")

    def gif_name(self, gid: int) -> str:
        meta = self.gif_ids.get(gid)
        return meta["name"] if meta else "gif id %d (not in the table)" % gid

    def kitty_name(self, kid: int) -> str:
        meta = self.kitty_ids.get(kid)
        return meta["name"] if meta else "layout id %d (not in the table)" % kid

    def _sole_id(self, space: str, kind: str) -> int:
        ids = self.gif_ids if space == GIF else self.kitty_ids
        found = [i for i, meta in ids.items() if meta.get("kind") == kind]
        if len(found) != 1:
            raise TableError(
                "expected exactly one %s id of kind %r, found %r" % (space, kind, found)
            )
        return found[0]

    @property
    def gif_empty(self) -> int:
        return self._sole_id(GIF, "empty")

    @property
    def kitty_empty(self) -> int:
        return self._sole_id(KITTY, "empty")

    def position_source_gif_id(self, field_name: str) -> int:
        """The gif id that carries a spawn position (e.g. ``robot_xy`` -> 255)."""
        for row in self.raw["pairs"]:
            if row["kitty"] == field_name:
                ids = _as_ids(row["gif"])
                if len(ids) != 1:
                    raise TableError("position row %r must name one gif id" % row)
                return ids[0]
        raise TableError("no pair row carries the position field %r" % field_name)

    @property
    def position_field_names(self) -> Tuple[str, ...]:
        # World::Sync order: robot chunk then kitty chunk (kitty_file.children).
        return tuple(self.position_fields)

    # ------------------------------------------------------------ container facts
    @property
    def container(self) -> dict:
        return self.raw["kitty_file"]

    @property
    def tile_size_px(self) -> int:
        return int(self.container["tile_size_px"])

    @property
    def file_version(self) -> int:
        """The version this converter WRITES: the campaign/v1 container."""
        return int(self.container["campaign_version"])

    @property
    def read_layouts(self) -> Dict[int, dict]:
        """Every container version this converter can READ, keyed by version int.

        The layouts are DATA (``kitty_file.read_layouts``): which child chunk
        holds the grid, where the level name starts inside the metadata chunk,
        and whether the grid chunk carries the radio-text sub-chunk.  Adding a
        version is a table edit, not a code edit.
        """
        return {
            int(version): layout
            for version, layout in self.container["read_layouts"].items()
            if not version.startswith("_")
        }

    def read_layout(self, version: int) -> dict:
        try:
            return self.read_layouts[version]
        except KeyError:
            raise TableError(
                "savegame version %d (0x%04x) has no layout in the table; it knows %s"
                % (version, version,
                   ", ".join("%d" % v for v in sorted(self.read_layouts)))
            )

    @property
    def gif_level_files(self) -> List[str]:
        """The level gif FILE NAMES of this dialect, from the table's own census.

        The census was taken over the dialect's whole level set, so its keys are
        exactly the files the game ships -- which is also the list of names a
        replacement level may be given, since the game loads a custom level only
        as an overwrite of one of them.  Derived, never typed out.
        """
        return sorted(self.raw["censuses"]["gif_id_counts"])

    @property
    def settings(self) -> dict:
        return self.raw["settings_donor"]

    @property
    def paint(self) -> dict:
        return self.raw["paint"]

    @property
    def paint_styles(self) -> List[str]:
        return list(self.paint["styles"])

    @property
    def default_paint_style(self) -> str:
        return self.paint["default_style_name"]

    @property
    def paintable_layouts(self) -> Tuple[int, ...]:
        return tuple(self.paint["paintable_layouts"])

    def paint_style_of(self, paint: int) -> str:
        """Which style bucket a stored ``mPaint`` value falls in."""
        for name, span in self.paint["style_paint_ranges"].items():
            if span[0] <= paint <= span[1]:
                return name
        return "paint %d (outside every style range)" % paint

    def paint_base(self, style: str) -> int:
        try:
            return int(self.paint["style_paint_ranges"][style][0])
        except KeyError:
            raise TableError(
                "unknown paint style %r; the table names %r"
                % (style, self.paint_styles)
            )

    # -------------------------------------------------------------------- checks
    def check(self) -> List[str]:
        """Integrity of the DATA.  Returns a list of problems (empty == clean)."""
        problems: List[str] = []
        for row in self.raw["pairs"]:
            for gid in _as_ids(row["gif"]):
                if gid not in self.gif_ids:
                    problems.append("pair %r names gif id %d, absent from gif.ids" % (row, gid))
                elif self.gif_ids[gid].get("refuse"):
                    # Either direction is a defect.  Forward, the row contradicts
                    # the refusal; backward, it would EMIT the id the refusal
                    # exists to keep out of a file.
                    problems.append(
                        "pair %r names gif id %d, which this table refuses (%s)"
                        % (row, gid, self.gif_ids[gid]["refuse"].split(".")[0])
                    )
            if isinstance(row["kitty"], str):
                if row["kitty"] not in self.position_fields:
                    problems.append("pair %r names unknown position field" % row)
            else:
                for kid in _as_ids(row["kitty"]):
                    if kid not in self.kitty_ids:
                        problems.append(
                            "pair %r names layout id %d, absent from kitty.ids" % (row, kid)
                        )
            if row.get("shape") == "vpair" and len(_as_ids(row["kitty"])) != 2:
                problems.append("pair %r is shape=vpair but its target is not a couple" % row)
        for style in self.paint_styles:
            if style not in self.paint["style_paint_ranges"]:
                problems.append("paint style %r has no range" % style)
        if self.default_paint_style not in self.paint_styles:
            problems.append("default paint style %r is not a named style" % self.default_paint_style)
        for layout in self.paintable_layouts:
            if layout not in self.kitty_ids:
                problems.append("paintable layout %d is not a layout id" % layout)
        return problems


def dialect_file(dialect: Optional[str]) -> str:
    """The packaged file name for a dialect, refusing an unknown one BY NAME."""
    name = DEFAULT_DIALECT if dialect is None else dialect
    try:
        return DIALECTS[name]
    except KeyError:
        raise TableError(
            "unknown dialect %r; this package ships %s"
            % (dialect, ", ".join(sorted(DIALECTS)))
        )


def _as_ids(value: Union[int, Sequence[int]]) -> Tuple[int, ...]:
    if isinstance(value, int):
        return (value,)
    return tuple(int(v) for v in value)


def _pick(source_id: int, rules: List[Rule]) -> Rule:
    """Resolve several rows carrying the same source id: best class tag wins.

    A tie is a table defect and says so, rather than picking silently.
    """
    if len(rules) == 1:
        return rules[0]
    best = min(CLASS_ORDER.index(r.cls) for r in rules)
    winners = [r for r in rules if CLASS_ORDER.index(r.cls) == best]
    if len(winners) > 1:
        raise TableError(
            "%s id %d is claimed by %d class-%s rows (%s) -- the table cannot say which"
            % (
                winners[0].direction.split("->")[0],
                source_id,
                len(winners),
                winners[0].cls,
                ", ".join(str(r.target_ids) for r in winners),
            )
        )
    return winners[0]


@dataclass
class Palette:
    """Canonical RGB per gif id, straight out of ``palette.json``."""

    raw: dict
    path: str

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Palette":
        path = path or os.environ.get(PALETTE_ENV) or os.path.join(DATA_DIR, "palette.json")
        with open(path, encoding="utf-8") as fh:
            return cls(raw=json.load(fh), path=path)

    @property
    def rgb_by_id(self) -> Dict[int, Tuple[int, int, int]]:
        return {int(k): tuple(v) for k, v in self.raw["canonical_rgb"].items()}

    def flat(self, size: int = 256, fill: Tuple[int, int, int] = (0, 0, 0)) -> List[int]:
        """A flat 3*size palette: every id the table knows keeps its measured RGB."""
        out = list(fill) * size
        for gid, rgb in self.rgb_by_id.items():
            if 0 <= gid < size:
                out[gid * 3 : gid * 3 + 3] = list(rgb)
        return out
