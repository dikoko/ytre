"""Tests for sfd_parser — particle effect (.sfd) decoder.

Fixture values were pinned 2026-09-05 by a hand-walked hex dump of the two
files (spec §6): sfx_common_particledot1_red.sfd (schema-3 polygon emitter,
the most-referenced effect in skills.json — 208 uses) and
sfx_common_condition_aging_billboard.sfd (schema-2 billboard, two textures,
NO additive field on disk).
"""
import collections
from pathlib import Path

import pytest

from src.parsers.sfd_parser import (
    BILLBOARD_GRAPHS, DYNAMIC_GRAPHS, EMITTER_GRAPHS, OBJECT_GRAPHS,
    parse_sfd, slope_mismatch,
)

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
SFD_DIR = YTREF_ROOT / "models" / "raw" / "Skill.IRD" / "SFD"


def _fleet():
    return sorted(SFD_DIR.glob("*.sfd"))


def test_red_dot_emitter_fixture():
    e = parse_sfd(SFD_DIR / "sfx_common_particledot1_red.sfd")
    assert e.kind == "emitter_polygon"
    assert e.schema == 3
    assert e.object_type == 3
    assert e.texture_direction == 0
    assert e.textures == ["sfx_common_particledot1_red.tga"]
    assert e.total_time == 1.0
    assert e.additive is True
    assert e.alignment == -1
    # object base graphs: 5 points, texture frame graph 6 points
    assert [len(e.graphs[k].points) for k in OBJECT_GRAPHS] == [5, 5, 5, 5]
    assert len(e.graphs["texture_frame"].points) == 6
    assert e.graphs["opacity"].points[0] == pytest.approx((0.0, 1.0, 0.0, 1.0))
    assert e.graphs["opacity"].points[-1] == pytest.approx((1.0, 1.0, 0.0, 0.0))
    # dynamic: gravity 10, everything else flat 0 except wind_x = 1
    assert e.graphs["gravity"].points[0] == pytest.approx((0.0, 10.0, 0.0, 10.0), abs=1e-4)
    assert e.graphs["wind_x"].points[0] == pytest.approx((0.0, 1.0, 0.0, 1.0))
    assert e.graphs["wind_force"].points[0][1] == 0.0
    # the 8-float editor snapshot: net force (0,-10,0), black hole 0, drag 0
    assert len(e.dynamic_state) == 8
    assert e.dynamic_state[:3] == [0.0, -10.0, 0.0]
    # emitter graphs — stored slopes are real slopes (life descends 2 -> 0)
    life0 = e.graphs["life"].points[0]
    assert life0[0] == 0.0 and life0[1] == 2.0
    assert life0[2] == pytest.approx(-2.2857, abs=1e-3)
    assert life0[3] == 2.0
    assert e.graphs["life_random"].points[0][1] == 1.0
    assert e.graphs["dir_y"].points[0][1] == pytest.approx(0.338, abs=1e-3)
    assert e.graphs["dir_x"].points[0][1] == 0.0
    assert e.graphs["speed"].points[0][1] == 15.0
    assert e.graphs["speed"].points[-1][1] == pytest.approx(3.409, abs=1e-3)
    assert e.graphs["spread"].points[0][1] == pytest.approx(35.065, abs=1e-3)
    assert e.graphs["rate"].points[0][1] == pytest.approx(64.286, abs=1e-3)
    assert e.graphs["rate"].points[0][2] == pytest.approx(-257.143, abs=1e-2)
    assert e.graphs["scale_t"].points[0][1] == pytest.approx(0.084, abs=1e-3)
    assert e.graphs["particle_opacity"].points[-1][1] == 0.0
    assert set(EMITTER_GRAPHS) <= set(e.graphs)
    assert set(DYNAMIC_GRAPHS) <= set(e.graphs)
    assert not (set(BILLBOARD_GRAPHS) & set(e.graphs))


