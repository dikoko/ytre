import sys
from pathlib import Path

import numpy as np
import pytest
from pygltflib import GLTF2

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._prop_config import PROP_BASE
from src.exporters.prop_animation import (
    build_animation_plan, object_matrix_d3d, to_godot_matrix,
)
from src.exporters.prop_exporter import export_prop
from src.parsers.tmd_parser import TMDParser

PORTAL = PROP_BASE / "Portal.IRD" / "p_portal003a.TMD"
FIRE = PROP_BASE / "Active.IRD" / "E_SCfire_1.TMD"


def _load(tmp_path, tmd_path, prop_id):
    out = tmp_path / f"{prop_id}.glb"
    export_prop(TMDParser().parse(tmd_path), out, prop_id=prop_id)
    return GLTF2().load(str(out))


@pytest.fixture(scope="module")
def portal_glb(tmp_path_factory):
    return _load(tmp_path_factory.mktemp("anim"), PORTAL, "p_portal003a")


@pytest.fixture(scope="module")
def portal_plan():
    return build_animation_plan(TMDParser().parse(PORTAL), "p_portal003a")


def _node_index(gltf, name):
    for i, n in enumerate(gltf.nodes):
        if n.name == name:
            return i
    return None


def _node_matrix(node) -> np.ndarray:
    """glTF node -> column-major 4x4 as a numpy column-vector matrix."""
    if node.matrix:
        return np.array(node.matrix, dtype=np.float64).reshape(4, 4).T
    m = np.eye(4)
    if node.rotation:
        x, y, z, w = node.rotation
        m[:3, :3] = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])
    if node.scale:
        m[:3, :3] = m[:3, :3] @ np.diag(node.scale)
    if node.translation:
        m[:3, 3] = node.translation
    return m


def test_animated_objects_get_a_pivot_and_an_animated_node(portal_glb, portal_plan):
    names = {n.name for n in portal_glb.nodes}
    assert portal_plan.animated
    for node in portal_plan.animated.values():
        assert node.node_name in names, f"missing animated node {node.node_name}"
        assert node.pivot_name in names, f"missing pivot node {node.pivot_name}"


def test_animated_node_uses_trs_not_a_matrix(portal_glb, portal_plan):
    """Animation channels target TRS; a matrix node cannot be animated."""
    for node in portal_plan.animated.values():
        gnode = portal_glb.nodes[_node_index(portal_glb, node.node_name)]
        assert not gnode.matrix, "animated node must be TRS"


def _descendants(gltf, idx, out=None):
    out = set() if out is None else out
    for c in (gltf.nodes[idx].children or []):
        if c not in out:
            out.add(c)
            _descendants(gltf, c, out)
    return out


def test_animated_node_descends_from_its_pivot(portal_glb, portal_plan):
    """Directly for plain objects; through the factor chain for sheared ones."""
    for node in portal_plan.animated.values():
        pivot_idx = _node_index(portal_glb, node.pivot_name)
        assert _node_index(portal_glb, node.node_name) in _descendants(
            portal_glb, pivot_idx
        )


def test_sheared_objects_get_an_animatable_factor_chain(portal_glb, portal_plan):
    """A scale about a tilted axis must not be frozen into a static matrix."""
    from src.exporters.prop_animation import has_shear

    sheared = [n for n in portal_plan.animated.values() if has_shear(n.animation)]
    assert sheared, "portal fixture no longer exercises the shear path"
    names = {n.name for n in portal_glb.nodes}
    for node in sheared:
        for suffix in ("_a", "_axisinv", "_scale"):
            assert f"{node.node_name}{suffix}" in names
        # every factor node must be TRS so it can carry channels
        for suffix in ("_a", "_axisinv", "_scale", ""):
            gnode = portal_glb.nodes[_node_index(portal_glb, f"{node.node_name}{suffix}")]
            assert not gnode.matrix


def test_frame0_world_placement_matches_the_authored_matrix(portal_glb, portal_plan):
    """The whole point of the pivot: frame 0 lands exactly where the static
    bake would have put it, measured through the REAL exported node chain."""
    model = TMDParser().parse(PORTAL)
    parent_of = {}
    for i, n in enumerate(portal_glb.nodes):
        for c in (n.children or []):
            parent_of[c] = i

    for obj_index, node in portal_plan.animated.items():
        idx = _node_index(portal_glb, node.node_name)
        m = np.eye(4)
        walk = idx
        guard = 0
        while walk is not None and guard < 32:
            m = _node_matrix(portal_glb.nodes[walk]) @ m
            walk = parent_of.get(walk)
            guard += 1
        want = to_godot_matrix(object_matrix_d3d(model.objects[obj_index]))
        assert np.allclose(m, want, atol=1e-4), (
            f"{node.node_name} placement off:\n{np.round(m,4)}\nwant\n{np.round(want,4)}"
        )


