"""
Weapon Exporter

Exports weapon PRT files to GLTF as static meshes (no skeleton or skinning).
Weapons attach rigidly to a bone via BoneAttachment3D in Godot.

Vertices in weapon PRTs are in world space (T-pose position). This exporter
transforms them to bone-local space so the weapon appears correctly when
attached to the target bone. The weapon object's local_transform.translation
is used instead of the pure bone inverse — it includes a grip alignment offset
that positions the hilt correctly in the hand.

Each object in the PRT becomes a separate named mesh node in the GLB
(e.g. weapon_blade_XXXX, blade_low, blade_high).

Coordinate conversion (TMD -> GLTF):
- Position: transformed from world space to bone-local space
- Normal: rotated to bone-local space
- UV: [u, v] (no conversion needed)
- Faces: [v0, v1, v2] (original winding)
"""

from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2, Asset, Scene, Node, Mesh, Primitive, Attributes,
    Accessor, BufferView, Buffer,
    UNSIGNED_SHORT, UNSIGNED_INT, FLOAT, SCALAR, VEC2, VEC3,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDModel, TMDBone


def _get_bone_inverse_world_transform(bone: TMDBone) -> tuple[np.ndarray, np.ndarray]:
    """Get inverse world transform for a bone.

    Returns (R_inv, t_inv) where:
        v_local = R_inv @ v_world + t_inv
    """
    pos = np.array([
        bone.world_transform.translation.x,
        bone.world_transform.translation.y,
        bone.world_transform.translation.z,
    ])
    R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T

    R_inv = R.T
    t_inv = -R_inv @ pos
    return R_inv, t_inv


def _find_bone_by_name(model: TMDModel, name: str) -> TMDBone:
    """Find a bone by name in a TMD model."""
    for bone in model.bones:
        if bone.name.strip() == name:
            return bone
    raise ValueError(f"Bone '{name}' not found in model")


def _find_weapon_mesh_object(model: TMDModel) -> object:
    """Find the main weapon mesh object (weapon_blade_*, not trail anchors)."""
    for obj in model.objects:
        name = obj.name.strip()
        if name.startswith("weapon_") and obj.mesh and len(obj.mesh.vertices) > 0:
            return obj
    return None


