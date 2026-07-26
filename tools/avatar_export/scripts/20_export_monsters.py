#!/usr/bin/env python3
"""
Monster Export Script

Exports monster TMD models with skeleton and animations from MLIB to GLB.
Embeds BMP texture directly into the GLB as a PNG material.

Usage:
    python scripts/20_export_monsters.py              # Export pilot monsters (5)
    python scripts/20_export_monsters.py --all         # Export all monsters
    python scripts/20_export_monsters.py --ids ct0001 ct0005  # Export specific monsters
"""

import argparse
import io
import sys
import time
from pathlib import Path

from PIL import Image
from pygltflib import (
    GLTF2, BufferView, Material, PbrMetallicRoughness,
    TextureInfo, Texture, Image as GLTFImage, Sampler,
)

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from src.exporters.animation_exporter import (
    export_with_animations, _build_parent_map, _build_tmd_to_mlib_map,
    _rotation_matrix_to_quaternion, _normalize_rotation_matrix,
    _quat_conjugate, _quat_multiply, _quat_normalize,
)
from src.parsers.mlib_parser import MLIBParser, Quaternion
from src.parsers.tmd_parser import TMDParser

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
MONSTER_IRD = YTREF_ROOT / "models" / "raw" / "Monster.IRD"
CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytavatar" / "client"
OUTPUT_MODELS_DIR = CLIENT_DIR / "assets" / "monsters" / "models"

PILOT_MONSTERS = ["ct0001", "ct0003", "ct0005", "ct0010", "ct0100"]


def discover_monsters() -> list[str]:
    """Find all monster directories in Monster.IRD.

    Requires the TMD to actually exist, so stray non-model directories in
    an extracted dump can't become phantom entries in every sweep."""
    dirs = sorted(
        d.name for d in MONSTER_IRD.iterdir()
        if d.is_dir() and d.name.startswith("ct")
        and (d / f"{d.name}.TMD").exists()
    )
    return dirs


def _embed_textures(glb_path: Path, monster_dir: Path, model) -> None:
    """Embed all TMD material textures into a GLB file."""
    gltf = GLTF2().load(str(glb_path))
    blob = bytearray(gltf.binary_blob())

    gltf.images = gltf.images or []
    gltf.samplers = gltf.samplers or []
    gltf.textures = gltf.textures or []
    gltf.materials = gltf.materials or []

    if not gltf.samplers:
        gltf.samplers.append(Sampler())

    # Build material index -> GLTF material index mapping
    mat_map = {}  # TMD material_index -> GLTF material index
    for mat_idx, tmd_mat in enumerate(model.materials):
        tex_name = tmd_mat.texture_filename
        if not tex_name:
            continue

        # Find the BMP file (case-insensitive search)
        bmp_path = None
        for f in monster_dir.iterdir():
            if f.name.lower() == tex_name.lower():
                bmp_path = f
                break
        if bmp_path is None:
            continue

        # Convert BMP to PNG and embed
        img = Image.open(bmp_path)
        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")
        png_bytes = png_buf.getvalue()

        img_offset = len(blob)
        blob.extend(png_bytes)

        img_bv_idx = len(gltf.bufferViews)
        gltf.bufferViews.append(
            BufferView(buffer=0, byteOffset=img_offset, byteLength=len(png_bytes))
        )

        img_idx = len(gltf.images)
        gltf.images.append(GLTFImage(bufferView=img_bv_idx, mimeType="image/png"))

        tex_idx = len(gltf.textures)
        gltf.textures.append(Texture(source=img_idx, sampler=0))

        gltf_mat_idx = len(gltf.materials)
        gltf.materials.append(Material(
            name=tmd_mat.name,
            pbrMetallicRoughness=PbrMetallicRoughness(
                baseColorTexture=TextureInfo(index=tex_idx),
                metallicFactor=0.0,
                roughnessFactor=1.0,
            ),
        ))
        mat_map[mat_idx] = gltf_mat_idx

    # Assign materials to mesh primitives.
    # Rebuild primitive→material mapping by replaying the split logic.
    if gltf.meshes and mat_map:
        prim_mat_list = []
        for mesh in model.meshes:
            unique_mats = set(mesh.vertex_materials.values()) if mesh.vertex_materials else set()
            if len(unique_mats) > 1:
                # Mesh was split by material — one primitive per material group
                mat_faces: dict[int, bool] = {}
                for face in mesh.faces:
                    face_mat = mesh.vertex_materials.get(face[0], mesh.material_index)
                    mat_faces[face_mat] = True
                for mat_idx in sorted(mat_faces.keys()):
                    prim_mat_list.append(mat_idx)
            else:
                prim_mat_list.append(mesh.material_index)

        for prim_idx, prim in enumerate(gltf.meshes[0].primitives):
            if prim_idx < len(prim_mat_list):
                tmd_mat_idx = prim_mat_list[prim_idx]
                if tmd_mat_idx in mat_map:
                    prim.material = mat_map[tmd_mat_idx]
                elif 0 in mat_map:
                    prim.material = mat_map[0]

    gltf.buffers[0].byteLength = len(blob)
    gltf.set_binary_blob(bytes(blob))
    gltf.save(str(glb_path))


