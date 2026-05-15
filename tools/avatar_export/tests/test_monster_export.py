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
