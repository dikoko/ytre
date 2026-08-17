import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._prop_config import discover_props
from src.parsers.tmd_parser import TMDParser
from tests.test_prop_static_identity import animated_props


def test_scale_axis_census():
    """73 of the 188 animated props carry SCALEAXISLIST."""
    animated = animated_props()
    found = 0
    for cat, prop_id, tmd_path in discover_props():
        if (cat, prop_id) not in animated:
            continue
        if any(a.scale_axis_keys for a in TMDParser().parse(tmd_path).animations):
            found += 1
    assert found == 73


def test_scale_axis_key_is_a_unit_quaternion():
    checked = 0
    for _cat, _prop_id, tmd_path in discover_props():
        model = TMDParser().parse(tmd_path)
        for anim in model.animations:
            for key in anim.scale_axis_keys:
                q = key.rotation
                mag = (q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w) ** 0.5
                assert abs(mag - 1.0) < 1e-3, f"non-unit scale axis {mag}"
                checked += 1
        if checked > 50:
            return
    assert checked > 0, "no scale-axis keys found at all"


def test_both_scale_axis_readers_are_exercised():
    """SCALEAXISLIST has two on-disk layouts and both ship.

    Files at TMD_VERSION_20040304 or newer use the plain axis reader; older
    ones take the legacy stretch-rotate reader, which carries an ORT block, interleaves
    scale with the axis, and negates axis[3]. Reading a legacy file with the
    modern layout yields denormal garbage, so both paths need coverage.
    """
    from src.parsers.tmd_parser import TMD_VERSION_20040304

    modern = legacy = 0
    for _cat, _prop_id, tmd_path in discover_props():
        model = TMDParser().parse(tmd_path)
        if not any(a.scale_axis_keys for a in model.animations):
            continue
        if model.version < TMD_VERSION_20040304:
            legacy += 1
        else:
            modern += 1
    assert modern == 69
    assert legacy == 4


def test_legacy_stretch_rot_supplies_scale_alongside_axis():
    """The legacy chunk emits BOTH tracks, so scale must be populated too."""
    from src.parsers.tmd_parser import TMD_VERSION_20040304

    for _cat, _prop_id, tmd_path in discover_props():
        model = TMDParser().parse(tmd_path)
        if model.version >= TMD_VERSION_20040304:
            continue
        for anim in model.animations:
            if not anim.scale_axis_keys:
                continue
            assert len(anim.scale_keys) == len(anim.scale_axis_keys)
            for sk, ak in zip(anim.scale_keys, anim.scale_axis_keys):
                assert sk.frame == ak.frame
            return
    raise AssertionError("no legacy stretch-rot prop found")


def test_inheritance_flags_are_in_range():
    """TMDINHERIT_POS/ROT/SCL occupy 0x0007/0x0038/0x01c0 (TMDChunkDef.h)."""
    seen = set()
    for _cat, _prop_id, tmd_path in discover_props():
        for anim in TMDParser().parse(tmd_path).animations:
            seen.add(anim.inheritance)
    for flags in seen:
        assert 0 <= flags <= 0x01FF, f"inheritance flags out of range: {flags:#x}"
