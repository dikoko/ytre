"""
Skeleton Exporter

Exports TMD mesh with skeleton binding (no animations).
Uses MLIB for bone hierarchy.

Coordinate conversion (TMD → GLTF):
- Position: [x, y, z] (no conversion - TMD is GLTF-compatible)
- Normal: [x, y, z] (no conversion)
- UV: [u, 1-v] (V-flip for texture orientation)
- Faces: [v0, v1, v2] (original winding)
- Bone positions: [x, y, z] (no conversion)
"""

import base64
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2, Asset, Scene, Node, Mesh, Primitive, Attributes,
    Accessor, BufferView, Buffer, Skin,
    UNSIGNED_SHORT, UNSIGNED_INT, FLOAT, SCALAR, VEC2, VEC3, VEC4, MAT4,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDModel
from src.parsers.mlib_parser import MLIBFile
from src.validators.mesh_validator import validate_mesh
from src.validators.skeleton_validator import validate_skeleton


# Arm bones that use MLIB IBMs (mesh transformed to MLIB space by V83)
ARM_BONES = {
    "@ClavicleL", "@Arm1L", "@Arm2L", "@HandL",
    "@ClavicleR", "@Arm1R", "@Arm2R", "@HandR",
    "@Finger1L", "@Finger2L", "@Finger3L", "@Finger4L",
    "@Finger1R", "@Finger2R", "@Finger3R", "@Finger4R",
}


@dataclass
class ExportContext:
    """Context for building GLTF."""
    gltf: GLTF2
    buffer: bytearray
    bone_node_indices: list[int] = field(default_factory=list)
    mlib_to_tmd: dict[int, int] = field(default_factory=dict)


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


def _quat_to_rotation_matrix(q: list[float]) -> np.ndarray:
    """Convert quaternion [x, y, z, w] to 3x3 rotation matrix."""
    x, y, z, w = q
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z

    return np.array([
        [1 - 2*(yy + zz), 2*(xy - wz), 2*(xz + wy)],
        [2*(xy + wz), 1 - 2*(xx + zz), 2*(yz - wx)],
        [2*(xz - wy), 2*(yz + wx), 1 - 2*(xx + yy)],
    ])


def _build_parent_map(model: TMDModel, mlib: MLIBFile) -> dict[int, int]:
    """Build parent map using MLIB hierarchy."""
    tmd_name_to_idx = {b.name.strip(): i for i, b in enumerate(model.bones)}
    mlib_name_to_idx = {b.name.strip(): i for i, b in enumerate(mlib.bones)}

    parent_map = {}
    for tmd_idx, tmd_bone in enumerate(model.bones):
        mlib_idx = mlib_name_to_idx.get(tmd_bone.name.strip())
        if mlib_idx is not None and mlib_idx < len(mlib.bones):
            mlib_parent_idx = mlib.bones[mlib_idx].parent_id
            if mlib_parent_idx >= 0 and mlib_parent_idx < len(mlib.bones):
                mlib_parent_name = mlib.bones[mlib_parent_idx].name.strip()
                tmd_parent_idx = tmd_name_to_idx.get(mlib_parent_name, -1)
                parent_map[tmd_idx] = tmd_parent_idx
            else:
                parent_map[tmd_idx] = -1
        else:
            parent_map[tmd_idx] = -1

    return parent_map


def _build_mlib_to_tmd_map(model: TMDModel, mlib: MLIBFile) -> dict[int, int]:
    """Build MLIB bone index to TMD bone index mapping."""
    tmd_name_to_idx = {b.name.strip(): i for i, b in enumerate(model.bones)}
    mlib_to_tmd = {}
    for mlib_idx, mlib_bone in enumerate(mlib.bones):
        tmd_idx = tmd_name_to_idx.get(mlib_bone.name.strip(), -1)
        if tmd_idx >= 0:
            mlib_to_tmd[mlib_idx] = tmd_idx
    return mlib_to_tmd


def _quat_conjugate(q: list[float]) -> list[float]:
    """Conjugate of quaternion [x, y, z, w]."""
    return [-q[0], -q[1], -q[2], q[3]]


