"""The level-building helpers the sample generator uses.

Kept separate from :mod:`generate` so the four sample recipes read as recipes.

Two ideas carry the whole file:

**A sketch, not a grid.**  A recipe paints into a sparse :class:`Sketch` with a
left-to-right cursor and never has to know how wide the finished level is; the
sketch works that out when it is asked for a :class:`~kittygif.level.Level`.

**Ids come from the TABLE.**  :class:`Vocab` selects by the table's own ``kind``
vocabulary and by its own record of what is authorable.  Not one tile id is
written down in this repository's sample code -- which is also why the samples
follow the table: correct a row in ``id-table.json`` and the next
``generate.py`` run lays the level out with the corrected id.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from kittygif.level import Level
from kittygif.table import GIF, KITTY, IdTable


class Vocab:
    """The ids of one space, selected by KIND and by AUTHORABILITY.

    *Authorable* is the table's own distinction, not ours.  Two per-id notes take
    an id out of the set, and both are the table's:

    ``observed``
        the ENGINE generates this at load time or keeps it as runtime state, so
        a level FILE never carries it (a decoration quadrant, a parallax tile,
        an activated checkpoint).
    ``refuse``
        this dialect refuses to READ the id at all, because translating it is
        dangerous rather than lossy (the Flash lethal range).  An id a converter
        will not accept is not one a sample may author.

    Every other id is fair game.  Where the table has a census of real level
    files, :meth:`check_against_census` cross-checks the derivation against it;
    a dialect whose game ships one embedded map has no such census and says so.
    """

    def __init__(self, table: IdTable, space: str) -> None:
        self.table = table
        self.space = space
        self.ids: Dict[int, dict] = table.gif_ids if space == GIF else table.kitty_ids

    # ------------------------------------------------------------------ sets
    @property
    def authorable(self) -> List[int]:
        return sorted(i for i, meta in self.ids.items()
                      if "observed" not in meta and not meta.get("refuse"))

    @property
    def empty(self) -> int:
        return self.table.gif_empty if self.space == GIF else self.table.kitty_empty

    def kind(self, name: str) -> List[int]:
        """Every AUTHORABLE id whose measured kind is ``name``, in id order."""
        out = [i for i in self.authorable if self.ids[i].get("kind") == name]
        if not out:
            raise LookupError(
                "the %s side of %s has no authorable id of kind %r; the kinds it "
                "does have are %s"
                % (self.space, self.table.path, name, sorted(self.kinds))
            )
        return out

    def one(self, name: str) -> int:
        got = self.kind(name)
        if len(got) != 1:
            raise LookupError(
                "kind %r is not a singleton in the %s space: %s" % (name, self.space, got)
            )
        return got[0]

    @property
    def kinds(self) -> List[str]:
        return sorted({self.ids[i].get("kind", "") for i in self.authorable})

    def name(self, tile: int) -> str:
        return (self.table.gif_name if self.space == GIF else self.table.kitty_name)(tile)

    # ------------------------------------------------------------- the check
    def census_union(self) -> Optional[List[int]]:
        """The ids the table OBSERVED in real level files, or None if it counted none."""
        key = "gif_id_counts" if self.space == GIF else "kitty_layout_counts"
        counts = self.table.raw.get("censuses", {}).get(key)
        if not counts:
            return None
        seen: set = set()
        for per_file in counts.values():
            seen |= {int(i) for i in per_file}
        return sorted(seen)

    def check_against_census(self) -> str:
        """Cross-check ``authorable`` against the measured census.

        The two are independent: one reads a per-id note, the other counts
        cells in real files.  On the gif side they must agree exactly.  On the
        ``.kitty`` side the census is a SUBSET -- eleven campaign levels do not
        exercise the whole editor palette -- so it is reported, not enforced.
        """
        census = self.census_union()
        if census is None:
            return "%s: no census in the table" % self.space
        authorable, census_set = set(self.authorable), set(census)
        if self.space == GIF:
            if authorable != census_set:
                raise AssertionError(
                    "the gif space's authorable set and its census disagree: "
                    "authorable-only %s, census-only %s"
                    % (sorted(authorable - census_set), sorted(census_set - authorable))
                )
            return "gif: %d authorable ids, and the census of real level files agrees exactly" % len(census)
        if not census_set <= authorable:
            raise AssertionError(
                "the .kitty census names ids the table calls unauthorable: %s"
                % sorted(census_set - authorable)
            )
        return ("kitty: %d authorable layout ids; the 11-level campaign census "
                "exercises %d of them" % (len(authorable), len(census_set)))


class Sketch:
    """A sparse grid with a left-to-right cursor.

    ``height`` is fixed by the recipe (a corridor is a band); the WIDTH is
    whatever the recipe painted, plus the right-hand wall it asks for.
    """

    def __init__(self, height: int, fill: int) -> None:
        self.height = height
        self.fill = fill
        self.cells: Dict[Tuple[int, int], int] = {}
        self.x = 0

    # ---------------------------------------------------------------- paint
    def set(self, x: int, y: int, tile: int) -> None:
        if not 0 <= y < self.height:
            raise IndexError("row %d is outside the %d-row band" % (y, self.height))
        if x < 0:
            raise IndexError("column %d is left of the level" % x)
        self.cells[(x, y)] = tile

    def rect(self, x0: int, y0: int, x1: int, y1: int, tile: int) -> None:
        """Inclusive on both corners."""
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, tile)

    def column(self, x: int, tile: int, y0: int = 0, y1: Optional[int] = None) -> None:
        self.rect(x, y0, x, self.height - 1 if y1 is None else y1, tile)

    def row(self, y: int, x0: int, x1: int, tile: int) -> None:
        self.rect(x0, y, x1, y, tile)

    def at(self, x: int, y: int) -> int:
        return self.cells.get((x, y), self.fill)

    # --------------------------------------------------------------- cursor
    def advance(self, n: int = 1) -> int:
        """Move the cursor right and return the column it LEFT."""
        was = self.x
        self.x += n
        return was

    @property
    def width(self) -> int:
        return max((x for x, _y in self.cells), default=0) + 1

    # ---------------------------------------------------------------- build
    def to_level(self, space: str, name: str, robot=None, kitty=None) -> Level:
        width = max(self.width, self.x)
        tiles = [self.fill] * (width * self.height)
        for (x, y), tile in self.cells.items():
            tiles[y * width + x] = tile
        return Level(space=space, width=width, height=self.height, tiles=tiles,
                     name=name, robot=robot, kitty=kitty)


class Corridor:
    """The band layout every sample here is built on.

    Twelve rows, read top to bottom::

        0   cap          solid   -- seals the loft
        1   loft         air     -- display pockets (enemies, ceiling things)
        2   loft         air
        3   ceiling      solid   -- and a place to hang things from
        4   lane         air
        5   lane         air
        6   lane         air     -- the robot walks HERE
        7   floor        solid
        8   cellar       air     -- display pockets (hazards, fluids, mechanisms)
        9   cellar       air
        10  cellar       air
        11  base         solid   -- seals the cellar

    A pocket is a stretch of loft or cellar walled off at both ends: everything
    in it is visible in an editor and in the viewer, and none of it can reach
    the lane.  That is what lets a showcase level carry one of every enemy and
    still have a walk-right intended solution.
    """

    HEIGHT = 12
    CAP, CEILING, FLOOR, BASE = 0, 3, 7, 11
    LOFT = (1, 2)
    LANE = (4, 5, 6)
    WALK = 6
    CELLAR = (8, 9, 10)

    def __init__(self, sketch: Sketch, solid: int) -> None:
        self.s = sketch
        self.solid = solid

    def band(self, x0: int, x1: int, floor: Optional[int] = None) -> None:
        """Lay the four structural rows across ``x0..x1``."""
        for y in (self.CAP, self.CEILING, self.BASE):
            self.s.row(y, x0, x1, self.solid)
        self.s.row(self.FLOOR, x0, x1, self.solid if floor is None else floor)

    def wall(self, x: int) -> None:
        self.s.column(x, self.solid)

    def seal(self, x: int, rows: Sequence[int]) -> None:
        """A solid divider column across ``rows`` -- the side of a pocket."""
        for y in rows:
            self.s.set(x, y, self.solid)

    def pocket(self, rows: Sequence[int], width: int) -> Tuple[int, int]:
        """Cut a walled-off pocket into ``rows`` at the cursor.

        Leaves the cursor just past the pocket's right-hand divider and returns
        the INTERIOR span ``(x0, x1)``, inclusive.  Contents are the caller's
        business: a dripper wants the pocket's top row, a lava pool its bottom.
        """
        self.seal(self.s.x, rows)
        x0 = self.s.x + 1
        x1 = x0 + width - 1
        self.seal(x1 + 1, rows)
        self.s.x = x1 + 2
        return x0, x1