def export_weapon(
    model: TMDModel,
    base_model: TMDModel,
    bone_name: str,
    output_path: Path | str,
    use_local_transform: bool = True,
) -> None:
    """
    Export weapon PRT as static mesh GLB with vertices in bone-local space.

    Each object in the model becomes a separate named mesh node.

    Args:
        model: Parsed weapon PRT model
        base_model: Parsed base TMD model (for bone transforms)
        bone_name: Target bone name (e.g. "@Sword")
        output_path: Path to output GLB file
        use_local_transform: If True, use weapon's local_transform.translation
            for grip alignment (blades). If False, use pure bone inverse
            for exact world-space reconstruction (spirits).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bone = _find_bone_by_name(base_model, bone_name)
    R_inv, t_inv_pure = _get_bone_inverse_world_transform(bone)

    if use_local_transform:
        # Use weapon's local_transform.translation for grip alignment offset
        weapon_obj = _find_weapon_mesh_object(model)
        if weapon_obj:
            t_inv = np.array([
                weapon_obj.local_transform.translation.x,
                weapon_obj.local_transform.translation.y,
                weapon_obj.local_transform.translation.z,
            ])
        else:
            t_inv = t_inv_pure
    else:
        # Pure bone inverse — exact world-space reconstruction
        t_inv = t_inv_pure

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.weapon_exporter"))
    buffer = bytearray()
    scene_node_indices = []

    for obj in model.objects:
        mesh = obj.mesh
        if mesh is None or len(mesh.vertices) == 0:
            continue

        # Get object world transform for positioning
        obj_pos = np.array([
            obj.world_transform.translation.x,
            obj.world_transform.translation.y,
            obj.world_transform.translation.z,
        ])
        obj_R = np.array(obj.world_transform.rotation.data).reshape(3, 3).T

        # Transform vertices: object-local -> world -> bone-local
        positions = []
        normals = []
        for v, n in zip(mesh.vertices, mesh.normals):
            v_local = np.array([v.x, v.y, v.z])
            n_local = np.array([n.x, n.y, n.z])

            # Object-local to world space
            v_world = obj_R @ v_local + obj_pos
            n_world = obj_R @ n_local

            # World to bone-local space
            v_bone = R_inv @ v_world + t_inv
            n_bone = R_inv @ n_world

            positions.extend(v_bone.tolist())
            normals.extend(n_bone.tolist())

        # UVs (no conversion needed)
        uvs = []
        for uv in mesh.uvs:
            uvs.extend([uv.u, uv.v])

        # Faces (original winding)
        indices = []
        for face in mesh.faces:
            indices.extend([face[0], face[1], face[2]])

        # Calculate bounds
        vertex_count = len(mesh.vertices)
        pos_array = np.array(positions, dtype=np.float32).reshape(-1, 3)
        min_bound = pos_array.min(axis=0).tolist()
        max_bound = pos_array.max(axis=0).tolist()

        # Pack vertex data
        pos_bin = np.array(positions, dtype=np.float32).tobytes()
        pos_offset = len(buffer)
        buffer.extend(pos_bin)

        norm_bin = np.array(normals, dtype=np.float32).tobytes()
        norm_offset = len(buffer)
        buffer.extend(norm_bin)

        uv_bin = np.array(uvs, dtype=np.float32).tobytes()
        uv_offset = len(buffer)
        buffer.extend(uv_bin)

        # Pack indices
        if vertex_count > 65535:
            idx_bin = np.array(indices, dtype=np.uint32).tobytes()
            idx_component = UNSIGNED_INT
        else:
            idx_bin = np.array(indices, dtype=np.uint16).tobytes()
            idx_component = UNSIGNED_SHORT

        idx_offset = len(buffer)
        buffer.extend(idx_bin)

        # Create buffer views
        bv_base = len(gltf.bufferViews)
        gltf.bufferViews.extend([
            BufferView(buffer=0, byteOffset=pos_offset, byteLength=len(pos_bin), target=ARRAY_BUFFER),
            BufferView(buffer=0, byteOffset=norm_offset, byteLength=len(norm_bin), target=ARRAY_BUFFER),
            BufferView(buffer=0, byteOffset=uv_offset, byteLength=len(uv_bin), target=ARRAY_BUFFER),
            BufferView(buffer=0, byteOffset=idx_offset, byteLength=len(idx_bin), target=ELEMENT_ARRAY_BUFFER),
        ])

        # Create accessors
        acc_base = len(gltf.accessors)
        gltf.accessors.extend([
            Accessor(
                bufferView=bv_base + 0,
                componentType=FLOAT,
                count=vertex_count,
                type=VEC3,
                min=min_bound,
                max=max_bound,
            ),
            Accessor(
                bufferView=bv_base + 1,
                componentType=FLOAT,
                count=vertex_count,
                type=VEC3,
            ),
            Accessor(
                bufferView=bv_base + 2,
                componentType=FLOAT,
                count=vertex_count,
                type=VEC2,
            ),
            Accessor(
                bufferView=bv_base + 3,
                componentType=idx_component,
                count=len(indices),
                type=SCALAR,
            ),
        ])

        # Create mesh
        gltf_mesh = Mesh(
            name=obj.name.strip(),
            primitives=[Primitive(
                attributes=Attributes(
                    POSITION=acc_base + 0,
                    NORMAL=acc_base + 1,
                    TEXCOORD_0=acc_base + 2,
                ),
                indices=acc_base + 3,
            )],
        )
        gltf.meshes.append(gltf_mesh)
        mesh_idx = len(gltf.meshes) - 1

        # Create node
        node = Node(name=obj.name.strip(), mesh=mesh_idx)
        gltf.nodes.append(node)
        scene_node_indices.append(len(gltf.nodes) - 1)

    # Create scene
    scene = Scene(nodes=scene_node_indices)
    gltf.scenes.append(scene)
    gltf.scene = 0

    # Finalize buffer
    gltf.buffers.append(Buffer(byteLength=len(buffer)))
    gltf.set_binary_blob(bytes(buffer))

    gltf.save(str(output_path))
