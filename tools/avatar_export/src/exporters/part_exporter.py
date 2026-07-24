"""
Part Exporter

Exports PRT (avatar part) files to GLTF with mesh geometry, skeleton, and skin.
Parts include the full skeleton from the base model so they can be properly
skinned when imported into Godot.

Key features:
- Mesh geometry: vertices, normals, UVs, faces
- Skin attributes: JOINTS_0, WEIGHTS_0 (4 bone influences per vertex)
- Full skeleton from base model for proper binding
- Skin object with inverse bind matrices

Coordinate conversion (TMD -> GLTF):
- Position: [x, y, z] (no conversion needed)
- Normal: [x, y, z] (no conversion needed)
- UV: [u, v] (no conversion needed)
"""

import base64
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2, Asset, Scene, Node, Mesh, Primitive, Attributes,
    Accessor, BufferView, Buffer, Skin,
    UNSIGNED_SHORT, UNSIGNED_INT, UNSIGNED_BYTE, FLOAT,
    SCALAR, VEC2, VEC3, VEC4, MAT4,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDModel
from src.parsers.mlib_parser import MLIBFile


def _build_mlib_to_tmd_mapping(base_model: TMDModel, mlib: MLIBFile) -> dict[int, int]:
    """Build mapping from MLIB bone indices to TMD bone indices by bone name."""
    tmd_name_to_idx = {bone.name.strip(): i for i, bone in enumerate(base_model.bones)}
    mlib_to_tmd = {}
    for mlib_idx, mlib_bone in enumerate(mlib.bones):
        mlib_name = mlib_bone.name.strip()
        tmd_idx = tmd_name_to_idx.get(mlib_name, mlib_idx)  # Fall back to same index
        mlib_to_tmd[mlib_idx] = tmd_idx
    return mlib_to_tmd


@dataclass
class ExportContext:
    """Context for building GLTF."""
    gltf: GLTF2
    buffer: bytearray
    bone_node_indices: list[int] = field(default_factory=list)


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
    return [x, y, z, w]


def _quat_conjugate(q: list[float]) -> list[float]:
    """Return conjugate of quaternion [x, y, z, w]."""
    return [-q[0], -q[1], -q[2], q[3]]


