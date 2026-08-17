import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._prop_config import PROP_BASE, discover_props
from src.exporters.prop_animation import (
    build_animation_plan, d3d_rotation_matrix, mat4_d3d, object_matrix_d3d,
    quat_from_d3d_matrix, to_godot_basis, to_godot_matrix,
    to_godot_translation, verify_frame0_invariant, world_matrix_d3d,
)
from src.parsers.tmd_parser import Quaternion, TMDParser
from tests.test_prop_static_identity import animated_props

PORTAL = PROP_BASE / "Portal.IRD" / "p_portal003a.TMD"
FIRE = PROP_BASE / "Active.IRD" / "E_SCfire_1.TMD"
DOOR = PROP_BASE / "Artificial.IRD" / "a_ESDdoor02a.TMD"


def test_identity_quaternion_is_identity_matrix():
    m = d3d_rotation_matrix(Quaternion(0.0, 0.0, 0.0, 1.0))
    assert np.allclose(m, np.eye(3), atol=1e-9)


def test_quat_matrix_round_trip():
    rng = np.random.default_rng(7)
    for _ in range(20):
        v = rng.normal(size=4)
        v /= np.linalg.norm(v)
        q = Quaternion(*v)
        m = d3d_rotation_matrix(q)
        back = quat_from_d3d_matrix(m)
        again = d3d_rotation_matrix(Quaternion(*back))
        assert np.allclose(m, again, atol=1e-6)


def test_godot_basis_conjugation_is_an_involution():
    rng = np.random.default_rng(0)
    m = rng.normal(size=(3, 3))
    # S . (S . m^T . S)^T . S == m
    assert np.allclose(to_godot_basis(to_godot_basis(m)), m, atol=1e-9)


def test_godot_translation_negates_z():
    assert to_godot_translation((1.0, 2.0, 3.0)) == (1.0, 2.0, -3.0)


def test_godot_matrix_conversion_is_a_homomorphism():
    """The real guard on the conversion: composition must survive it.

    D3D composes row-vector (p . A . B); Godot composes column-vector
    (B @ A @ p). If to_godot_matrix got the transpose or the mirror wrong,
    single matrices could still look plausible while products came out
    wrong — which is exactly how a whole prop ends up mirrored.
    """
    rng = np.random.default_rng(11)
    for _ in range(25):
        a = mat4_d3d(rng.normal(size=(3, 3)), rng.normal(size=3))
        b = mat4_d3d(rng.normal(size=(3, 3)), rng.normal(size=3))
        assert np.allclose(
            to_godot_matrix(a @ b), to_godot_matrix(b) @ to_godot_matrix(a),
            atol=1e-9,
        )


def test_godot_matrix_round_trips_a_point():
    """A point transformed in D3D and converted must land where Godot puts it."""
    rng = np.random.default_rng(3)
    m = mat4_d3d(rng.normal(size=(3, 3)), rng.normal(size=3))
    p = rng.normal(size=3)
    d3d = np.append(p, 1.0) @ m
    godot = to_godot_matrix(m) @ np.append(to_godot_translation(p), 1.0)
    assert np.allclose(to_godot_translation(d3d[:3]), godot[:3], atol=1e-9)


def test_animation_offset_detected_per_file():
    """24 animations for 23 objects -> offset 1; 30/30 -> offset 0 (spec 1.2)."""
    portal = build_animation_plan(TMDParser().parse(PORTAL), "p_portal003a")
    assert portal.anim_offset == 1
    door = build_animation_plan(TMDParser().parse(DOOR), "a_ESDdoor02a")
    assert door.anim_offset == 0


def test_fire_invariant_is_exact():
    """E_SCfire_1: every animated object reproduces its authored world matrix."""
    model = TMDParser().parse(FIRE)
    plan = build_animation_plan(model, "E_SCfire_1")
    assert plan.animated
    assert verify_frame0_invariant(model, plan) == []


def test_pivot_places_frame0_at_the_authored_world_matrix():
    """The placement guarantee, stated directly: frame 0 == the static bake."""
    model = TMDParser().parse(PORTAL)
    plan = build_animation_plan(model, "p_portal003a")
    assert plan.animated
    for obj_index in plan.animated:
        got = world_matrix_d3d(plan, obj_index, 0)
        want = object_matrix_d3d(model.objects[obj_index])
        assert np.allclose(got, want, atol=1e-4)


def test_animation_actually_moves_away_from_frame0():
    """Guard against a pivot that accidentally freezes the motion.

    If the pivot were applied on the wrong side, every frame would collapse
    onto the frame-0 pose and the props would export 'animated' but still.
    """
    model = TMDParser().parse(PORTAL)
    plan = build_animation_plan(model, "p_portal003a")
    moved = 0
    for obj_index, node in plan.animated.items():
        n_keys = max(len(node.animation.position_keys),
                     len(node.animation.rotation_keys),
                     len(node.animation.scale_keys))
        if n_keys < 2:
            continue
        a = world_matrix_d3d(plan, obj_index, 0)
        b = world_matrix_d3d(plan, obj_index, n_keys - 1)
        if np.abs(a - b).max() > 1e-6:
            moved += 1
    assert moved > 0, "no animated object changes between first and last key"


