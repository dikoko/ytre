"""
Region Exporter

Exports TMD mesh split by body regions, each as separate mesh nodes.
All regions share the same skeleton and skin for proper animation.

Based on skeleton_exporter.py with multi-mesh support.
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
from src.exporters.region_config import BodyRegion, get_vertex_region


@dataclass
class RegionMesh:
    """Mesh data for a single body region."""
    region: BodyRegion
    vertex_indices: list[int]  # Original vertex indices in this region
    faces: list[tuple[int, int, int]]  # Face indices (original indices)


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


def split_mesh_by_region(
    model: TMDModel,
    mlib: MLIBFile,
) -> dict[BodyRegion, RegionMesh]:
    """
    Split mesh vertices and faces by body region.

    Args:
        model: Parsed TMD model
        mlib: Parsed MLIB file (for bone name mapping)

    Returns:
        Dict mapping BodyRegion to RegionMesh
    """
    mesh = model.meshes[0]

    # Build MLIB bone index to TMD bone index mapping
    tmd_name_to_idx = {b.name.strip(): i for i, b in enumerate(model.bones)}
    mlib_to_tmd = {}
    for mlib_idx, mlib_bone in enumerate(mlib.bones):
        tmd_idx = tmd_name_to_idx.get(mlib_bone.name.strip(), -1)
        if tmd_idx >= 0:
            mlib_to_tmd[mlib_idx] = tmd_idx

    # Get bone names list (TMD indices)
    bone_names = [b.name.strip() for b in model.bones]

    # Classify each vertex by region
    vertex_regions: list[BodyRegion | None] = []
    for v_idx in range(len(mesh.vertices)):
        bone_weights = mesh.vertex_skinning.get(v_idx, [])

        # Convert MLIB bone indices to TMD bone indices
        tmd_bone_weights = []
        for mlib_bone_idx, weight in bone_weights:
            tmd_bone_idx = mlib_to_tmd.get(mlib_bone_idx, -1)
            if tmd_bone_idx >= 0:
                tmd_bone_weights.append((tmd_bone_idx, weight))

        # Use material index to identify hair submesh
        # For hair vertices, pass position for scalp/strands split
        material_index = mesh.vertex_materials.get(v_idx)
        vertex = mesh.vertices[v_idx]
        vertex_pos = (vertex.x, vertex.y, vertex.z)
        region = get_vertex_region(tmd_bone_weights, bone_names, material_index, vertex_pos)
        vertex_regions.append(region)

    # Group vertices by region
    region_vertices: dict[BodyRegion, set[int]] = {r: set() for r in BodyRegion}
    for v_idx, region in enumerate(vertex_regions):
        if region is not None:
            region_vertices[region].add(v_idx)

    # Assign faces to regions by majority vote of vertices
    region_faces: dict[BodyRegion, list[tuple[int, int, int]]] = {r: [] for r in BodyRegion}

    for face in mesh.faces:
        v0, v1, v2 = face

        # Count regions of face vertices
        face_regions = [vertex_regions[v0], vertex_regions[v1], vertex_regions[v2]]
        region_counts: dict[BodyRegion, int] = {}
        for r in face_regions:
            if r is not None:
                region_counts[r] = region_counts.get(r, 0) + 1

        if not region_counts:
            # No classified vertices - skip this face
            continue

        # Assign to majority region
        majority_region = max(region_counts, key=lambda r: region_counts[r])
        region_faces[majority_region].append(face)

        # Add all face vertices to this region (for complete faces)
        region_vertices[majority_region].add(v0)
        region_vertices[majority_region].add(v1)
        region_vertices[majority_region].add(v2)

    # Build RegionMesh for each non-empty region
    result: dict[BodyRegion, RegionMesh] = {}
    for region in BodyRegion:
        if region_faces[region]:
            result[region] = RegionMesh(
                region=region,
                vertex_indices=sorted(region_vertices[region]),
                faces=region_faces[region],
            )

    return result


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


def _build_skeleton(ctx: ExportContext, model: TMDModel, mlib: MLIBFile) -> int:
    """Build skeleton nodes and return armature index."""
    gltf = ctx.gltf
    parent_map = _build_parent_map(model, mlib)

    # Get world transforms
    world_pos = []
    world_rot = []
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

    # Compute LOCAL transforms
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
        name="AvatarSkin",
        joints=ctx.bone_node_indices,
        skeleton=armature_idx,
        inverseBindMatrices=ibm_accessor,
    )
    gltf.skins.append(skin)

    return armature_idx


def _build_inverse_bind_matrices(model: TMDModel) -> list[float]:
    """Build inverse bind matrices from TMD world transforms."""
    ibm_data = []

    for bone in model.bones:
        pos = [
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            bone.world_transform.translation.z,
        ]
        R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
        R_inv = R.T
        t_inv = -R_inv @ np.array(pos)

        ibm = [
            R_inv[0, 0], R_inv[1, 0], R_inv[2, 0], 0.0,
            R_inv[0, 1], R_inv[1, 1], R_inv[2, 1], 0.0,
            R_inv[0, 2], R_inv[1, 2], R_inv[2, 2], 0.0,
            t_inv[0], t_inv[1], t_inv[2], 1.0,
        ]
        ibm_data.extend(ibm)

    return ibm_data


def _build_region_mesh(
    ctx: ExportContext,
    model: TMDModel,
    region_mesh: RegionMesh,
) -> int:
    """
    Build GLTF mesh for a single region.

    Returns mesh index in gltf.meshes.
    """
    gltf = ctx.gltf
    original_mesh = model.meshes[0]

    # Build vertex index remapping (original -> new compact index)
    old_to_new = {old_idx: new_idx for new_idx, old_idx in enumerate(region_mesh.vertex_indices)}

    # Extract vertex data for this region
    positions = []
    normals = []
    uvs = []
    joints_data = []
    weights_data = []

    for old_idx in region_mesh.vertex_indices:
        v = original_mesh.vertices[old_idx]
        positions.extend([v.x, v.y, v.z])

        n = original_mesh.normals[old_idx]
        normals.extend([n.x, n.y, n.z])

        uv = original_mesh.uvs[old_idx]
        uvs.extend([uv.u, 1.0 - uv.v])  # V-flip

        # Skinning data
        bone_weights = original_mesh.vertex_skinning.get(old_idx, [])
        sorted_weights = sorted(bone_weights, key=lambda x: -x[1])[:4]
        while len(sorted_weights) < 4:
            sorted_weights.append((0, 0.0))

        total_weight = sum(w for _, w in sorted_weights)
        if total_weight > 0:
            sorted_weights = [(b, w / total_weight) for b, w in sorted_weights]

        for mlib_bone_idx, weight in sorted_weights:
            tmd_bone_idx = ctx.mlib_to_tmd.get(mlib_bone_idx, 0)
            joints_data.append(tmd_bone_idx)
            weights_data.append(weight)

    # Remap face indices to new vertex indices
    indices = []
    for face in region_mesh.faces:
        v0, v1, v2 = face
        indices.extend([old_to_new[v0], old_to_new[v1], old_to_new[v2]])

    # Calculate bounds
    vertex_count = len(region_mesh.vertex_indices)
    pos_array = np.array(positions, dtype=np.float32).reshape(-1, 3)
    min_bound = pos_array.min(axis=0).tolist()
    max_bound = pos_array.max(axis=0).tolist()

    # Pack data into buffer
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
        name=f"region_{region_mesh.region.value}",
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

    return len(gltf.meshes) - 1


def export_with_regions(
    model: TMDModel,
    mlib: MLIBFile,
    output_path: Path | str,
) -> dict[BodyRegion, int]:
    """
    Export TMD model with mesh split by body regions.

    Each region is a separate mesh node sharing the same skeleton.

    Args:
        model: Parsed TMD model
        mlib: Parsed MLIB file
        output_path: Path to output GLB file

    Returns:
        Dict mapping BodyRegion to vertex count for each exported region
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.region_exporter"))
    ctx = ExportContext(gltf=gltf, buffer=bytearray())

    # Build MLIB to TMD bone index mapping
    tmd_name_to_idx = {b.name.strip(): i for i, b in enumerate(model.bones)}
    for mlib_idx, mlib_bone in enumerate(mlib.bones):
        tmd_idx = tmd_name_to_idx.get(mlib_bone.name.strip(), -1)
        if tmd_idx >= 0:
            ctx.mlib_to_tmd[mlib_idx] = tmd_idx

    # Build skeleton
    armature_idx = _build_skeleton(ctx, model, mlib)

    # Split mesh by region
    region_meshes = split_mesh_by_region(model, mlib)

    # Create mesh nodes for each region
    scene_nodes = [armature_idx]
    region_stats: dict[BodyRegion, int] = {}

    for region in BodyRegion:
        if region not in region_meshes:
            continue

        region_mesh = region_meshes[region]
        mesh_idx = _build_region_mesh(ctx, model, region_mesh)

        # Create mesh node with skin
        mesh_node = Node(
            name=f"mesh_{region.value}",
            mesh=mesh_idx,
            skin=0,
        )
        gltf.nodes.append(mesh_node)
        scene_nodes.append(len(gltf.nodes) - 1)

        region_stats[region] = len(region_mesh.vertex_indices)

    # Create scene
    scene = Scene(nodes=scene_nodes)
    gltf.scenes.append(scene)
    gltf.scene = 0

    # Finalize buffer
    gltf.buffers.append(Buffer(
        byteLength=len(ctx.buffer),
        uri="data:application/octet-stream;base64," + _base64_encode(bytes(ctx.buffer)),
    ))

    gltf.save(str(output_path))

    return region_stats
