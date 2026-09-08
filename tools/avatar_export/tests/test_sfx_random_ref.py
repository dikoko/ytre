"""Tests for sfx_random_ref — the Python mirror of the original's
table-walking random helpers (spec §3.3). The GDScript port
(client/scripts/sfx_random.gd) replays the parity fixture this module
generates, so the formulas here ARE the contract."""
import math
from pathlib import Path

import pytest

from src.sfx_random_ref import (
    SfxRandomRef, build_parity, deg_units, load_tables, sin_units,
)

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
SKILL_IRD = YTREF_ROOT / "models" / "raw" / "Skill.IRD"


@pytest.fixture(scope="module")
def tables():
    return load_tables(SKILL_IRD / "intrand.dat", SKILL_IRD / "floatrand.dat")


def test_tables_shape(tables):
    ints, floats = tables
    assert len(ints) == 10000 and len(floats) == 10000
    assert ints[:3] == [26513, 10779, 25352]
    assert 2 <= min(ints) and max(ints) <= 32763
    assert floats[0] == pytest.approx(0.8091250, abs=1e-6)
    assert all(0.0 < f < 1.0 for f in floats)


def test_cursors_walk_and_wrap(tables):
    r = SfxRandomRef(*tables)
    assert [r.irand() for _ in range(3)] == [26513, 10779, 25352]
    r.reset()
    for _ in range(10000):
        r.irand()
    assert r.irand() == 26513          # wrapped to index 0
    assert r.frand() == pytest.approx(0.8091250, abs=1e-6)


def test_deg_units_wraps_negative():
    assert deg_units(90.0) == 16380
    assert deg_units(-90.0) == 49156   # (u16)(-16380): the fast-spin quirk
    assert deg_units(360.0) == 65520
    assert sin_units(16384) == pytest.approx(1.0)


def test_random_float_range(tables):
    r = SfxRandomRef(*tables)
    vals = [r.random_float(0.0, 1.0) for _ in range(200)]
    assert all(-1.0 <= v <= 1.0 for v in vals)
    # first int 26513 -> (26513 - 16383.5) / 16383.5
    assert vals[0] == pytest.approx((26513 - 16383.5) / 16383.5)


def test_random_life_clamps(tables):
    r = SfxRandomRef(*tables)
    assert r.random_life(2.0, 5.0) == pytest.approx(2.0 - 0.8091250 * 2.0, abs=1e-6)
    r.reset()
    assert r.random_life(-2.0, -1.0) == pytest.approx(2.0 - 0.8091250 * 1.0, abs=1e-6)


def test_random_direction_keeps_length_and_spreads(tables):
    r = SfxRandomRef(*tables)
    d = (0.0, 5.0, 0.0)
    for _ in range(50):
        out = r.random_direction(d, 35.0)
        assert math.sqrt(sum(c * c for c in out)) == pytest.approx(5.0, abs=1e-4)
        cos_angle = out[1] / 5.0
        assert cos_angle >= math.cos(math.radians(35.0)) - 1e-6
    r.reset()
    assert r.random_direction(d, 0.0) == pytest.approx(d)   # zero spread = same vector


def test_parity_fixture_shape(tables):
    p = build_parity(SfxRandomRef(*tables))
    assert p["version"] == 1
    assert len(p["irand"]) == 20 and len(p["frand"]) == 20
    assert len(p["random_float"]) == 50
    assert len(p["random_life"]) == 50
    assert len(p["random_direction"]) == 50 and len(p["random_direction"][0]) == 3
    assert len(p["spawn"]) == 20
    assert set(p["spawn"][0]) == {"dir", "ang_vel", "init_deg", "life"}
