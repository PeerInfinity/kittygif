"""The conversion report.

Both directions of this converter are PARTIAL, so the tool never refuses a file:
it always emits, and the report says exactly what was translated faithfully, what
was degraded cosmetically, and what could not be represented at all.  Three
classes, taken from the table's own tags:

  * **a** -- mappable: a table entry both ends agree on.  Converted silently.
  * **b** -- degraded: cosmetic only (a paint style, a decoration, a bonus
    collectible).  Solvability unchanged.  Listed.
  * **c** -- unrepresentable mechanics: emitted as the nearest safe tile and
    reported prominently, with per-kind counts and coordinates.  **A class-(c)
    substitution may change whether the level can be finished.**

The JSON form is the machine-readable one; the text form is for a human reading
stderr.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

CLASS_LABEL = {
    "a": "mappable",
    "b": "degraded (cosmetic)",
    "c": "UNREPRESENTABLE (substituted)",
}


@dataclass
class Entry:
    cls: str
    source_id: int
    source_name: str
    target_id: Optional[int]
    target_name: str
    note: str = ""
    coords: List[Tuple[int, int]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.coords)

    def to_json(self) -> dict:
        return {
            "class": self.cls,
            "class_label": CLASS_LABEL[self.cls],
            "source_id": self.source_id,
            "source_name": self.source_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "count": self.count,
            "coords": [list(c) for c in self.coords],
            "note": self.note,
        }


@dataclass
class Report:
    direction: str
    width: int = 0
    height: int = 0
    source: str = ""
    target: str = ""
    table_path: str = ""
    entries: List[Entry] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------ building
    def record(self, cls: str, source_id: int, source_name: str,
               target_id: Optional[int], target_name: str, note: str,
               x: int, y: int) -> None:
        key = (cls, source_id, target_id)
        entry = self._index.get(key)
        if entry is None:
            entry = Entry(cls, source_id, source_name, target_id, target_name, note)
            self._index[key] = entry
            self.entries.append(entry)
        entry.coords.append((x, y))

    def __post_init__(self) -> None:
        self._index: Dict[Tuple[str, int, Optional[int]], Entry] = {}

    # ------------------------------------------------------------------ querying
    def by_class(self, cls: str) -> List[Entry]:
        return [e for e in self.entries if e.cls == cls]

    def counts(self) -> Dict[str, int]:
        out = {c: 0 for c in CLASS_LABEL}
        for entry in self.entries:
            out[entry.cls] += entry.count
        return out

    @property
    def solvability_at_risk(self) -> bool:
        """True iff something was substituted that can change the route."""
        return any(e.count for e in self.by_class("c"))

    # ------------------------------------------------------------------- output
    def to_json(self) -> dict:
        ordered = sorted(
            self.entries, key=lambda e: ("abc".index(e.cls), -e.count, e.source_id)
        )
        return {
            "direction": self.direction,
            "source": self.source,
            "target": self.target,
            "id_table": self.table_path,
            "grid": {"width": self.width, "height": self.height},
            "cells": {"total": self.width * self.height, "by_class": self.counts()},
            "solvability_at_risk": self.solvability_at_risk,
            "entries": [e.to_json() for e in ordered],
            "notes": list(self.notes),
        }

    def to_text(self, max_coords: int = 8) -> str:
        counts = self.counts()
        lines = [
            "%s: %s -> %s" % (self.direction, self.source or "(level)", self.target or "(level)"),
            "  grid %dx%d = %d cells   mappable %d | degraded %d | substituted %d"
            % (self.width, self.height, self.width * self.height,
               counts["a"], counts["b"], counts["c"]),
        ]
        for cls in ("c", "b"):
            entries = sorted(self.by_class(cls), key=lambda e: (-e.count, e.source_id))
            entries = [e for e in entries if e.count]
            if not entries:
                continue
            lines.append("  %s:" % CLASS_LABEL[cls])
            for entry in entries:
                where = " ".join("(%d,%d)" % c for c in entry.coords[:max_coords])
                if entry.count > max_coords:
                    where += " ... +%d more" % (entry.count - max_coords)
                lines.append(
                    "    %4d x %s -> %s%s"
                    % (entry.count, entry.source_name, entry.target_name,
                       ("  [%s]" % entry.note) if entry.note else "")
                )
                if where:
                    lines.append("           at %s" % where)
        for note in self.notes:
            lines.append("  note: %s" % note)
        if self.solvability_at_risk:
            lines.append(
                "  *** SOLVABILITY MAY HAVE CHANGED: the substitutions above replace "
                "mechanics this format cannot express. ***"
            )
        return "\n".join(lines)