def _quat_multiply(a: list[float], b: list[float]) -> list[float]:
    """Multiply two quaternions [x, y, z, w]."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ]


def _rotate_vector_by_quat(v: list[float], q: list[float]) -> list[float]:
    """Rotate vector v by quaternion q."""
    vq = [v[0], v[1], v[2], 0]
    q_inv = _quat_conjugate(q)
    result = _quat_multiply(_quat_multiply(q, vq), q_inv)
    return [result[0], result[1], result[2]]


def _build_parent_map(model: TMDModel) -> dict[int, int]:
    """Build bone parent map from TMD bone hierarchy."""
    parent_map = {}
    for i, bone in enumerate(model.bones):
        if bone.parent_id >= 0 and bone.parent_id < len(model.bones):
            parent_map[i] = bone.parent_id
    return parent_map


def _build_skeleton(ctx: ExportContext, model: TMDModel) -> int:
    """Build skeleton nodes and skin from base model, return armature node index."""
    gltf = ctx.gltf
    parent_map = _build_parent_map(model)

    # Get world transforms
    # LH -> RH mirror: conjugate every world transform by S = diag(1,1,-1)
    S = np.diag([1.0, 1.0, -1.0])
    world_pos = []
    world_rot = []
    for bone in model.bones:
        t = [
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            -bone.world_transform.translation.z,
        ]
        R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
        q = _rotation_matrix_to_quaternion(S @ R @ S)
        world_pos.append(t)
        world_rot.append(q)

    # Compute local transforms
    local_pos = []
    local_rot = []
    for bone_idx in range(len(model.bones)):
        parent_idx = parent_map.get(bone_idx, -1)
        if parent_idx < 0:
            local_pos.append(world_pos[bone_idx])
            local_rot.append(world_rot[bone_idx])
        else:
            parent_rot_inv = _quat_conjugate(world_rot[parent_idx])
            diff = [
                world_pos[bone_idx][0] - world_pos[parent_idx][0],
                world_pos[bone_idx][1] - world_pos[parent_idx][1],
                world_pos[bone_idx][2] - world_pos[parent_idx][2],
            ]
            lp = _rotate_vector_by_quat(diff, parent_rot_inv)
            local_pos.append(lp)
            lr = _quat_multiply(parent_rot_inv, world_rot[bone_idx])
            local_rot.append(lr)

    # Create armature node
    armature_node = Node(name="Armature")
    gltf.nodes.append(armature_node)
    armature_idx = len(gltf.nodes) - 1

    # Create bone nodes
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
    for bone_idx in range(len(model.bones)):
        parent_idx = parent_map.get(bone_idx, -1)
        node_idx = ctx.bone_node_indices[bone_idx]

        if parent_idx < 0 or parent_idx >= len(model.bones):
            if armature_node.children is None:
                armature_node.children = []
            armature_node.children.append(node_idx)
        else:
            parent_node_idx = ctx.bone_node_indices[parent_idx]
            if gltf.nodes[parent_node_idx].children is None:
                gltf.nodes[parent_node_idx].children = []
            gltf.nodes[parent_node_idx].children.append(node_idx)

    # Build inverse bind matrices
    ibm_data = _build_inverse_bind_matrices(model)

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
        name="PartSkin",
        joints=ctx.bone_node_indices,
        skeleton=armature_idx,
        inverseBindMatrices=ibm_accessor,
    )
    gltf.skins.append(skin)

    return armature_idx


def _build_inverse_bind_matrices(model: TMDModel) -> list[float]:
    """Build inverse bind matrices from TMD world transforms."""
    ibm_data = []

    S = np.diag([1.0, 1.0, -1.0])
    for bone in model.bones:
        # LH -> RH mirror, matching the skeleton nodes
        pos = [
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            -bone.world_transform.translation.z,
        ]
        R = S @ np.array(bone.world_transform.rotation.data).reshape(3, 3).T @ S

        # IBM = inverse of world transform
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


def export_part(
    model: TMDModel,
    base_model: TMDModel,
    mlib: MLIBFile,
    output_path: Path | str,
    swp_entry=None,
) -> None:
    """
    Export PRT model as GLB with skeleton and skin from base model.

    PRT files use MLIB bone indices for skinning, but our skeleton uses TMD
    bone order. This function remaps the bone indices appropriately.

    Args:
        model: Parsed TMD/PRT model (the part to export)
        base_model: Parsed base TMD model (male.TMD) for skeleton data
        mlib: Parsed MLIB file for bone index mapping
        output_path: Path to output GLB file
        swp_entry: Optional SwpData for this part. The original client
            overwrites specific part-vertex normals with authored weld
            normals when the part is equipped (boundary shading match with
            the base body); we bake that here at export time.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.part_exporter"))
    ctx = ExportContext(gltf=gltf, buffer=bytearray())

    # Build MLIB -> TMD bone index mapping
    # PRT files use MLIB indices, but our skeleton uses TMD order
    mlib_to_tmd = _build_mlib_to_tmd_mapping(base_model, mlib)

    # Build skeleton from base model FIRST (so bone indices match)
    armature_idx = _build_skeleton(ctx, base_model)

    # Collect all mesh data
    all_positions = []
    all_normals = []
    all_uvs = []
    all_indices = []
    all_joints = []
    all_weights = []
    vertex_offset = 0

    for mesh_idx, mesh in enumerate(model.meshes):
        # Authored weld normals from the .swp replace the part's own normals
        # at seam vertices (applied at equip time by the original client)
        welds = {}
        if swp_entry is not None and mesh_idx < swp_entry.mesh_num:
            welds = dict(swp_entry.get_weld_normals(mesh_idx))

        # Positions/normals Z-negated: LH -> RH mirror
        for v in mesh.vertices:
            all_positions.extend([v.x, v.y, -v.z])

        for n_idx, n in enumerate(mesh.normals):
            if n_idx in welds:
                wx, wy, wz = welds[n_idx]
                all_normals.extend([wx, wy, -wz])
            else:
                all_normals.extend([n.x, n.y, -n.z])

        # UVs (no flip - original TMD UV coordinates)
        for uv in mesh.uvs:
            all_uvs.extend([uv.u, uv.v])

        # Faces: winding reversed (the Z mirror flips triangle orientation)
        for face in mesh.faces:
            all_indices.extend([
                face[0] + vertex_offset,
                face[2] + vertex_offset,
                face[1] + vertex_offset,
            ])

        # Skinning data
        for v_idx in range(len(mesh.vertices)):
            merged_idx = vertex_offset + v_idx

            if merged_idx in mesh.vertex_skinning:
                skin_data = mesh.vertex_skinning[merged_idx]
            elif v_idx in mesh.vertex_skinning:
                skin_data = mesh.vertex_skinning[v_idx]
            else:
                skin_data = [(0, 1.0)]

            joints = [0, 0, 0, 0]
            weights = [0.0, 0.0, 0.0, 0.0]

            for i, (bone_idx, weight) in enumerate(skin_data[:4]):
                # Remap from MLIB index to TMD index
                tmd_idx = mlib_to_tmd.get(bone_idx, bone_idx)
                joints[i] = tmd_idx
                weights[i] = weight

            # Normalize weights
            weight_sum = sum(weights)
            if weight_sum > 0:
                weights = [w / weight_sum for w in weights]
            else:
                weights = [1.0, 0.0, 0.0, 0.0]

            all_joints.extend(joints)
            all_weights.extend(weights)

        vertex_offset += len(mesh.vertices)

    # Calculate position bounds
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

    joints_bin = np.array(all_joints, dtype=np.uint8).tobytes()
    joints_offset = len(ctx.buffer)
    ctx.buffer.extend(joints_bin)

    weights_bin = np.array(all_weights, dtype=np.float32).tobytes()
    weights_offset = len(ctx.buffer)
    ctx.buffer.extend(weights_bin)

    # Pack indices
    vertex_count = len(all_positions) // 3
    if vertex_count > 65535:
        idx_bin = np.array(all_indices, dtype=np.uint32).tobytes()
        idx_component = UNSIGNED_INT
    else:
        idx_bin = np.array(all_indices, dtype=np.uint16).tobytes()
        idx_component = UNSIGNED_SHORT

    idx_offset = len(ctx.buffer)
    ctx.buffer.extend(idx_bin)

    # Buffer view base index (after IBM buffer view)
    bv_base = len(gltf.bufferViews)

    # Create buffer views
    gltf.bufferViews.extend([
        BufferView(buffer=0, byteOffset=pos_offset, byteLength=len(pos_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=norm_offset, byteLength=len(norm_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=uv_offset, byteLength=len(uv_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=joints_offset, byteLength=len(joints_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=weights_offset, byteLength=len(weights_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=idx_offset, byteLength=len(idx_bin), target=ELEMENT_ARRAY_BUFFER),
    ])

    # Accessor base index (after IBM accessor)
    acc_base = len(gltf.accessors)

    # Create accessors
    gltf.accessors.extend([
        # POSITION
        Accessor(
            bufferView=bv_base + 0,
            componentType=FLOAT,
            count=vertex_count,
            type=VEC3,
            min=min_bound,
            max=max_bound,
        ),
        # NORMAL
        Accessor(
            bufferView=bv_base + 1,
            componentType=FLOAT,
            count=vertex_count,
            type=VEC3,
        ),
        # TEXCOORD_0
        Accessor(
            bufferView=bv_base + 2,
            componentType=FLOAT,
            count=vertex_count,
            type=VEC2,
        ),
        # JOINTS_0
        Accessor(
            bufferView=bv_base + 3,
            componentType=UNSIGNED_BYTE,
            count=vertex_count,
            type=VEC4,
        ),
        # WEIGHTS_0
        Accessor(
            bufferView=bv_base + 4,
            componentType=FLOAT,
            count=vertex_count,
            type=VEC4,
        ),
        # Indices
        Accessor(
            bufferView=bv_base + 5,
            componentType=idx_component,
            count=len(all_indices),
            type=SCALAR,
        ),
    ])

    # Create mesh
    mesh = Mesh(
        name="part_mesh",
        primitives=[Primitive(
            attributes=Attributes(
                POSITION=acc_base + 0,
                NORMAL=acc_base + 1,
                TEXCOORD_0=acc_base + 2,
                JOINTS_0=acc_base + 3,
                WEIGHTS_0=acc_base + 4,
            ),
            indices=acc_base + 5,
        )],
    )
    gltf.meshes.append(mesh)

    # Create mesh node with skin reference
    mesh_node = Node(name="part", mesh=0, skin=0)
    gltf.nodes.append(mesh_node)
    mesh_node_idx = len(gltf.nodes) - 1

    # Create scene with armature and mesh
    scene = Scene(nodes=[armature_idx, mesh_node_idx])
    gltf.scenes.append(scene)
    gltf.scene = 0

    # Finalize buffer
    gltf.buffers.append(Buffer(
        byteLength=len(ctx.buffer),
        uri="data:application/octet-stream;base64," + _base64_encode(bytes(ctx.buffer)),
    ))

    gltf.save(str(output_path))