def _correct_mlib_rotations(tmd, mlib) -> None:
    """Pre-correct MLIB rotation data to match TMD rest-pose rotations.

    For bones where TMD and MLIB rest-pose rotations differ, compute a
    per-bone correction and apply it to ALL animation frames in-place.
    This ensures animations produce correct poses relative to the TMD skeleton.
    Only modifies the in-memory MLIB data, not the file.
    """
    parent_map = _build_parent_map(tmd, mlib)
    t2m = _build_tmd_to_mlib_map(tmd, mlib)

    # Compute TMD rest-pose local rotations
    world_rot = []
    for bone in tmd.bones:
        R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
        R = _normalize_rotation_matrix(R)
        world_rot.append(_rotation_matrix_to_quaternion(R))

    # Find reference motion (stand)
    ref_motion = None
    for motion in mlib.motions:
        if "stand" in motion.name:
            ref_motion = motion
            break
    if ref_motion is None and mlib.motions:
        ref_motion = mlib.motions[0]
    if ref_motion is None:
        return

    # Compute per-bone correction: TMD_rest_local * inverse(MLIB_stand_f0)
    corrections = {}  # mlib_bone_idx → correction quaternion
    for tmd_idx in range(len(tmd.bones)):
        parent_idx = parent_map.get(tmd_idx, -1)
        if parent_idx < 0:
            tmd_lr = world_rot[tmd_idx]
        else:
            tmd_lr = _quat_multiply(_quat_conjugate(world_rot[parent_idx]), world_rot[tmd_idx])

        mlib_idx = t2m.get(tmd_idx)
        if mlib_idx is None or mlib_idx >= ref_motion.bone_count:
            continue

        r = ref_motion.rotations[0][mlib_idx]
        mlib_ref = [r.x, r.y, r.z, r.w]
        dot = abs(sum(a * b for a, b in zip(tmd_lr, mlib_ref)))

        if dot < 0.999:
            mlib_ref_inv = _quat_conjugate(mlib_ref)
            correction = _quat_normalize(_quat_multiply(tmd_lr, mlib_ref_inv))
            corrections[mlib_idx] = correction

    if not corrections:
        return

    # Apply corrections to ALL animation frames in-place
    for motion in mlib.motions:
        for frame in range(motion.frame_count):
            for mlib_idx, correction in corrections.items():
                if mlib_idx >= motion.bone_count:
                    continue
                r = motion.rotations[frame][mlib_idx]
                q = [r.x, r.y, r.z, r.w]
                corrected = _quat_normalize(_quat_multiply(correction, q))
                motion.rotations[frame][mlib_idx] = Quaternion(
                    w=corrected[3], x=corrected[0], y=corrected[1], z=corrected[2],
                )


# Monsters that need per-bone rotation correction (TMD/MLIB mismatch causes
# visible distortion on arms, weapons, or other body parts)
_MONSTERS_NEEDING_CORRECTION = {
    'ct0032',   # Right arm distortion
    'ct0037',   # Weapon detachment (@Sword)
    'ct0038',   # Weapon detachment (@Sword)
}


def export_monster(monster_id: str) -> tuple[bool, str]:
    """Export a single monster's GLB with embedded texture. Returns (success, message)."""
    monster_dir = MONSTER_IRD / monster_id
    tmd_path = monster_dir / f"{monster_id}.TMD"
    mlib_path = monster_dir / f"{monster_id}.mlib"

    if not tmd_path.exists() or not mlib_path.exists():
        return False, f"Missing TMD or MLIB for {monster_id}"

    try:
        # Parse
        tmd = TMDParser().parse(tmd_path)
        mlib = MLIBParser().parse(mlib_path)

        # Export GLB (no V-flip for monsters, no avatar validation).
        # mlib_translations: faithful MLIB pose (translation tracks from the
        # MLIB skeleton's own offsets) — replaces the retired
        # _correct_mlib_rotations compensation, same as the NPC pipeline.
        glb_path = OUTPUT_MODELS_DIR / f"{monster_id}.glb"
        export_with_animations(
            tmd, mlib, glb_path,
            animation_names=None, validate=False, v_flip=False,
            anim_correction=True, split_materials=True,
            mlib_translations=True,
        )

        # Embed textures into GLB (supports multi-material monsters)
        _embed_textures(glb_path, monster_dir, tmd)

        glb_size = glb_path.stat().st_size / 1024
        anim_count = len(mlib.motions)
        return True, f"{monster_id}: {glb_size:.0f}KB, {len(tmd.bones)} bones, {anim_count} anims"
    except Exception as e:
        return False, f"{monster_id}: ERROR - {e}"


def main():
    parser = argparse.ArgumentParser(description="Export monster models to GLB")
    parser.add_argument("--all", action="store_true", help="Export all monsters")
    parser.add_argument("--ids", nargs="+", help="Export specific monster IDs")
    args = parser.parse_args()

    if args.ids:
        monster_ids = args.ids
    elif args.all:
        monster_ids = discover_monsters()
    else:
        monster_ids = PILOT_MONSTERS

    OUTPUT_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Exporting {len(monster_ids)} monsters...")
    start = time.time()
    success_count = 0

    for mid in monster_ids:
        ok, msg = export_monster(mid)
        print(f"  {'OK' if ok else 'FAIL'} {msg}")
        if ok:
            success_count += 1

    elapsed = time.time() - start
    print(f"\nDone: {success_count}/{len(monster_ids)} exported in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
