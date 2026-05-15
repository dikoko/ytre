"""
Mesh-Only Exporter

Exports TMD mesh data to GLTF without skeleton or animations.
Used to verify mesh geometry before adding skeletal binding.

Coordinate conversion (TMD → GLTF):
- Position: [x, y, z] (no conversion needed - TMD is GLTF-compatible)
- Normal: [x, y, z] (no conversion needed)
- UV: [u, 1-v] (V-flip for texture orientation)
- Faces: [v0, v1, v2] (original winding)
"""

import base64
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2, Asset, Scene, Node, Mesh, Primitive, Attributes,
    Accessor, BufferView, Buffer,
    UNSIGNED_SHORT, UNSIGNED_INT, FLOAT, SCALAR, VEC2, VEC3,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDModel
from src.validators.mesh_validator import validate_mesh


@dataclass
class ExportContext:
    """Context for building GLTF."""
    gltf: GLTF2
    buffer: bytearray


def _base64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode('utf-8')


def export_mesh_only(
    model: TMDModel,
    output_path: Path | str,
    validate: bool = True,
) -> None:
    """
    Export TMD model as mesh-only GLB (no skeleton).

    Args:
        model: Parsed TMD model
        output_path: Path to output GLB file
        validate: Run validation before export (default True)

    Raises:
        ValueError: If validation fails
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Validate mesh data
    if validate:
        result = validate_mesh(model)
        if not result.valid:
            raise ValueError(f"Mesh validation failed: {result.message}")

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.mesh_exporter"))
    ctx = ExportContext(gltf=gltf, buffer=bytearray())

    # Combine all meshes into one
    all_positions = []
    all_normals = []
    all_uvs = []
    all_indices = []
    vertex_offset = 0

    for mesh in model.meshes:
        # Positions (no conversion - TMD is GLTF-compatible)
        for v in mesh.vertices:
            all_positions.extend([v.x, v.y, v.z])

        # Normals (no conversion)
        for n in mesh.normals:
            all_normals.extend([n.x, n.y, n.z])

        # UVs (V-flip for texture orientation)
        for uv in mesh.uvs:
            all_uvs.extend([uv.u, 1.0 - uv.v])

        # Faces (original winding)
        for face in mesh.faces:
            all_indices.extend([
                face[0] + vertex_offset,
                face[1] + vertex_offset,
                face[2] + vertex_offset,
            ])

        vertex_offset += len(mesh.vertices)

    # Calculate bounds
    positions_array = np.array(all_positions, dtype=np.float32).reshape(-1, 3)
    min_bound = positions_array.min(axis=0).tolist()
    max_bound = positions_array.max(axis=0).tolist()

    # Pack vertex data
    pos_bin = np.array(all_positions, dtype=np.float32).tobytes()
    pos_offset = len(ctx.buffer)
    ctx.buffer.extend(pos_bin)

    norm_bin = np.array(all_normals, dtype=np.float32).tobytes()
    norm_offset = len(ctx.buffer)
    ctx.buffer.extend(norm_bin)

    uv_bin = np.array(all_uvs, dtype=np.float32).tobytes()
    uv_offset = len(ctx.buffer)
    ctx.buffer.extend(uv_bin)

    # Pack index data (use uint32 if needed)
    vertex_count = len(all_positions) // 3
    if vertex_count > 65535:
        idx_bin = np.array(all_indices, dtype=np.uint32).tobytes()
        idx_component = UNSIGNED_INT
    else:
        idx_bin = np.array(all_indices, dtype=np.uint16).tobytes()
        idx_component = UNSIGNED_SHORT

    idx_offset = len(ctx.buffer)
    ctx.buffer.extend(idx_bin)

    # Create buffer views
    gltf.bufferViews.extend([
        BufferView(buffer=0, byteOffset=pos_offset, byteLength=len(pos_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=norm_offset, byteLength=len(norm_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=uv_offset, byteLength=len(uv_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=idx_offset, byteLength=len(idx_bin), target=ELEMENT_ARRAY_BUFFER),
    ])

    # Create accessors
    gltf.accessors.extend([
        Accessor(
            bufferView=0,
            componentType=FLOAT,
            count=vertex_count,
            type=VEC3,
            min=min_bound,
            max=max_bound,
        ),
        Accessor(
            bufferView=1,
            componentType=FLOAT,
            count=vertex_count,
            type=VEC3,
        ),
        Accessor(
            bufferView=2,
            componentType=FLOAT,
            count=vertex_count,
            type=VEC2,
        ),
        Accessor(
            bufferView=3,
            componentType=idx_component,
            count=len(all_indices),
            type=SCALAR,
        ),
    ])

    # Create mesh
    mesh = Mesh(
        name="avatar_mesh",
        primitives=[Primitive(
            attributes=Attributes(
                POSITION=0,
                NORMAL=1,
                TEXCOORD_0=2,
            ),
            indices=3,
        )],
    )
    gltf.meshes.append(mesh)

    # Create node and scene
    node = Node(name="avatar", mesh=0)
    gltf.nodes.append(node)

    scene = Scene(nodes=[0])
    gltf.scenes.append(scene)
    gltf.scene = 0

    # Finalize buffer
    gltf.buffers.append(Buffer(
        byteLength=len(ctx.buffer),
        uri="data:application/octet-stream;base64," + _base64_encode(bytes(ctx.buffer)),
    ))

    gltf.save(str(output_path))
