"""
Axis Rotation Visualizer

Creates procedural animations that rotate target bones around X, Y, Z axes
to visualize the bone coordinate system.

Output: GLB with animations debug_rot_X, debug_rot_Y, debug_rot_Z
Each animation rotates Spine1 and Spine2 by 45 degrees around the specified axis.

Visual cues:
- Spine1: Large RED cube
- Spine2: Large BLUE cube
- Other bones: Small gray cubes
"""

import base64
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2, Asset, Scene, Node, Mesh, Primitive, Attributes,
    Accessor, BufferView, Buffer, Material, PbrMetallicRoughness,
    Animation, AnimationChannel, AnimationChannelTarget, AnimationSampler,
    UNSIGNED_SHORT, FLOAT, SCALAR, VEC3, VEC4,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDModel


@dataclass
class ExportContext:
    """Context for building GLTF."""
    gltf: GLTF2
    buffer: bytearray
    bone_node_indices: list[int]  # Maps bone index to node index
    # Mesh indices for different bone types
    small_cube_mesh: int = -1
    spine1_cube_mesh: int = -1
    spine2_cube_mesh: int = -1


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


def _add_accessor(ctx: ExportContext, data: list, accessor_type: str, component_type: int) -> int:
    """Add data as accessor and return accessor index."""
    gltf = ctx.gltf

    if accessor_type == SCALAR:
        arr = np.array(data, dtype=np.float32)
        count = len(data)
    elif accessor_type == VEC3:
        arr = np.array(data, dtype=np.float32)
        count = len(data) // 3
    elif accessor_type == VEC4:
        arr = np.array(data, dtype=np.float32)
        count = len(data) // 4
    else:
        arr = np.array(data, dtype=np.float32)
        count = len(data)

    bin_data = arr.tobytes()
    offset = len(ctx.buffer)
    ctx.buffer.extend(bin_data)

    # Add buffer view
    bv = BufferView(buffer=0, byteOffset=offset, byteLength=len(bin_data))
    gltf.bufferViews.append(bv)
    bv_idx = len(gltf.bufferViews) - 1

    # Add accessor
    acc = Accessor(
        bufferView=bv_idx,
        componentType=component_type,
        count=count,
        type=accessor_type,
    )

    # Set min/max for time accessor
    if accessor_type == SCALAR and count > 0:
        acc.min = [float(min(data))]
        acc.max = [float(max(data))]

    gltf.accessors.append(acc)
    return len(gltf.accessors) - 1


def _create_material(ctx: ExportContext, color: list[float], name: str = "material") -> int:
    """Create a colored material and return material index."""
    gltf = ctx.gltf
    material = Material(
        name=name,
        pbrMetallicRoughness=PbrMetallicRoughness(
            baseColorFactor=color,  # [R, G, B, A]
            metallicFactor=0.0,
            roughnessFactor=0.8,
        ),
    )
    gltf.materials.append(material)
    return len(gltf.materials) - 1


def _create_cube_mesh(ctx: ExportContext, size: float = 0.03, material_idx: int = None) -> int:
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

    # Mesh with optional material
    primitive = Primitive(
        attributes=Attributes(POSITION=acc_v_idx),
        indices=acc_i_idx,
    )
    if material_idx is not None:
        primitive.material = material_idx

    mesh = Mesh(primitives=[primitive])
    gltf.meshes.append(mesh)
    return len(gltf.meshes) - 1


def _build_skeleton_nodes(ctx: ExportContext, model: TMDModel) -> None:
    """Build skeleton nodes from TMD bones with colored cube meshes."""
    gltf = ctx.gltf
    ctx.bone_node_indices = []

    for i, bone in enumerate(model.bones):
        # Extract world transform
        R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
        t = [
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            bone.world_transform.translation.z,
        ]
        q = _rotation_matrix_to_quaternion(R)

        # Select mesh based on bone name
        name = bone.name.strip()
        if name == "@Spine1":
            mesh_idx = ctx.spine1_cube_mesh
        elif name == "@Spine2":
            mesh_idx = ctx.spine2_cube_mesh
        else:
            mesh_idx = ctx.small_cube_mesh

        node = Node(
            name=name,
            translation=t,
            rotation=q,
            mesh=mesh_idx,
        )
        gltf.nodes.append(node)
        ctx.bone_node_indices.append(len(gltf.nodes) - 1)