def _quat_multiply(q1: list[float], q2: list[float]) -> list[float]:
    """Multiply two quaternions [x, y, z, w]."""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return [
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
    ]


def _rotate_vector_by_quat(v: list[float], q: list[float]) -> list[float]:
    """Rotate vector v by quaternion q."""
    vq = [v[0], v[1], v[2], 0]
    q_inv = _quat_conjugate(q)
    result = _quat_multiply(_quat_multiply(q, vq), q_inv)
    return [result[0], result[1], result[2]]


def _build_skeleton(ctx: ExportContext, model: TMDModel, mlib: MLIBFile) -> int:
    """Build skeleton nodes and return skin index."""
    gltf = ctx.gltf
    parent_map = _build_parent_map(model, mlib)

    # Get world transforms (no X-mirror - TMD is compatible with GLTF)
    world_pos = []
    world_rot = []  # [x, y, z, w]
    for bone in model.bones:
        t = [
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            bone.world_transform.translation.z,
        ]
        R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
        q = _rotation_matrix_to_quaternion(R)
        world_pos.append(t)
        world_rot.append(q)

    # Compute LOCAL transforms from world transforms
    # local_pos = parent_rot^-1 * (world_pos - parent_pos)
    # local_rot = parent_rot^-1 * world_rot
    local_pos = []
    local_rot = []
    for bone_idx in range(len(model.bones)):
        parent_idx = parent_map.get(bone_idx, -1)
        if parent_idx < 0:
            # Root bone: local = world
            local_pos.append(world_pos[bone_idx])
            local_rot.append(world_rot[bone_idx])
        else:
            # Child bone: compute relative to parent
            parent_rot_inv = _quat_conjugate(world_rot[parent_idx])

            # Local position
            diff = [
                world_pos[bone_idx][0] - world_pos[parent_idx][0],
                world_pos[bone_idx][1] - world_pos[parent_idx][1],
                world_pos[bone_idx][2] - world_pos[parent_idx][2],
            ]
            lp = _rotate_vector_by_quat(diff, parent_rot_inv)
            local_pos.append(lp)

            # Local rotation
            lr = _quat_multiply(parent_rot_inv, world_rot[bone_idx])
            local_rot.append(lr)

    # Create armature node
    armature_node = Node(name="Armature")
    gltf.nodes.append(armature_node)
    armature_idx = len(gltf.nodes) - 1

    # Create bone nodes with LOCAL transforms
    ctx.bone_node_indices = []
    for i, bone in enumerate(model.bones):
        node = Node(
            name=bone.name.strip(),
            translation=local_pos[i],
            rotation=local_rot[i],
        )
        gltf.nodes.append(node)
        ctx.bone_node_indices.append(len(gltf.nodes) - 1)

    # Set up parent-child relationships
    root_bones = []
    for bone_idx in range(len(model.bones)):
        parent_idx = parent_map.get(bone_idx, -1)
        node_idx = ctx.bone_node_indices[bone_idx]

        if parent_idx < 0 or parent_idx >= len(model.bones):
            # Root bone
            if armature_node.children is None:
                armature_node.children = []
            armature_node.children.append(node_idx)
            root_bones.append(node_idx)
        else:
            # Non-root: child of parent
            parent_node_idx = ctx.bone_node_indices[parent_idx]
            if gltf.nodes[parent_node_idx].children is None:
                gltf.nodes[parent_node_idx].children = []
            gltf.nodes[parent_node_idx].children.append(node_idx)

    # Build inverse bind matrices
    ibm_data = _build_inverse_bind_matrices(model, mlib)

    # Add IBM accessor
    ibm_bin = np.array(ibm_data, dtype=np.float32).tobytes()
    ibm_offset = len(ctx.buffer)
    ctx.buffer.extend(ibm_bin)

    bv = BufferView(buffer=0, byteOffset=ibm_offset, byteLength=len(ibm_bin))
    gltf.bufferViews.append(bv)
    bv_idx = len(gltf.bufferViews) - 1

    acc = Accessor(
        bufferView=bv_idx,
        componentType=FLOAT,
        count=len(model.bones),
        type=MAT4,
    )
    gltf.accessors.append(acc)
    ibm_accessor = len(gltf.accessors) - 1

    # Create skin
    skin = Skin(
        name="AvatarSkin",
        joints=ctx.bone_node_indices,
        skeleton=armature_idx,
        inverseBindMatrices=ibm_accessor,
    )
    gltf.skins.append(skin)

    return armature_idx


