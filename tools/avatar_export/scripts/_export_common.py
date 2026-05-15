"""
Shared export logic for monsters and NPCs.

Both use the same TMD + MLIB + BMP format and export pipeline.
"""

import io
import sys
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


_texture_index: dict[str, Path] | None = None


def _build_texture_index(texture_dirs: list[Path]) -> dict[str, Path]:
    """Build a one-time case-insensitive index of all texture files."""
    index = {}
    for d in texture_dirs:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.is_file():
                index[f.name.lower()] = f
    return index


def _find_texture(basename: str, model_dir: Path, texture_dirs: list[Path] | None = None) -> Path | None:
    """Find a texture file by basename, searching model_dir then texture_dirs.

    Case-insensitive matching. Uses a cached index for texture_dirs.
    """
    global _texture_index
    basename_lower = basename.lower()

    # Search model directory first (small, always fresh)
    for f in model_dir.iterdir():
        if f.is_file() and f.name.lower() == basename_lower:
            return f

    # Search texture directories via cached index
    if texture_dirs:
        if _texture_index is None:
            _texture_index = _build_texture_index(texture_dirs)
        return _texture_index.get(basename_lower)

    return None


def embed_textures(glb_path: Path, model_dir: Path, model, texture_dirs: list[Path] | None = None, double_sided: bool = False) -> None:
    """Embed all TMD material textures into a GLB file."""
    gltf = GLTF2().load(str(glb_path))
    blob = bytearray(gltf.binary_blob())

    gltf.images = gltf.images or []
    gltf.samplers = gltf.samplers or []
    gltf.textures = gltf.textures or []
    gltf.materials = gltf.materials or []

    if not gltf.samplers:
        gltf.samplers.append(Sampler())

    mat_map = {}
    for mat_idx, tmd_mat in enumerate(model.materials):
        tex_name = tmd_mat.texture_filename
        if not tex_name:
            continue

        # Extract basename from Windows-style paths like ..\Texture\foo.bmp
        tex_basename = tex_name.replace("\\", "/").split("/")[-1]

        # Search model_dir first, then texture_dirs
        tex_path = _find_texture(tex_basename, model_dir, texture_dirs)
        if tex_path is None:
            continue

        img = Image.open(tex_path).convert("RGBA")

        # Detect magenta color-key transparency (R>240, G<20, B>240)
        arr = np.array(img)
        magenta_mask = (arr[:, :, 0] > 240) & (arr[:, :, 1] < 20) & (arr[:, :, 2] > 240)
        has_colorkey = magenta_mask.sum() > (arr.shape[0] * arr.shape[1] * 0.01)

        if has_colorkey:
            arr[magenta_mask, 3] = 0  # Set alpha to 0 for magenta pixels
            img = Image.fromarray(arr, "RGBA")

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

        # Use alpha masking for color-keyed textures
        alpha_mode = "MASK" if has_colorkey else "OPAQUE"
        mat_kwargs = {}
        if has_colorkey:
            mat_kwargs["alphaCutoff"] = 0.5
            mat_kwargs["doubleSided"] = True
        elif double_sided:
            mat_kwargs["doubleSided"] = True

        gltf_mat_idx = len(gltf.materials)
        gltf.materials.append(Material(
            name=tmd_mat.name or Path(tex_basename).stem,
            alphaMode=alpha_mode,
            pbrMetallicRoughness=PbrMetallicRoughness(
                baseColorTexture=TextureInfo(index=tex_idx),
                metallicFactor=0.0,
                roughnessFactor=1.0,
            ),
            **mat_kwargs,
        ))
        mat_map[mat_idx] = gltf_mat_idx

    if gltf.meshes and mat_map:
        prim_mat_list = []
        for mesh in model.meshes:
            unique_mats = set(mesh.vertex_materials.values()) if mesh.vertex_materials else set()
            if len(unique_mats) > 1:
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


def correct_mlib_rotations(tmd, mlib, only_tmd_indices: set[int] | None = None) -> None:
    """Pre-correct MLIB rotation data to match TMD rest-pose rotations.

    For bones where TMD and MLIB rest-pose rotations differ, compute a
    per-bone correction and apply it to ALL animation frames in-place.

    If only_tmd_indices is provided, only correct those specific TMD bone indices.
    This is useful for fixing equip bone misalignment without affecting the
    rest of the skeleton.
    """
    parent_map = _build_parent_map(tmd, mlib)
    t2m = _build_tmd_to_mlib_map(tmd, mlib)

    world_rot = []
    for bone in tmd.bones:
        R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
        R = _normalize_rotation_matrix(R)
        world_rot.append(_rotation_matrix_to_quaternion(R))

    ref_motion = None
    for motion in mlib.motions:
        if "stand" in motion.name:
            ref_motion = motion
            break
    if ref_motion is None and mlib.motions:
        ref_motion = mlib.motions[0]
    if ref_motion is None:
        return

    corrections = {}
    for tmd_idx in range(len(tmd.bones)):
        if only_tmd_indices is not None and tmd_idx not in only_tmd_indices:
            continue

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