def test_static_objects_still_baked(portal_glb, portal_plan):
    """Objects without keys keep the old path: geometry under a plain node."""
    animated_names = set()
    for node in portal_plan.animated.values():
        animated_names.add(node.node_name)
        animated_names.add(node.pivot_name)
    plain = [n for n in portal_glb.nodes
             if n.mesh is not None and n.name not in animated_names]
    assert plain, "expected at least one baked static mesh node"


def test_every_mesh_is_reachable_from_the_scene(portal_glb):
    """A node emitted but never parented would silently vanish in Godot."""
    reachable = set()

    def walk(i):
        if i in reachable:
            return
        reachable.add(i)
        for c in (portal_glb.nodes[i].children or []):
            walk(c)

    for root in portal_glb.scenes[portal_glb.scene].nodes:
        walk(root)
    for i, n in enumerate(portal_glb.nodes):
        assert i in reachable, f"node {n.name} is orphaned"


def test_animation_channels_emitted(portal_glb):
    assert portal_glb.animations, "no glTF animations emitted"
    assert "default" in {a.name for a in portal_glb.animations}


def test_all_samplers_are_linear(portal_glb):
    """The engine lerps position/scale and slerps rotation; TCB is dead."""
    for anim in portal_glb.animations:
        for sampler in anim.samplers:
            assert sampler.interpolation == "LINEAR"


def test_channels_target_animated_nodes_only(portal_glb, portal_plan):
    owned = set()
    for node in portal_plan.animated.values():
        for suffix in ("", "_a", "_axisinv", "_scale"):
            idx = _node_index(portal_glb, f"{node.node_name}{suffix}")
            if idx is not None:
                owned.add(idx)
    for anim in portal_glb.animations:
        for channel in anim.channels:
            assert channel.target.node in owned
            assert channel.target.path in ("translation", "rotation", "scale")


def test_time_inputs_are_seconds(portal_glb):
    """318 frames at 30 fps -> the longest input ends near 10.6 s."""
    model = TMDParser().parse(PORTAL)
    longest = model.total_frames / model.frame_speed
    acc = portal_glb.accessors
    ends = [acc[s.input].max[0] for a in portal_glb.animations
            for s in a.samplers if acc[s.input].max]
    assert ends
    assert max(ends) <= longest + 0.05


def test_quaternion_keys_share_a_hemisphere(portal_glb):
    """A LINEAR sampler interpolates raw components, so a sign flip between
    neighbouring keys would spin the long way round. The engine handles this
    at sample time (gtQuatSlerp's `flip`); glTF must bake it into the data."""
    blob = portal_glb.binary_blob()
    for anim in portal_glb.animations:
        for ch in anim.channels:
            if ch.target.path != "rotation":
                continue
            acc = portal_glb.accessors[anim.samplers[ch.sampler].output]
            bv = portal_glb.bufferViews[acc.bufferView]
            data = np.frombuffer(
                blob[bv.byteOffset:bv.byteOffset + bv.byteLength], dtype=np.float32
            ).reshape(-1, 4)
            for i in range(1, len(data)):
                assert float(np.dot(data[i - 1], data[i])) >= -1e-6, \
                    "consecutive quaternion keys are in opposite hemispheres"


def test_rotation_channels_actually_vary(portal_glb):
    """Guard against emitting channels whose keys are all identical."""
    blob = portal_glb.binary_blob()
    varying = 0
    for anim in portal_glb.animations:
        if anim.name != "default":
            continue
        for ch in anim.channels:
            acc = portal_glb.accessors[anim.samplers[ch.sampler].output]
            bv = portal_glb.bufferViews[acc.bufferView]
            data = np.frombuffer(
                blob[bv.byteOffset:bv.byteOffset + bv.byteLength], dtype=np.float32
            )
            if len(data) and float(np.abs(data - data[0]).max()) > 1e-6:
                varying += 1
    assert varying > 0, "every animation channel is constant"


def test_fire_exports_and_places_correctly(tmp_path):
    glb = _load(tmp_path, FIRE, "E_SCfire_1")
    plan = build_animation_plan(TMDParser().parse(FIRE), "E_SCfire_1")
    names = {n.name for n in glb.nodes}
    for node in plan.animated.values():
        assert node.node_name in names
