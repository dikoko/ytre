"""
Shared export logic for prop texture embedding.

Embeds BMP/TGA textures from TMD models into GLB files with
correct material assignment, color-key transparency, and double-sided support.
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


# Keyed on the texture_dirs tuple: a single unkeyed cache poisoned callers
# that passed a different dir list than whoever populated it first (e.g.
# SKILL/TMD glow textures silently unresolvable after a [TEXTURE_IRD]-only
# call warmed the cache).
_texture_index_cache: dict[tuple, dict[str, Path]] = {}


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
    basename_lower = basename.lower()

    # Search model directory first (small, always fresh)
    for f in model_dir.iterdir():
        if f.is_file() and f.name.lower() == basename_lower:
            return f

    # Search texture directories via a per-dir-list cached index
    if texture_dirs:
        key = tuple(str(d) for d in texture_dirs)
        index = _texture_index_cache.get(key)
        if index is None:
            index = _build_texture_index(texture_dirs)
            _texture_index_cache[key] = index
        return index.get(basename_lower)

    return None


def texture_has_colorkey(tex_path: Path) -> bool:
    """Detect magenta color-key transparency in a texture (>1% magenta pixels).

    Magenta = R>240, G<20, B>240. Same rule used by embed_textures for
    alpha-masking; exposed standalone so callers (e.g. the prop export script)
    can decide double-sidedness before textures are embedded.
    """
    img = Image.open(tex_path).convert("RGBA")
    arr = np.array(img)
    magenta_mask = (arr[:, :, 0] > 240) & (arr[:, :, 1] < 20) & (arr[:, :, 2] > 240)
    return bool(magenta_mask.sum() > (arr.shape[0] * arr.shape[1] * 0.01))


def embed_textures(glb_path: Path, model_dir: Path, model, texture_dirs: list[Path] | None = None) -> None:
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
        has_colorkey = texture_has_colorkey(tex_path)

        if has_colorkey:
            arr = np.array(img)
            magenta_mask = (arr[:, :, 0] > 240) & (arr[:, :, 1] < 20) & (arr[:, :, 2] > 240)
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
        elif tmd_mat.two_sided:
            # The TMD per-material two-sided flag disables culling in the
            # original client; materials without it were backface-culled.
            mat_kwargs["doubleSided"] = True

        if tmd_mat.self_illumination > 0:
            # A self-illumination value > 0 routes the mesh to the ADDITIVE
            # full-bright pass in the original client (lights off, ambient
            # white, src-alpha + one blending). Carried through the GLB
            # as emissiveFactor so prop_lighting.gd can swap in the additive
            # fixed-function material at runtime. The magnitude is informative
            # only — the original client checks strictly > 0.
            si = min(1.0, tmd_mat.self_illumination)
            mat_kwargs["emissiveFactor"] = [si, si, si]

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

        # Walk primitives across ALL meshes in order — export_prop chunks
        # >256-primitive props into multiple meshes (Godot's per-mesh
        # surface cap), and prim_mat_list follows that same global order.
        all_prims = [p for mesh in gltf.meshes for p in mesh.primitives]
        for prim_idx, prim in enumerate(all_prims):
            if prim_idx < len(prim_mat_list):
                tmd_mat_idx = prim_mat_list[prim_idx]
                if tmd_mat_idx in mat_map:
                    prim.material = mat_map[tmd_mat_idx]
                elif 0 in mat_map:
                    prim.material = mat_map[0]

    gltf.buffers[0].byteLength = len(blob)
    gltf.set_binary_blob(bytes(blob))
    gltf.save(str(glb_path))
