"""
Skeleton Cube Visualizer

Places 3cm cubes at each bone's world position to visualize the skeleton.
Each cube is positioned and rotated according to the bone's world transform.

Output: GLB with 54 cube nodes representing each bone position.
"""

import base64
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2, Asset, Scene, Node, Mesh, Primitive, Attributes,
    Accessor, BufferView, Buffer,
    UNSIGNED_SHORT, FLOAT, SCALAR, VEC3,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDModel


@dataclass
class ExportContext:
    """Context for building GLTF."""
    gltf: GLTF2
    buffer: bytearray


def _base64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode('utf-8')


def _rotation_matrix_to_quaternion(R: np.ndarray) -> list[float]:
    """Convert 3x3 rotation matrix to quaternion [x, y, z, w]."""
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return [float(x), float(y), float(z), float(w)]


def _create_cube_mesh(ctx: ExportContext, size: float = 0.03) -> int:
    """Create a simple cube mesh and return mesh index."""
    gltf = ctx.gltf
    h = size / 2

    # 8 vertices for cube
    vertices = [
        -h, -h, h,   h, -h, h,   h, h, h,  -h, h, h,   # Front
        -h, -h, -h, -h, h, -h,   h, h, -h,  h, -h, -h,  # Back
    ]
    indices = [
        0, 1, 2, 2, 3, 0,  # Front
        4, 5, 6, 6, 7, 4,  # Back
        3, 2, 6, 6, 5, 3,  # Top
        0, 3, 5, 5, 4, 0,  # Left
        1, 7, 6, 6, 2, 1,  # Right
        4, 7, 1, 1, 0, 4,  # Bottom
    ]

    # Pack vertex data
    v_bin = np.array(vertices, dtype=np.float32).tobytes()
    v_offset = len(ctx.buffer)
    ctx.buffer.extend(v_bin)

    # Pack index data
    i_bin = np.array(indices, dtype=np.uint16).tobytes()
    i_offset = len(ctx.buffer)
    ctx.buffer.extend(i_bin)

    # Buffer views
    bv_v = BufferView(buffer=0, byteOffset=v_offset, byteLength=len(v_bin), target=ARRAY_BUFFER)
    bv_i = BufferView(buffer=0, byteOffset=i_offset, byteLength=len(i_bin), target=ELEMENT_ARRAY_BUFFER)
    gltf.bufferViews.extend([bv_v, bv_i])
    bv_v_idx = len(gltf.bufferViews) - 2
    bv_i_idx = len(gltf.bufferViews) - 1

    # Accessors
    acc_v = Accessor(
        bufferView=bv_v_idx,
        componentType=FLOAT,
        count=8,
        type=VEC3,
        min=[-h, -h, -h],
        max=[h, h, h],
    )
    acc_i = Accessor(
        bufferView=bv_i_idx,
        componentType=UNSIGNED_SHORT,
        count=len(indices),
        type=SCALAR,
    )
    gltf.accessors.extend([acc_v, acc_i])
    acc_v_idx = len(gltf.accessors) - 2
    acc_i_idx = len(gltf.accessors) - 1

    # Mesh
    mesh = Mesh(primitives=[Primitive(
        attributes=Attributes(POSITION=acc_v_idx),
        indices=acc_i_idx,
    )])
    gltf.meshes.append(mesh)
    return len(gltf.meshes) - 1


def create_skeleton_viz(model: TMDModel, output_path: Path | str) -> None:
    """
    Create skeleton cube visualization GLB.

    Each bone is represented by a 3cm cube at its world position.

    Args:
        model: Parsed TMD model
        output_path: Path to output GLB file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.debug.skeleton_viz"))
    ctx = ExportContext(gltf=gltf, buffer=bytearray())

    # Create single cube mesh that all bones will share
    cube_mesh_idx = _create_cube_mesh(ctx, size=0.03)

    # Create a node for each bone
    scene_nodes = []
    for bone in model.bones:
        # Extract world transform
        R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
        t = [
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            bone.world_transform.translation.z,
        ]
        q = _rotation_matrix_to_quaternion(R)

        node = Node(
            name=bone.name.strip(),
            translation=t,
            rotation=q,
            mesh=cube_mesh_idx,
        )
        gltf.nodes.append(node)
        scene_nodes.append(len(gltf.nodes) - 1)

    # Create scene with all bone nodes
    scene = Scene(nodes=scene_nodes)
    gltf.scenes.append(scene)
    gltf.scene = 0

    # Finalize buffer
    gltf.buffers.append(Buffer(
        byteLength=len(ctx.buffer),
        uri="data:application/octet-stream;base64," + _base64_encode(bytes(ctx.buffer)),
    ))

    gltf.save(str(output_path))