def _build_inverse_bind_matrices(model: TMDModel, mlib: MLIBFile) -> list[float]:
    """Build inverse bind matrices from TMD world transforms."""
    ibm_data = []

    for bone_idx, bone in enumerate(model.bones):
        # Get world transform (no X-mirror)
        pos = [
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            bone.world_transform.translation.z,
        ]
        R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T

        # Build IBM: inverse of world transform
        # IBM = [R^T | -R^T * t]
        R_inv = R.T
        t_inv = -R_inv @ np.array(pos)

        # Column-major 4x4 matrix
        ibm = [
            R_inv[0, 0], R_inv[1, 0], R_inv[2, 0], 0.0,
            R_inv[0, 1], R_inv[1, 1], R_inv[2, 1], 0.0,
            R_inv[0, 2], R_inv[1, 2], R_inv[2, 2], 0.0,
            t_inv[0], t_inv[1], t_inv[2], 1.0,
        ]
        ibm_data.extend(ibm)

    return ibm_data


def _build_skinning_data(ctx: ExportContext, model: TMDModel) -> tuple[list[int], list[float]]:
    """Build JOINTS_0 and WEIGHTS_0 data from TMD skinning."""
    joints = []
    weights = []

    mesh = model.meshes[0]  # Assume single mesh
    vertex_count = len(mesh.vertices)

    for v_idx in range(vertex_count):
        v_weights = mesh.vertex_skinning.get(v_idx)

        if v_weights:
            # Sort by weight (descending) and take up to 4
            sorted_weights = sorted(v_weights, key=lambda x: -x[1])[:4]

            # Pad to 4 entries
            while len(sorted_weights) < 4:
                sorted_weights.append((0, 0.0))

            # Normalize weights to sum to 1.0
            total_weight = sum(w for _, w in sorted_weights)
            if total_weight > 0:
                sorted_weights = [(b, w / total_weight) for b, w in sorted_weights]

            # Convert MLIB bone indices to TMD bone indices
            for mlib_bone_idx, weight in sorted_weights:
                tmd_bone_idx = ctx.mlib_to_tmd.get(mlib_bone_idx, 0)
                joints.append(tmd_bone_idx)
                weights.append(weight)
        else:
            # Fallback - bind to root bone
            joints.extend([0, 0, 0, 0])
            weights.extend([1.0, 0.0, 0.0, 0.0])

    return joints, weights