def test_aging_billboard_fixture():
    e = parse_sfd(SFD_DIR / "sfx_common_condition_aging_billboard.sfd")
    assert e.kind == "billboard"
    assert e.schema == 2            # older tool build: no additive field
    assert e.object_type == 7
    assert e.texture_direction == 1  # TOP
    assert e.textures == ["sfx_common_condition_aging3.tga",
                          "sfx_common_condition_aging1.tga"]
    assert e.total_time == 1.0
    assert e.additive is True        # the default when absent, nothing on disk
    assert e.alignment == 0          # VIEWPLANE
    assert e.dynamic_state == []
    assert e.graphs["opacity"].points[0] == pytest.approx((0.0, 0.0, 4.0, 0.0), abs=1e-3)
    assert e.graphs["opacity"].points[-1][1] == pytest.approx(0.409, abs=1e-3)
    assert e.graphs["width"].points[0] == pytest.approx((0.0, 1.562, 0.0, 1.562), abs=1e-3)
    assert len(e.graphs["height"].points) == 5
    assert not (set(EMITTER_GRAPHS) & set(e.graphs))


def test_fleet_parses_clean_and_census_pinned():
    files = _fleet()
    assert len(files) == 154
    schema = collections.Counter()
    additive = collections.Counter()
    alignment = collections.Counter()
    mismatch_files = 0
    files_past_one = 0
    for f in files:
        e = parse_sfd(f)                       # no exception = clean, zero trailing bytes
        schema[(e.kind, e.schema)] += 1
        additive[e.additive] += 1
        if e.kind == "billboard":
            alignment[e.alignment] += 1
        file_past_one = False
        for g in e.graphs.values():
            if g.points:
                assert g.points[0][0] == 0.0
            for i in range(len(g.points) - 1):
                assert g.points[i][0] <= g.points[i + 1][0]
                if g.points[i + 1][0] > 1.0:
                    file_past_one = True
            if len(g.points) > 1:
                assert g.points[-1][2] == 0.0 and g.points[-1][3] == 0.0
        if file_past_one:
            files_past_one += 1
        if any(slope_mismatch(g) for g in e.graphs.values()):
            mismatch_files += 1
    assert schema == {("emitter_polygon", 2): 66, ("emitter_polygon", 3): 52,
                      ("billboard", 2): 23, ("billboard", 3): 13}
    assert additive == {True: 135, False: 19}
    assert alignment == {0: 36}
    # 73 files store slopes an equal-interval recompute does not reproduce —
    # pinned so a parser that "helpfully" recomputes c1/c2 fails loudly.
    assert mismatch_files == 73
    # The original evaluator clamps t to [0,1], so authored points past 1.0
    # are dead data (9 files); a graph whose last point sits before 1.0
    # evaluates to 0 past it (the strict walk reaches the last point, whose
    # coefficients are 0).
    assert files_past_one == 9


def test_unsupported_root_class_is_loud(tmp_path):
    bad = tmp_path / "bad.sfd"
    # type byte 3, new-class tag, version 3|0x8000, name_len 8, "SfCBogus"
    bad.write_bytes(bytes.fromhex("03 ffff 0380 0800") + b"SfCBogus" + b"\x00" * 32)
    with pytest.raises(ValueError, match="SfCBogus"):
        parse_sfd(bad)


def test_trailing_bytes_is_loud(tmp_path):
    original = (SFD_DIR / "sfx_common_particledot1_red.sfd").read_bytes()
    bad = tmp_path / "trailing.sfd"
    bad.write_bytes(original + b"\x00")
    with pytest.raises(ValueError) as exc_info:
        parse_sfd(bad)
    assert "trailing" in str(exc_info.value).lower()
    assert str(len(original)) in str(exc_info.value)


def test_type_byte_mismatch_is_loud(tmp_path):
    data = bytearray((SFD_DIR / "sfx_common_particledot1_red.sfd").read_bytes())
    data[0] = 7  # leading type byte says BILLBOARD, class tag says polygon emitter
    bad = tmp_path / "mismatch.sfd"
    bad.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="object type"):
        parse_sfd(bad)
