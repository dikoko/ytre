"""Tests for monster export pipeline."""

from pathlib import Path

import pytest
from pygltflib import GLTF2

from src.exporters.animation_exporter import export_with_animations
from src.parsers.mlib_parser import MLIBParser
from src.parsers.tmd_parser import TMDParser

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MONSTER_IRD = YTREF_ROOT / "models" / "raw" / "Monster.IRD"

# Pilot monsters for testing
PILOT_MONSTERS = ["ct0001", "ct0003", "ct0005", "ct0010", "ct0100"]


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path


def _parse_monster(monster_id: str):
    """Parse a monster's TMD and MLIB files."""
    monster_dir = MONSTER_IRD / monster_id
    tmd = TMDParser().parse(monster_dir / f"{monster_id}.TMD")
    mlib = MLIBParser().parse(monster_dir / f"{monster_id}.mlib")
    return tmd, mlib


@pytest.mark.parametrize("monster_id", PILOT_MONSTERS)
def test_monster_export_creates_valid_glb(monster_id, tmp_output):
    """Export a monster and verify the GLB is valid."""
    tmd, mlib = _parse_monster(monster_id)
    output_path = tmp_output / f"{monster_id}.glb"

    export_with_animations(tmd, mlib, output_path, animation_names=None, validate=False, v_flip=False, anim_correction=True)

    assert output_path.exists()
    gltf = GLTF2().load(str(output_path))
    assert len(gltf.meshes) >= 1
    assert len(gltf.skins) == 1
    assert len(gltf.animations) == 6  # stand, walk, run, attack1, hit1, die


def test_ct0003_skeleton_exports_with_bones(tmp_output):
    """ct0003 skeleton exports with correct bone structure."""
    tmd, mlib = _parse_monster("ct0003")
    output_path = tmp_output / "ct0003.glb"

    export_with_animations(tmd, mlib, output_path, animation_names=[], validate=False, v_flip=False, anim_correction=True)

    gltf = GLTF2().load(str(output_path))
    assert len(gltf.skins) == 1
    assert len(gltf.skins[0].joints) == 57  # ct0003 has 57 bones


def test_ct0007_bone_name_fallback(tmp_output):
    """ct0007 has @Head in TMD but Bip01 Head in MLIB - should still animate."""
    tmd, mlib = _parse_monster("ct0007")
    output_path = tmp_output / "ct0007.glb"

    export_with_animations(tmd, mlib, output_path, animation_names=None, validate=False, v_flip=False, anim_correction=True)

    gltf = GLTF2().load(str(output_path))
    skin = gltf.skins[0]
    # TMD bone 5 is the first @Head — find it (first occurrence in joints list)
    head_node_idx = None
    for joint_idx in skin.joints:
        if gltf.nodes[joint_idx].name == "@Head":
            head_node_idx = joint_idx
            break
    assert head_node_idx is not None, "@Head bone not found"

    # @Head (TMD 5) should be a child of Bip01 Neck, not a direct child of Armature.
    # Without index fallback, it becomes an orphan root parented to Armature.
    parent_name = None
    for node in gltf.nodes:
        if node.children and head_node_idx in node.children:
            parent_name = node.name
            break
    assert parent_name == "Bip01 Neck", (
        f"@Head should be child of 'Bip01 Neck', got parent '{parent_name}'"
    )


def test_ct0025_walk_root_height(tmp_output):
    """ct0025 walk should keep root near bind height (1.05), not double it."""
    tmd, mlib = _parse_monster("ct0025")
    output_path = tmp_output / "ct0025.glb"

    export_with_animations(
        tmd, mlib, output_path,
        animation_names=["ct0025_walk"],
        validate=False, v_flip=False, anim_correction=True, split_materials=True,
    )

    gltf = GLTF2().load(str(output_path))
    blob = gltf.binary_blob()

    import numpy as np
    anim = gltf.animations[0]
    trans_channel = None
    for ch in anim.channels:
        if ch.target.path == "translation":
            trans_channel = ch
            break
    assert trans_channel is not None, "Walk animation should have translation channel"

    sampler = anim.samplers[trans_channel.sampler]
    acc = gltf.accessors[sampler.output]
    bv = gltf.bufferViews[acc.bufferView]
    data = np.frombuffer(blob[bv.byteOffset:bv.byteOffset + bv.byteLength], dtype=np.float32).reshape(-1, 3)

    mean_y = data[:, 1].mean()
    assert 0.8 < mean_y < 1.3, f"Walk root Y should be near 1.05, got mean={mean_y:.3f}"


@pytest.mark.parametrize("monster_id", PILOT_MONSTERS)
def test_monster_animations_have_correct_names(monster_id, tmp_output):
    """Verify animation names follow ct####_action pattern."""
    tmd, mlib = _parse_monster(monster_id)
    output_path = tmp_output / f"{monster_id}.glb"

    export_with_animations(tmd, mlib, output_path, animation_names=None, validate=False, v_flip=False, anim_correction=True)

    gltf = GLTF2().load(str(output_path))
    anim_names = {a.name for a in gltf.animations}
    expected_suffixes = ["stand", "walk", "run", "attack1", "hit1", "die"]
    for suffix in expected_suffixes:
        assert f"{monster_id}_{suffix}" in anim_names, f"Missing animation {monster_id}_{suffix}"


