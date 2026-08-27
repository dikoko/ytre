"""Effects export: cross-tree texture resolution + never-invalid GLBs.

2026-08-25 report: 54/352 effect GLBs failed Godot import with
"Index material = 0 is out of bounds (materials.size() = 0)". Root cause:
effect TMDs reference textures in OTHER asset trees via relative paths
(`..\\..\\Monster\\ct0113\\ct0113.bmp` — monster-death effects reuse the
monster's own skin; weapon glows reference `..\\..\\Avatar\\attach\\*.BMP`
with uppercase extensions). embed_textures only searched basenames in the
prop texture dirs, silently skipped the miss, and shipped primitives
stamped with a material index into an empty materials array.

Contract pinned here:
1. Relative texture paths resolve against the TMD's own directory,
   case-insensitively, mapping bare tree names to their .IRD dirs
   (Monster -> Monster.IRD).
2. Resolution order is unchanged for everything that already resolved
   (model dir, then texture-dir index, THEN the relative resolver) — the
   static-prop byte-identity gate depends on that.
3. A texture that cannot be resolved at all yields a textureless
   fallback material instead of an out-of-bounds primitive reference —
   an exported GLB must always be importable.
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._export_common import embed_textures
from scripts._prop_config import SKILL_TMD_DIR, TEXTURE_SEARCH_DIRS
from src.exporters.prop_exporter import export_prop
from src.parsers.tmd_parser import TMDParser


def _export(prop_id: str, tmp_path: Path) -> dict:
    tmd_path = SKILL_TMD_DIR / f"{prop_id}.TMD"
    model = TMDParser().parse(tmd_path)
    glb = tmp_path / f"{prop_id}.glb"
    export_prop(model, glb, prop_id=prop_id)
    embed_textures(glb, tmd_path.parent, model, texture_dirs=TEXTURE_SEARCH_DIRS)
    data = glb.read_bytes()
    n = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + n])


def _assert_material_refs_valid(gltf: dict, label: str) -> None:
    mats = gltf.get("materials", [])
    for mesh in gltf.get("meshes", []):
        for prim in mesh["primitives"]:
            ref = prim.get("material")
            assert ref is None or ref < len(mats), (
                f"{label}: primitive references material {ref} but only "
                f"{len(mats)} materials exist — Godot refuses this GLB")


def test_cross_tree_monster_texture_resolves(tmp_path):
    """sfx_ct0113_attack1 references ..\\..\\Monster\\ct0113\\ct0113.bmp."""
    gltf = _export("sfx_ct0113_attack1", tmp_path)
    _assert_material_refs_valid(gltf, "sfx_ct0113_attack1")
    mats = gltf.get("materials", [])
    assert mats, "monster-skin material must be emitted"
    assert any("baseColorTexture" in m.get("pbrMetallicRoughness", {})
               for m in mats), "the monster skin must actually embed"


def test_attach_texture_resolves_case_insensitively(tmp_path):
    """sfx_weapon_mura_A1005 references ..\\..\\Avatar\\attach\\
    weapon_mura_A1005.bmp; the shipped file is .BMP (uppercase)."""
    gltf = _export("sfx_weapon_mura_A1005", tmp_path)
    _assert_material_refs_valid(gltf, "sfx_weapon_mura_A1005")
    mats = gltf.get("materials", [])
    assert mats and any("baseColorTexture" in m.get("pbrMetallicRoughness", {})
                        for m in mats)


def test_missing_texture_yields_valid_glb_with_fallback(tmp_path):
    """sfx_spirit_order_hellhound_nonstopdash_target2 references
    sfx_hellhound.tga, which ships nowhere — the one genuinely missing
    texture in the fleet. The GLB must still be importable: a textureless
    fallback material, never an out-of-bounds reference."""
    gltf = _export("sfx_spirit_order_hellhound_nonstopdash_target2", tmp_path)
    _assert_material_refs_valid(gltf, "hellhound target2")
    mats = gltf.get("materials", [])
    assert mats, "fallback material must be emitted for the missing texture"
