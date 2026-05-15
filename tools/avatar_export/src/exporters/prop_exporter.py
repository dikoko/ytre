"""
Prop Exporter — Static mesh with multi-material support.

Exports TMD terrain props (buildings, trees, furniture, etc.) to GLB.
No skeleton or animation — static meshes only.

Key differences from mesh_exporter.py:
- Splits meshes by per-vertex material (multi-material support)
- Names materials mat_{texture_basename} for texture resolution
- No UV V-flip by default (same as monsters/NPCs)
- Root node named after prop_id

Key differences from animation_exporter.py:
- No skeleton, skin, or animation data
- No JOINTS_0 or WEIGHTS_0 attributes
"""

from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2, Asset, Scene, Node, Mesh, Primitive, Attributes,
    Accessor, BufferView, Buffer,
    UNSIGNED_SHORT, UNSIGNED_INT, FLOAT, SCALAR, VEC2, VEC3,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDModel


def _split_mesh_by_material(mesh) -> list[tuple[int, list]]:
    """Split a mesh's faces into groups by vertex material index.

    Returns list of (material_index, face_list) tuples.
    Reuses the same logic as animation_exporter._split_mesh_by_material.
    """
    if not mesh.vertex_materials:
        return [(mesh.material_index, mesh.faces)]

    unique_mats = set(mesh.vertex_materials.values())
    if len(unique_mats) <= 1:
        mat_idx = next(iter(unique_mats)) if unique_mats else mesh.material_index
        return [(mat_idx, mesh.faces)]

    mat_faces: dict[int, list] = {}
    for face in mesh.faces:
        face_mat = mesh.vertex_materials.get(face[0], mesh.material_index)
        mat_faces.setdefault(face_mat, []).append(face)

    return sorted(mat_faces.items())


def _build_prop_primitive(
    gltf: GLTF2,
    buf: bytearray,
    mesh,
    face_list: list,
    v_flip: bool,
) -> Primitive:
    """Build a GLTF Primitive from a subset of faces — no skinning data."""
    # Collect unique vertices, build re-index map
    old_indices = set()
    for face in face_list:
        old_indices.update(face)
    old_to_new = {old: new for new, old in enumerate(sorted(old_indices))}

    positions = []
    normals_list = []
    uvs = []

    for old_idx in sorted(old_indices):
        v = mesh.vertices[old_idx]
        positions.extend([v.x, v.y, -v.z])
        n = mesh.normals[old_idx]
        normals_list.extend([-n.x, -n.y, n.z])
        uv = mesh.uvs[old_idx]
        uvs.extend([uv.u, 1.0 - uv.v if v_flip else uv.v])

    # Re-indexed face indices — keep D3D winding (CW), rely on doubleSided=True.
    # Reversing winding breaks lighting on 3D props (stands, buildings) by making
    # the inside face the "front" face. Flat ground props (track, field) are visible
    # via doubleSided rendering without needing reversed winding.
    indices = []
    for face in face_list:
        indices.extend([old_to_new[face[0]], old_to_new[face[1]], old_to_new[face[2]]])

    vertex_count = len(old_to_new)
    pos_array = np.array(positions, dtype=np.float32).reshape(-1, 3)

    # Pack buffers
    pos_bin = np.array(positions, dtype=np.float32).tobytes()
    pos_offset = len(buf); buf.extend(pos_bin)

    norm_bin = np.array(normals_list, dtype=np.float32).tobytes()
    norm_offset = len(buf); buf.extend(norm_bin)

    uv_bin = np.array(uvs, dtype=np.float32).tobytes()
    uv_offset = len(buf); buf.extend(uv_bin)

    # Use uint32 if vertex count exceeds uint16 range
    if vertex_count > 65535:
        idx_bin = np.array(indices, dtype=np.uint32).tobytes()
        idx_component = UNSIGNED_INT
    else:
        idx_bin = np.array(indices, dtype=np.uint16).tobytes()
        idx_component = UNSIGNED_SHORT

    idx_offset = len(buf); buf.extend(idx_bin)

    # Buffer views (4: pos, norm, uv, idx)
    bv_start = len(gltf.bufferViews)
    gltf.bufferViews.extend([
        BufferView(buffer=0, byteOffset=pos_offset, byteLength=len(pos_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=norm_offset, byteLength=len(norm_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=uv_offset, byteLength=len(uv_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=idx_offset, byteLength=len(idx_bin), target=ELEMENT_ARRAY_BUFFER),
    ])

    # Accessors (4: pos, norm, uv, idx)
    acc_start = len(gltf.accessors)
    gltf.accessors.extend([
        Accessor(
            bufferView=bv_start + 0, componentType=FLOAT, count=vertex_count, type=VEC3,
            min=pos_array.min(axis=0).tolist(), max=pos_array.max(axis=0).tolist(),
        ),
        Accessor(bufferView=bv_start + 1, componentType=FLOAT, count=vertex_count, type=VEC3),
        Accessor(bufferView=bv_start + 2, componentType=FLOAT, count=vertex_count, type=VEC2),
        Accessor(bufferView=bv_start + 3, componentType=idx_component, count=len(indices), type=SCALAR),
    ])

    return Primitive(
        attributes=Attributes(
            POSITION=acc_start + 0,
            NORMAL=acc_start + 1,
            TEXCOORD_0=acc_start + 2,
        ),
        indices=acc_start + 3,
    )


def export_prop(
    model: TMDModel,
    output_path: Path | str,
    prop_id: str = "prop",
    v_flip: bool = False,
) -> None:
    """Export TMD prop model as static GLB with multi-material support.

    Args:
        model: Parsed TMD model
        output_path: Path to output GLB file
        prop_id: Name for the root node (used in Godot scene tree)
        v_flip: Apply UV V-flip (False for props, same as monsters/NPCs)
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.prop_exporter"))
    buf = bytearray()

    primitives = []
    for mesh in model.meshes:
        mat_groups = _split_mesh_by_material(mesh)
        for _mat_idx, face_list in mat_groups:
            prim = _build_prop_primitive(gltf, buf, mesh, face_list, v_flip)
            primitives.append(prim)

    gltf_mesh = Mesh(name=f"{prop_id}_mesh", primitives=primitives)
    gltf.meshes.append(gltf_mesh)

    node = Node(name=prop_id, mesh=0)
    gltf.nodes.append(node)

    scene = Scene(nodes=[0])
    gltf.scenes.append(scene)
    gltf.scene = 0

    gltf.buffers.append(Buffer(byteLength=len(buf)))
    gltf.set_binary_blob(bytes(buf))
    gltf.save_binary(str(output_path))