def test_key_frames_stay_in_a_sane_range():
    """Payload-desync detector, and the check that caught the TCB bug.

    Track keys are `frame + value` and nothing else — 16/20/16 bytes for
    position/rotation/scale. The parser used to also read a 5-float TCB
    block that does not exist on disk, which slid every subsequent read and
    turned float bit patterns into frame numbers around 1.1e9 (~1.07e8
    seconds at 30 fps). Any future desync shows up here immediately.
    """
    worst = 0
    for cat, prop_id in _ANIMATED:
        match = [t for c, p, t in discover_props() if (c, p) == (cat, prop_id)]
        model = TMDParser().parse(match[0])
        for anim in model.animations:
            for keys in (anim.position_keys, anim.rotation_keys,
                         anim.scale_keys, anim.scale_axis_keys):
                for key in keys:
                    worst = max(worst, key.frame)
    assert worst == 4800, f"max key frame moved to {worst}"


def test_frame0_local_matches_the_static_local_matrix_for_most_objects():
    """Statistical sanity gate on the decoded key VALUES.

    Unlike verify_frame0_invariant — which the pivot makes true by
    construction regardless of what the keys contain — this compares the
    decoded frame-0 TRS against an independently stored matrix. It is not a
    universal invariant (STATICLOCALMATRIX is an authored snapshot that does
    not always correspond to frame 0, so ~20% legitimately differ), but a
    payload desync drops the match rate to essentially zero.
    """
    from src.exporters.prop_animation import local_matrix_d3d

    matched = total = 0
    for cat, prop_id in _ANIMATED:
        path = [t for c, p, t in discover_props() if (c, p) == (cat, prop_id)][0]
        model = TMDParser().parse(path)
        plan = build_animation_plan(model, prop_id)
        for obj_index, node in plan.animated.items():
            got = local_matrix_d3d(node.animation, 0)
            want = object_matrix_d3d(model.objects[obj_index], "local_transform")
            if not np.all(np.isfinite(got)):
                continue
            total += 1
            if np.abs(got - want).max() <= 1e-3:
                matched += 1
    assert total > 3000
    assert matched / total > 0.75, f"only {matched}/{total} — likely a desync"


def test_demoted_objects_are_rare_and_recorded():
    """Objects that cannot yield a pivot fall back to the static bake.

    Two causes, both fatal to a node transform if ignored: NaN in the
    authored tracks, and a singular frame-0 basis that cannot be inverted.

    Only 6 objects library-wide, all singular. The 41 'NaN track' objects
    this once reported were an artefact of the TCB payload desync, not
    authored data: with the correct 16/20/16-byte key layout every shipped
    track decodes finite. The NaN guard stays as a cheap safety net.
    """
    from src.exporters.prop_animation import _tracks_are_finite

    nan_tracks = singular = 0
    for cat, prop_id in _ANIMATED:
        match = [t for c, p, t in discover_props() if (c, p) == (cat, prop_id)]
        model = TMDParser().parse(match[0])
        plan = build_animation_plan(model, prop_id)
        for obj_index in plan.demoted:
            anim = model.animations[obj_index + plan.anim_offset]
            if _tracks_are_finite(anim):
                singular += 1
            else:
                nan_tracks += 1
    assert nan_tracks == 0
    assert singular == 6


def test_one_prop_animates_only_mesh_free_helpers():
    """a_SWAptameet01's sole animated object is a Dummy with no geometry.

    Nothing is emitted for it, so its GLB is byte-identical to a static
    export and the scene gets no AnimationPlayer. The export script must not
    advertise it as animated — hence has_visible_animation, and hence the
    exporter's 187 rather than the plan resolver's 188.
    """
    from src.exporters.prop_animation import has_visible_animation

    invisible = []
    for cat, prop_id in _ANIMATED:
        path = [t for c, p, t in discover_props() if (c, p) == (cat, prop_id)][0]
        model = TMDParser().parse(path)
        plan = build_animation_plan(model, prop_id)
        if not has_visible_animation(model, plan):
            invisible.append(prop_id)
    assert invisible == ["a_SWAptameet01"]


_ANIMATED = sorted(animated_props())


@pytest.mark.parametrize("category,prop_id", _ANIMATED,
                         ids=[f"{c}/{p}" for c, p in _ANIMATED])
def test_frame0_invariant_over_all_animated_props(category, prop_id):
    """Spec 5.1 — the gate that catches an index-mapping or matrix error."""
    match = [t for c, p, t in discover_props() if (c, p) == (category, prop_id)]
    model = TMDParser().parse(match[0])
    plan = build_animation_plan(model, prop_id)
    failures = verify_frame0_invariant(model, plan)
    assert failures == [], (
        f"{category}/{prop_id}: {len(failures)}/{len(plan.animated)} objects off "
        f"— {failures[:3]}"
    )
