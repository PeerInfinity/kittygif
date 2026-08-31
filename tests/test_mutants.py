"""Mutant discipline: prove each gate DISCRIMINATES before trusting it green.

A gate that cannot go red on a broken table is not a gate.  Each test here
breaks the table in one specific way, in a COPY (the shipped data file is never
edited), and asserts the matching gate fails.

  (i)  table-swap     -- transpose two ids; L1 must go red.
  (ii) degrade-policy  -- retag a class-(c) kind as (a); the report gate must go red.

**Mutant (i) came back with a finding.**  Transposing two ``both`` rows is
INVISIBLE to L1: a ``both`` row is one edge of a bijection, permuting the edges
leaves a bijection, and ``gif -> kitty -> gif`` still closes -- even though the
emitted level has had two materials swapped.  L1 is a self-consistency gate, so
a consistently relabelled table is exactly what it cannot see.  Both halves are
pinned below; the mutant that L1 *can* see breaks the symmetry (the forward rows
transposed, the reverse rows left alone), and the symmetric one is caught only by
the external oracle (``scripts/local/l2_oracle_gate.py --mutant``).

Both mutants also carry their own negative control: they must leave the OTHER
gate alone, or they would be proving something broader than they claim.
"""

import pytest

import fixtures
from kittygif import gifio, kittyio
from kittygif.convert import gif_to_kitty, kitty_to_gif
from kittygif.table import IdTable


def _roundtrip(table, level):
    kitty_level, forward = gif_to_kitty(level, table, name="MUT")
    back, reverse = kitty_to_gif(kitty_level, table)
    return back, forward, reverse


# ------------------------------------------------------------------ mutant (i)
def _transpose_symmetric(raw):
    """Transpose the gif ends of two class-(a) both-direction rows.

    This is the mutant as first specified -- and it is MEASURED VACUOUS against
    L1 (see the test below).  Kept, and asserted, so the finding cannot be lost.
    """
    rows = _both_rows(raw)
    rows[0]["gif"], rows[1]["gif"] = rows[1]["gif"], rows[0]["gif"]
    return rows[0], rows[1]


def _transpose_one_direction(raw):
    """Transpose two ids in the gif->kitty direction ONLY.

    A ``both`` row is one bijection EDGE, so permuting the edges leaves a
    bijection and the round trip still closes.  Breaking the symmetry -- the two
    forward rows swapped, the two reverse rows left where they were -- is what a
    round-trip gate can actually see.
    """
    a, b = _both_rows(raw)[:2]
    ka, kb = a["kitty"], b["kitty"]
    a["kitty"], a["directions"] = kb, "gif->kitty"
    b["kitty"], b["directions"] = ka, "gif->kitty"
    raw["pairs"].append({"gif": a["gif"], "kitty": ka, "cls": "a",
                         "directions": "kitty->gif", "note": "unmutated reverse"})
    raw["pairs"].append({"gif": b["gif"], "kitty": kb, "cls": "a",
                         "directions": "kitty->gif", "note": "unmutated reverse"})
    return a, b


def _both_rows(raw):
    rows = [r for r in raw["pairs"]
            if r["cls"] == "a" and r["directions"] == "both"
            and isinstance(r["gif"], int) and isinstance(r["kitty"], int)
            and r["gif"] != 0]
    assert len(rows) >= 2
    return rows


def test_l1_is_green_on_the_shipped_table(table):
    """The control the mutants are measured against, at this tree state."""
    level = fixtures.l1_gif(table)
    back, _f, _r = _roundtrip(table, level)
    assert back.tiles == level.tiles


def test_a_SYMMETRIC_transposition_is_invisible_to_L1_and_that_is_the_point(
        tmp_path, table):
    """L1 is a SELF-CONSISTENCY gate: a relabelled table is still a bijection.

    Transposing two ``both`` rows permutes the edges of a bijection, so
    ``gif -> kitty -> gif`` still closes -- while the emitted .kitty really has
    had two materials swapped.  Only an external oracle (L2 in
    ``scripts/local/``, or the game itself) can see this class of defect.  The
    assertions below pin BOTH halves of that finding.
    """
    path = fixtures.mutant_table(tmp_path, table, _transpose_symmetric)
    mutant = IdTable.load(path)
    assert mutant.check() == []

    level = fixtures.l1_gif(table)
    back, _f, _r = _roundtrip(mutant, level)
    assert back.tiles == level.tiles, "if this ever goes red, L1 grew teeth it did not have"

    honest, _ = gif_to_kitty(level, table, name="OK")
    lying, _ = gif_to_kitty(level, mutant, name="MUT")
    assert honest.tiles != lying.tiles, "the mutant must really produce a different level"


def test_one_directional_transposition_turns_L1_RED(tmp_path, table):
    path = fixtures.mutant_table(tmp_path, table, _transpose_one_direction)
    mutant = IdTable.load(path)
    assert mutant.check() == [], "the mutant must be a VALID table, just a wrong one"

    level = fixtures.l1_gif(table)          # the fixture is built from the REAL table
    back, _f, _r = _roundtrip(mutant, level)
    assert back.tiles != level.tiles, "L1 cannot see a transposed pair -- it is not a gate"