def _build_axis_animations(ctx: ExportContext, model: TMDModel) -> None:
    """Build procedural animations rotating target bones around X, Y, Z."""
    gltf = ctx.gltf

    # Find target bones (Spine1, Spine2)
    target_bones = ["@Spine1", "@Spine2"]
    target_node_indices = []

    for i, bone in enumerate(model.bones):
        name = bone.name.strip()
        if name in target_bones:
            node_idx = ctx.bone_node_indices[i]
            target_node_indices.append(node_idx)

    if not target_node_indices:
        # Fallback: just use first few bones
        target_node_indices = ctx.bone_node_indices[:2]

    # Create animations for X, Y, Z axes
    axes = [("X", 1, 0, 0), ("Y", 0, 1, 0), ("Z", 0, 0, 1)]

    for axis_name, ax, ay, az in axes:
        anim = Animation(name=f"debug_rot_{axis_name}", channels=[], samplers=[])

        # Times: 0.0 to 1.0 (3 keyframes)
        times = [0.0, 0.5, 1.0]
        time_acc = _add_accessor(ctx, times, SCALAR, FLOAT)

        # Rotations: identity -> +45° -> identity
        q_identity = [0.0, 0.0, 0.0, 1.0]

        # +45 degrees rotation
        ang = math.radians(45.0)
        sin_a = math.sin(ang / 2)
        cos_a = math.cos(ang / 2)
        q_pos = [ax * sin_a, ay * sin_a, az * sin_a, cos_a]

        # Flatten rotation values for all 3 keyframes
        rot_values = []
        rot_values.extend(q_identity)
        rot_values.extend(q_pos)
        rot_values.extend(q_identity)

        rot_acc = _add_accessor(ctx, rot_values, VEC4, FLOAT)

        # Create sampler
        anim.samplers.append(AnimationSampler(input=time_acc, output=rot_acc))

        # Create channels for each target bone
        for target_idx in target_node_indices:
            anim.channels.append(AnimationChannel(
                sampler=len(anim.samplers) - 1,
                target=AnimationChannelTarget(node=target_idx, path="rotation"),
            ))

        gltf.animations.append(anim)


def create_axis_viz(model: TMDModel, output_path: Path | str) -> None:
    """
    Create axis rotation visualization GLB.

    Args:
        model: Parsed TMD model
        output_path: Path to output GLB file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.debug.axis_viz"))
    ctx = ExportContext(gltf=gltf, buffer=bytearray(), bone_node_indices=[])

    # Create materials
    gray_mat = _create_material(ctx, [0.5, 0.5, 0.5, 1.0], "gray")
    red_mat = _create_material(ctx, [1.0, 0.2, 0.2, 1.0], "red_spine1")
    blue_mat = _create_material(ctx, [0.2, 0.4, 1.0, 1.0], "blue_spine2")

    # Create cube meshes with different sizes and colors
    ctx.small_cube_mesh = _create_cube_mesh(ctx, size=0.02, material_idx=gray_mat)
    ctx.spine1_cube_mesh = _create_cube_mesh(ctx, size=0.08, material_idx=red_mat)  # Large RED
    ctx.spine2_cube_mesh = _create_cube_mesh(ctx, size=0.08, material_idx=blue_mat)  # Large BLUE

    # Build skeleton nodes with colored cube meshes (for animation targets)
    _build_skeleton_nodes(ctx, model)

    # Build axis rotation animations
    _build_axis_animations(ctx, model)

    # Create scene with all bone nodes
    scene = Scene(nodes=ctx.bone_node_indices)
    gltf.scenes.append(scene)
    gltf.scene = 0

    # Finalize buffer
    gltf.buffers.append(Buffer(
        byteLength=len(ctx.buffer),
        uri="data:application/octet-stream;base64," + _base64_encode(bytes(ctx.buffer)),
    ))

    gltf.save(str(output_path))