def _euler_to_quat(rx: float, ry: float, rz: float) -> list[float]:
    """Convert euler angles (degrees) to quaternion [x,y,z,w]."""
    rx, ry, rz = np.radians(rx), np.radians(ry), np.radians(rz)
    cx, sx = np.cos(rx/2), np.sin(rx/2)
    cy, sy = np.cos(ry/2), np.sin(ry/2)
    cz, sz = np.cos(rz/2), np.sin(rz/2)
    return [
        sx*cy*cz - cx*sy*sz,
        cx*sy*cz + sx*cy*sz,
        cx*cy*sz - sx*sy*cz,
        cx*cy*cz + sx*sy*sz,
    ]


def _apply_bone_tweaks(mlib, t2m: dict, tweaks: dict[int, dict]) -> None:
    """Apply per-bone rotation/position tweaks to MLIB animation data.

    tweaks: {tmd_idx: {"rot": [rx, ry, rz]}} — euler degrees, applied to all frames.
    Only modifies in-memory data.
    """
    for tmd_idx, tweak in tweaks.items():
        mlib_idx = t2m.get(tmd_idx)
        if mlib_idx is None:
            continue

        if "rot" in tweak:
            extra_q = _euler_to_quat(*tweak["rot"])
            for motion in mlib.motions:
                for frame in range(motion.frame_count):
                    if mlib_idx >= motion.bone_count:
                        continue
                    r = motion.rotations[frame][mlib_idx]
                    q = [r.x, r.y, r.z, r.w]
                    # Post-multiply: rotate in bone-local space (not world)
                    result = _quat_normalize(_quat_multiply(q, extra_q))
                    motion.rotations[frame][mlib_idx] = Quaternion(
                        w=result[3], x=result[0], y=result[1], z=result[2],
                    )


def export_model(
    model_id: str, model_dir: Path, output_dir: Path,
    correction_ids: set[str] | None = None,
    force_tmd_scale_ids: set[str] | None = None,
    smooth_bone_overrides: dict[str, set[int]] | None = None,
    equip_correction: dict[str, set[int]] | None = None,
    bone_tweaks: dict[str, dict[int, dict]] | None = None,
    skip_reparent_ids: set[str] | None = None,
) -> tuple[bool, str]:
    """Export a single TMD+MLIB model to GLB with embedded textures."""
    tmd_path = model_dir / f"{model_id}.TMD"
    mlib_path = model_dir / f"{model_id}.mlib"

    if not tmd_path.exists() or not mlib_path.exists():
        return False, f"Missing TMD or MLIB for {model_id}"

    try:
        tmd = TMDParser().parse(tmd_path)
        mlib = MLIBParser().parse(mlib_path)

        if correction_ids and model_id in correction_ids:
            correct_mlib_rotations(tmd, mlib)

        # Equip-only rotation correction (fix specific bones without affecting skeleton)
        if equip_correction and model_id in equip_correction:
            correct_mlib_rotations(tmd, mlib, only_tmd_indices=equip_correction[model_id])

        # Per-bone tweaks (rotation adjustments to MLIB data, position to skeleton)
        pos_tweaks = {}
        if bone_tweaks and model_id in bone_tweaks:
            model_tweaks = bone_tweaks[model_id]
            # Rotation tweaks modify MLIB data
            rot_tweaks = {k: v for k, v in model_tweaks.items() if "rot" in v}
            if rot_tweaks:
                t2m = _build_tmd_to_mlib_map(tmd, mlib)
                _apply_bone_tweaks(mlib, t2m, rot_tweaks)
            # Position tweaks passed to skeleton builder
            for bone_idx, tweak in model_tweaks.items():
                if "pos" in tweak:
                    pos_tweaks[bone_idx] = tweak["pos"]

        glb_path = output_dir / f"{model_id}.glb"
        smooth_indices = smooth_bone_overrides.get(model_id) if smooth_bone_overrides else None
        export_with_animations(
            tmd, mlib, glb_path,
            animation_names=None, validate=False, v_flip=False,
            anim_correction=True, split_materials=True,
            force_tmd_scale=bool(force_tmd_scale_ids and model_id in force_tmd_scale_ids),
            smooth_bone_indices=smooth_indices,
            pos_tweaks=pos_tweaks if pos_tweaks else None,
            skip_reparent=bool(skip_reparent_ids and model_id in skip_reparent_ids),
        )

        embed_textures(glb_path, model_dir, tmd)

        glb_size = glb_path.stat().st_size / 1024
        anim_count = len(mlib.motions)
        return True, f"{model_id}: {glb_size:.0f}KB, {len(tmd.bones)} bones, {anim_count} anims"
    except Exception as e:
        return False, f"{model_id}: ERROR - {e}"