# --- Skinning-bind IBM parity (2026-07-26) ---------------------------------
# The original client skins vertices with W_runtime @ inv(TMD static world)
# — verbatim authored rotations including scale and reflections. Node
# animation parity alone cannot catch a wrong bind (bone positions barely
# move while every skinned vertex skews), so skinning is correct iff every
# IBM equals inv(S4 @ static_world @ S4). The old reflection-rig bind path
# (a stand-frame-0 hybrid pose) violated this — the ct0016/cn0090 "walking
# library" distortion, ct0024 limb distortion.

def _max_ibm_error_vs_static(tmd, glb_path):
    """tmd must already be extended (_extend_bones_with_animation_targets)
    when the export was — joint k maps to the EXTENDED bone list's entry k."""
    import numpy as np
    gltf = GLTF2().load(str(glb_path))
    blob = gltf.binary_blob()
    S4 = np.diag([1.0, 1.0, -1.0, 1.0])
    # ORDINAL mapping (joint k <-> tmd.bones[k]), never by name: shipped
    # rigs carry duplicate bone names (ct0039 has six "@Hair00"), and the
    # exporter itself binds ordinally.
    truth_inv = []
    for b in tmd.bones:
        R = np.array(b.world_transform.rotation.data).reshape(3, 3).T
        M = np.eye(4)
        M[:3, :3] = R
        t = b.world_transform.translation
        M[:3, 3] = [t.x, t.y, t.z]
        truth_inv.append(np.linalg.inv(S4 @ M @ S4))

    def read_acc(idx):
        acc = gltf.accessors[idx]
        bv = gltf.bufferViews[acc.bufferView]
        off = (bv.byteOffset or 0) + (acc.byteOffset or 0)
        return np.frombuffer(blob, dtype=np.float32,
                             count=acc.count * 16, offset=off).reshape(-1, 4, 4)

    worst = 0.0
    for skin in gltf.skins:
        ibms = np.transpose(read_acc(skin.inverseBindMatrices), (0, 2, 1))
        assert len(skin.joints) >= len(truth_inv), "skin joints < TMD bones"
        for k in range(len(truth_inv)):
            worst = max(worst, float(np.abs(ibms[k] - truth_inv[k]).max()))
    return worst


@pytest.mark.parametrize("monster_id", [
    "ct0016",   # reflection-rig bind path — was 11.4 off
    "ct0024",   # reflection-rig path — user-visible limb distortion
    "ct0039",   # no reflections, duplicate-bone-name rig
    "ct0021",   # control: was already exact; must stay exact
])
def test_ibms_match_engine_static_bind(monster_id, tmp_output):
    monster_dir = MONSTER_IRD / monster_id
    tmd = TMDParser().parse(monster_dir / f"{monster_id}.TMD")
    mlib = MLIBParser().parse(monster_dir / f"{monster_id}.mlib")
    out = tmp_output / f"{monster_id}.glb"
    export_with_animations(tmd, mlib, out, animation_names=None,
                           validate=False, v_flip=False, anim_correction=True,
                           split_materials=True, mlib_translations=True)
    # export_with_animations extended tmd.bones in place (mlib_translations),
    # so the ordinal comparison below sees the same list the skin was built on
    err = _max_ibm_error_vs_static(tmd, out)
    assert err < 1e-4, f"{monster_id}: IBM deviates {err:.4f} from static bind"


def test_moving_root_uses_bone0_transkey_not_deltas(tmp_output):
    """Root rule per retail client behavior: the skeleton root's X/Y come
    from bone 0's own translation track (the authored absolute pose —
    ct0021's walk crouches to ~0.87-1.05), while the separate root-position
    track is the ENTITY displacement track (per-frame deltas for moving
    motions; the client integrates it into entity movement, zeroes x/y, and
    pins the skeleton root Z at the motion origin). The old exporter fed
    zero-meaned root positions + bind height into the root node instead —
    every moving walk/run hovered at standing height (ct0021: 1.42, +0.45
    too high)."""
    import numpy as np
    tmd, mlib = _parse_monster("ct0021")
    out = tmp_output / "ct0021.glb"
    export_with_animations(tmd, mlib, out, animation_names=["ct0021_walk"],
                           validate=False, v_flip=False, anim_correction=True,
                           split_materials=True, mlib_translations=True)
    gltf = GLTF2().load(str(out))
    blob = gltf.binary_blob()
    anim = gltf.animations[0]
    root_vals = None
    for ch in anim.channels:
        if ch.target.path != "translation":
            continue
        if gltf.nodes[ch.target.node].name.strip() == "@Root":
            s = anim.samplers[ch.sampler]
            acc = gltf.accessors[s.output]
            bv = gltf.bufferViews[acc.bufferView]
            off = (bv.byteOffset or 0) + (acc.byteOffset or 0)
            root_vals = np.frombuffer(blob, np.float32, acc.count * 3,
                                      off).reshape(-1, 3)
    assert root_vals is not None
    motion = next(m for m in mlib.motions if m.name.endswith("walk"))
    tk0 = np.array([[fr[0].x, fr[0].y, -fr[0].z] for fr in motion.translations])
    # X/Y must equal bone 0's translation track; Z pinned at the origin (0).
    assert np.abs(root_vals[:, 0] - tk0[:, 0]).max() < 1e-4
    assert np.abs(root_vals[:, 1] - tk0[:, 1]).max() < 1e-4, (
        f"walk root Y [{root_vals[:,1].min():.3f}..{root_vals[:,1].max():.3f}] "
        f"!= authored track Y [{tk0[:,1].min():.3f}..{tk0[:,1].max():.3f}]")
    assert np.abs(root_vals[:, 2] - (-motion.origin.z)).max() < 1e-4