def export_with_skeleton(
    model: TMDModel,
    mlib: MLIBFile,
    output_path: Path | str,
    validate: bool = True,
) -> None:
    """
    Export TMD model with skeleton as GLB (no animations).

    Args:
        model: Parsed TMD model
        mlib: Parsed MLIB file (for hierarchy)
        output_path: Path to output GLB file
        validate: Run validation before export
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if validate:
        result = validate_mesh(model)
        if not result.valid:
            raise ValueError(f"Mesh validation failed: {result.message}")
        result = validate_skeleton(model)
        if not result.valid:
            raise ValueError(f"Skeleton validation failed: {result.message}")

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.skeleton_exporter"))
    ctx = ExportContext(gltf=gltf, buffer=bytearray())
    ctx.mlib_to_tmd = _build_mlib_to_tmd_map(model, mlib)

    # Build skeleton first
    armature_idx = _build_skeleton(ctx, model, mlib)

    # Build mesh (no X-mirror - TMD is compatible with GLTF)
    mesh = model.meshes[0]

    positions = []
    for v in mesh.vertices:
        positions.extend([v.x, v.y, v.z])

    normals = []
    for n in mesh.normals:
        normals.extend([n.x, n.y, n.z])

    # V-flip UVs (still needed for texture orientation)
    uvs = []
    for uv in mesh.uvs:
        uvs.extend([uv.u, 1.0 - uv.v])

    # Original face winding (no reversal)
    indices = []
    for face in mesh.faces:
        indices.extend([face[0], face[1], face[2]])

    # Build skinning data
    joints_data, weights_data = _build_skinning_data(ctx, model)

    # Calculate bounds
    pos_array = np.array(positions, dtype=np.float32).reshape(-1, 3)
    min_bound = pos_array.min(axis=0).tolist()
    max_bound = pos_array.max(axis=0).tolist()

    # Pack data into buffer
    vertex_count = len(mesh.vertices)

    pos_bin = np.array(positions, dtype=np.float32).tobytes()
    pos_offset = len(ctx.buffer)
    ctx.buffer.extend(pos_bin)

    norm_bin = np.array(normals, dtype=np.float32).tobytes()
    norm_offset = len(ctx.buffer)
    ctx.buffer.extend(norm_bin)

    uv_bin = np.array(uvs, dtype=np.float32).tobytes()
    uv_offset = len(ctx.buffer)
    ctx.buffer.extend(uv_bin)

    joints_bin = np.array(joints_data, dtype=np.uint16).tobytes()
    joints_offset = len(ctx.buffer)
    ctx.buffer.extend(joints_bin)

    weights_bin = np.array(weights_data, dtype=np.float32).tobytes()
    weights_offset = len(ctx.buffer)
    ctx.buffer.extend(weights_bin)

    idx_bin = np.array(indices, dtype=np.uint16).tobytes()
    idx_offset = len(ctx.buffer)
    ctx.buffer.extend(idx_bin)

    # Create buffer views
    bv_start = len(gltf.bufferViews)
    gltf.bufferViews.extend([
        BufferView(buffer=0, byteOffset=pos_offset, byteLength=len(pos_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=norm_offset, byteLength=len(norm_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=uv_offset, byteLength=len(uv_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=joints_offset, byteLength=len(joints_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=weights_offset, byteLength=len(weights_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=idx_offset, byteLength=len(idx_bin), target=ELEMENT_ARRAY_BUFFER),
    ])

    # Create accessors
    acc_start = len(gltf.accessors)
    gltf.accessors.extend([
        Accessor(bufferView=bv_start + 0, componentType=FLOAT, count=vertex_count, type=VEC3, min=min_bound, max=max_bound),
        Accessor(bufferView=bv_start + 1, componentType=FLOAT, count=vertex_count, type=VEC3),
        Accessor(bufferView=bv_start + 2, componentType=FLOAT, count=vertex_count, type=VEC2),
        Accessor(bufferView=bv_start + 3, componentType=UNSIGNED_SHORT, count=vertex_count, type=VEC4),
        Accessor(bufferView=bv_start + 4, componentType=FLOAT, count=vertex_count, type=VEC4),
        Accessor(bufferView=bv_start + 5, componentType=UNSIGNED_SHORT, count=len(indices), type=SCALAR),
    ])

    # Create mesh
    gltf_mesh = Mesh(
        name="avatar_mesh",
        primitives=[Primitive(
            attributes=Attributes(
                POSITION=acc_start + 0,
                NORMAL=acc_start + 1,
                TEXCOORD_0=acc_start + 2,
                JOINTS_0=acc_start + 3,
                WEIGHTS_0=acc_start + 4,
            ),
            indices=acc_start + 5,
        )],
    )
    gltf.meshes.append(gltf_mesh)

    # Create mesh node with skin
    mesh_node = Node(name="avatar", mesh=0, skin=0)
    gltf.nodes.append(mesh_node)
    mesh_node_idx = len(gltf.nodes) - 1

    # Create scene
    scene = Scene(nodes=[armature_idx, mesh_node_idx])
    gltf.scenes.append(scene)
    gltf.scene = 0

    # Finalize buffer
    gltf.buffers.append(Buffer(
        byteLength=len(ctx.buffer),
        uri="data:application/octet-stream;base64," + _base64_encode(bytes(ctx.buffer)),
    ))

    gltf.save(str(output_path))