def test_one_directional_transposition_turns_L1_RED_through_real_files(
        tmp_path, table, palette):
    """The same mutant, driven the way the CLI drives it: gif -> file -> gif."""
    path = fixtures.mutant_table(tmp_path, table, _transpose_one_direction)
    mutant = IdTable.load(path)
    level = fixtures.l1_gif(table)

    src, mid, dst = (str(tmp_path / n) for n in ("m_src.gif", "m.kitty", "m_dst.gif"))
    gifio.write(level, src, palette)
    converted, _f = gif_to_kitty(gifio.read(src), mutant, name="MUT")
    kittyio.write(converted, mid, mutant)
    back, _r = kitty_to_gif(kittyio.read(mid, mutant), mutant)
    gifio.write(back, dst, palette)
    assert open(src, "rb").read() != open(dst, "rb").read()


def test_table_swap_mutant_leaves_the_REPORT_gate_alone(tmp_path, table):
    """Negative control: this mutant is about ids, not about policy."""
    path = fixtures.mutant_table(tmp_path, table, _transpose_one_direction)
    mutant = IdTable.load(path)
    _out, report = kitty_to_gif(fixtures.all_layouts_kitty(mutant), mutant)
    assert report.solvability_at_risk


# ----------------------------------------------------------------- mutant (ii)
def _c_kind_retagged_as_a(raw, direction):
    """Reclassify one class-(c) row as class (a) -- the degrade policy, broken."""
    row = next(r for r in raw["pairs"]
               if r["cls"] == "c" and r["directions"] == direction)
    row["cls"] = "a"
    return row


def _victim(table, direction):
    import json

    raw = json.loads(json.dumps(table.raw))
    return _c_kind_retagged_as_a(raw, direction)


def test_degrade_policy_mutant_turns_the_gif_to_kitty_REPORT_gate_RED(tmp_path, table):
    victim = _victim(table, "gif->kitty")
    victim_id = victim["gif"] if isinstance(victim["gif"], int) else victim["gif"][0]

    path = fixtures.mutant_table(
        tmp_path, table, lambda raw: _c_kind_retagged_as_a(raw, "gif->kitty"))
    mutant = IdTable.load(path)

    level = fixtures.unmappable_gif(table)
    _out, report = gif_to_kitty(level, mutant, name="MUT")

    entry = next(e for e in report.entries if e.source_id == victim_id)
    assert entry.cls == "a", "the mutant did not actually change the policy"
    # the gate in test_report.py asserts exactly this, and it now fails:
    assert not any(e.cls == "c" and e.source_id == victim_id for e in report.entries)


def test_degrade_policy_mutant_can_silence_the_solvability_warning(tmp_path, table):
    """The consequential half: a mis-tagged kind stops warning the player."""

    def retag_every_c(raw):
        for row in raw["pairs"]:
            if row["cls"] == "c" and row["directions"] == "gif->kitty":
                row["cls"] = "b"

    path = fixtures.mutant_table(tmp_path, table, retag_every_c)
    mutant = IdTable.load(path)
    level = fixtures.unmappable_gif(table)

    _out, honest = gif_to_kitty(level, table, name="OK")
    _out2, lying = gif_to_kitty(level, mutant, name="MUT")
    assert honest.solvability_at_risk and not lying.solvability_at_risk
    assert "SOLVABILITY MAY HAVE CHANGED" not in lying.to_text()


def test_degrade_policy_mutant_leaves_L1_alone(tmp_path, table, palette):
    """Negative control: retagging a class-(c) kind moves no mappable id."""
    path = fixtures.mutant_table(
        tmp_path, table, lambda raw: _c_kind_retagged_as_a(raw, "kitty->gif"))
    mutant = IdTable.load(path)
    level = fixtures.l1_gif(table)
    back, _f, _r = _roundtrip(mutant, level)
    assert back.tiles == level.tiles


# --------------------------------------------------------- fixture discrimination
def test_the_l1_fixture_actually_contains_every_mappable_id(table):
    """A fixture that omits an id cannot fail on it."""
    level = fixtures.l1_gif(table)
    present = set(level.tiles)
    expected = fixtures.mappable_gif_ids(table)
    missing = expected - present
    assert not missing, "the L1 fixture never exercises %s" % sorted(missing)


def test_the_report_fixture_actually_contains_every_degraded_id(table):
    level = fixtures.unmappable_gif(table)
    present = set(level.tiles)
    expected = {gid for gid, rule in table.forward.items()
                if rule.cls in ("b", "c") and not rule.position_field}
    assert not expected - present


def test_the_kitty_fixture_actually_contains_every_layout_id(table):
    level = fixtures.all_layouts_kitty(table)
    assert set(level.tiles) >= set(table.reverse)


@pytest.mark.parametrize("length", [1, 2, 3, 4])
def test_the_gate_fixture_exercises_each_run_length(table, length):
    gate = next(g for g, r in table.forward.items() if r.shape == "vpair")
    level = fixtures.l1_gif(table)
    runs = []
    for x in range(level.width):
        ys = [y for y in range(level.height) if level.at(x, y) == gate]
        current = []
        for y in ys:
            if current and current[-1] == y - 1:
                current.append(y)
            else:
                if current:
                    runs.append(len(current))
                current = [y]
        if current:
            runs.append(len(current))
    assert length in runs
