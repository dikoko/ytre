"""
Animation Exporter

Exports TMD mesh with skeleton and animations.
Builds on skeleton_exporter, adding animation data from MLIB.

Animation approach:
- MLIB stores local rotations per bone per frame
- Apply directly to bone nodes (same as debug_anim.py)
"""

import base64
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2, Asset, Scene, Node, Mesh, Primitive, Attributes,
    Accessor, BufferView, Buffer, Skin,
    Animation, AnimationChannel, AnimationChannelTarget, AnimationSampler,
    UNSIGNED_SHORT, FLOAT, SCALAR, VEC2, VEC3, VEC4, MAT4,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDModel
from src.parsers.mlib_parser import MLIBFile, MLIBMotion
from src.validators.mesh_validator import validate_mesh
from src.validators.skeleton_validator import validate_skeleton


@dataclass
class ExportContext:
    """Context for building GLTF."""
    gltf: GLTF2
    buffer: bytearray
    bone_node_indices: list[int] = field(default_factory=list)
    mlib_to_tmd: dict[int, int] = field(default_factory=dict)
    tmd_to_mlib: dict[int, int] = field(default_factory=dict)
    tmd_name_to_idx: dict[str, int] = field(default_factory=dict)
    mlib_name_to_idx: dict[str, int] = field(default_factory=dict)
    local_rot: list[list[float]] = field(default_factory=list)
    local_pos: list[list[float]] = field(default_factory=list)  # bind-pose local positions
    world_rot_full: list = field(default_factory=list)
    smooth_bone_indices: set[int] = field(default_factory=set)
    pos_tweaks: dict[int, list[float]] = field(default_factory=dict)  # tmd_idx -> [x,y,z] offset
    skip_reparent: bool = False
    equip_reparent: dict[int, int] = field(default_factory=dict)  # tmd_idx -> new_parent_tmd_idx
    original_parent_map: dict[int, int] = field(default_factory=dict)  # original parents before reparent


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


def _quat_normalize(q: list[float]) -> list[float]:
    """Normalize a quaternion."""
    norm = sum(c * c for c in q) ** 0.5
    if norm < 1e-10:
        return [0.0, 0.0, 0.0, 1.0]
    return [c / norm for c in q]


def _quat_slerp(q1: list[float], q2: list[float], t: float) -> list[float]:
    """Spherical linear interpolation between two quaternions."""
    import math
    dot = sum(a * b for a, b in zip(q1, q2))
    if dot < 0:
        q2 = [-c for c in q2]
        dot = -dot
    if dot > 0.9995:
        result = [a + t * (b - a) for a, b in zip(q1, q2)]
        return _quat_normalize(result)
    theta = math.acos(min(1.0, dot))
    sin_theta = math.sin(theta)
    s1 = math.sin((1.0 - t) * theta) / sin_theta
    s2 = math.sin(t * theta) / sin_theta
    return _quat_normalize([s1 * a + s2 * b for a, b in zip(q1, q2)])


# Bone name prefixes that contain baked physics and need smoothing
_PHYSICS_BONE_PREFIXES = (
    "@Skirt", "@skirt", "@Hair", "@Breast",              # Avatar
    "@necktie", "@upper", "@ribon", "@Cloth", "@Cover",  # Monster cloth/string
    "@Cap", "@Tail", "@Mantle", "@Feeler",               # Monster appendages
    "@Manteau", "@Rosary", "@Pipe",                      # NPC cloth/accessories
)

# EMA smoothing factor for physics bones (0=no smoothing, 1=full smoothing)
_PHYSICS_SMOOTHING = 0.5

# Known equip bone prefixes (weapons/props held in hands)
_EQUIP_BONE_PREFIXES = (
    "@Sword", "@FixBlade", "@fan", "@Book", "@book",
    "@broom", "@bucket", "@Tea",
    "@Wand", "@Staff", "@Stick",
)

# Parent bones where equip attachment is intentional (not detachment)
# e.g. @Pelvis = back-mounted props that should stay on the body
_EQUIP_KEEP_PARENTS = ("@Pelvis", "Bip01 Pelvis", "@Head")


def _detect_equip_reparents(
    model, parent_map: dict[int, int],
) -> dict[int, int]:
    """Detect equip chain ROOT bones that should be reparented to nearest hand.

    Only reparents the chain root — children stay attached to their original
    parent within the chain. Skips bones already on a hand chain or parented
    to body-mount points (@Pelvis).

    Returns dict mapping tmd_idx -> hand_tmd_idx.
    """
    # Find hand bone indices
    hands = {}  # 'L' or 'R' -> tmd_idx
    for i, b in enumerate(model.bones):
        name = b.name.strip()
        if 'HandR' in name or 'R Hand' in name:
            hands['R'] = i
        elif 'HandL' in name or 'L Hand' in name:
            hands['L'] = i
    if not hands:
        return {}

    hand_indices = set(hands.values())

    reparents = {}
    for i, b in enumerate(model.bones):
        name = b.name.strip()
        if not any(name.startswith(p) for p in _EQUIP_BONE_PREFIXES):
            continue

        # Check if already on a hand chain
        on_hand = False
        idx = i
        for _ in range(15):
            pidx = parent_map.get(idx, -1)
            if pidx < 0:
                break
            if pidx in hand_indices:
                on_hand = True
                break
            idx = pidx
        if on_hand:
            continue

        # Skip if parented to a body-mount point (back props, belt props)
        parent_idx = parent_map.get(i, -1)
        if parent_idx >= 0:
            parent_name = model.bones[parent_idx].name.strip()
            if parent_name in _EQUIP_KEEP_PARENTS:
                continue

        # Check if ANY ancestor is already being reparented (only reparent chain root)
        has_reparented_ancestor = False
        idx = i
        for _ in range(15):
            pidx = parent_map.get(idx, -1)
            if pidx < 0:
                break
            if pidx in reparents:
                has_reparented_ancestor = True
                break
            idx = pidx
        if has_reparented_ancestor:
            continue

        # Find nearest hand by world position
        pos = b.world_transform.translation
        best_hand_idx = None
        best_dist = 999.0
        for side, hi in hands.items():
            hp = model.bones[hi].world_transform.translation
            dist = ((pos.x - hp.x)**2 + (pos.y - hp.y)**2 + (pos.z - hp.z)**2)**0.5
            if dist < best_dist:
                best_dist = dist
                best_hand_idx = hi
        if best_hand_idx is not None:
            reparents[i] = best_hand_idx

    return reparents


def _smooth_physics_rotations(quats: list[list[float]]) -> list[list[float]]:
    """Apply exponential moving average smoothing to a quaternion track.
    Uses bidirectional EMA (forward + backward) to avoid lag."""
    if len(quats) <= 1:
        return quats

    alpha = _PHYSICS_SMOOTHING

    # Forward pass
    forward = [quats[0]]
    for i in range(1, len(quats)):
        smoothed = _quat_slerp(quats[i], forward[i - 1], alpha)
        forward.append(smoothed)

    # Backward pass
    backward = [None] * len(quats)
    backward[-1] = quats[-1]
    for i in range(len(quats) - 2, -1, -1):
        smoothed = _quat_slerp(quats[i], backward[i + 1], alpha)
        backward[i] = smoothed

    # Average forward and backward
    result = []
    for i in range(len(quats)):
        avg = _quat_slerp(forward[i], backward[i], 0.5)
        result.append(avg)

    return result


def _build_parent_map(model: TMDModel, mlib: MLIBFile) -> dict[int, int]:
    """Build parent map using MLIB hierarchy.

    Uses _build_tmd_to_mlib_map for TMD→MLIB mapping (handles name mismatches
    and duplicate names). For parent lookup, uses the inverse of that mapping
    (MLIB parent index → TMD index).
    """
    tmd_to_mlib = _build_tmd_to_mlib_map(model, mlib)
    # Build reverse map: MLIB index → TMD index
    mlib_to_tmd = {v: k for k, v in tmd_to_mlib.items()}

    parent_map = {}
    for tmd_idx in range(len(model.bones)):
        mlib_idx = tmd_to_mlib.get(tmd_idx)
        if mlib_idx is not None and mlib_idx < len(mlib.bones):
            mlib_parent_idx = mlib.bones[mlib_idx].parent_id
            if mlib_parent_idx >= 0 and mlib_parent_idx < len(mlib.bones):
                tmd_parent_idx = mlib_to_tmd.get(mlib_parent_idx, -1)
                parent_map[tmd_idx] = tmd_parent_idx
            else:
                parent_map[tmd_idx] = -1
        else:
            parent_map[tmd_idx] = -1

    return parent_map


def _build_mlib_to_tmd_map(model: TMDModel, mlib: MLIBFile) -> dict[int, int]:
    """Build MLIB bone index to TMD bone index mapping.

    Primary: match by name. Fallback: match by index when names differ.
    """
    tmd_name_to_idx = {b.name.strip(): i for i, b in enumerate(model.bones)}
    mlib_to_tmd = {}
    unmatched_mlib = []

    # First pass: name-based matching
    for mlib_idx, mlib_bone in enumerate(mlib.bones):
        tmd_idx = tmd_name_to_idx.get(mlib_bone.name.strip(), -1)
        if tmd_idx >= 0:
            mlib_to_tmd[mlib_idx] = tmd_idx
        else:
            unmatched_mlib.append(mlib_idx)

    # Second pass: index-based fallback for unmatched bones
    if unmatched_mlib:
        matched_tmd = set(mlib_to_tmd.values())
        for mlib_idx in unmatched_mlib:
            if mlib_idx < len(model.bones) and mlib_idx not in matched_tmd:
                mlib_to_tmd[mlib_idx] = mlib_idx
                matched_tmd.add(mlib_idx)

    return mlib_to_tmd


def _build_tmd_to_mlib_map(model: TMDModel, mlib: MLIBFile) -> dict[int, int]:
    """Build TMD bone index to MLIB bone index mapping.

    Primary: match by name (1:1 only). Fallback: match by index when names
    differ or when multiple TMD bones share the same name.
    """
    mlib_name_to_idx = {b.name.strip(): i for i, b in enumerate(mlib.bones)}
    tmd_to_mlib = {}
    unmatched_tmd = []

    # Detect duplicate TMD bone names
    name_counts: dict[str, int] = {}
    for bone in model.bones:
        n = bone.name.strip()
        name_counts[n] = name_counts.get(n, 0) + 1
    duplicate_names = {n for n, c in name_counts.items() if c > 1}

    # First pass: name-based matching (skip duplicates — they need index fallback)
    for tmd_idx, tmd_bone in enumerate(model.bones):
        name = tmd_bone.name.strip()
        if name in duplicate_names:
            unmatched_tmd.append(tmd_idx)
            continue
        mlib_idx = mlib_name_to_idx.get(name)
        if mlib_idx is not None:
            tmd_to_mlib[tmd_idx] = mlib_idx
        else:
            unmatched_tmd.append(tmd_idx)

    # Second pass: index-based fallback for unmatched bones
    if unmatched_tmd:
        matched_mlib = set(tmd_to_mlib.values())
        for tmd_idx in unmatched_tmd:
            if tmd_idx < len(mlib.bones) and tmd_idx not in matched_mlib:
                tmd_to_mlib[tmd_idx] = tmd_idx
                matched_mlib.add(tmd_idx)

    return tmd_to_mlib


def _normalize_rotation_matrix(R: np.ndarray) -> np.ndarray:
    """Normalize a rotation matrix by removing scale and reflections.

    Some TMD bones have non-orthogonal rotation matrices with embedded scale
    factors or negative determinants (reflections for mirrored bones).
    This extracts the pure rotation component via SVD polar decomposition.
    """
    U, _, Vt = np.linalg.svd(R)
    R_clean = U @ Vt
    # Ensure proper rotation (det = +1), not reflection (det = -1)
    if np.linalg.det(R_clean) < 0:
        U[:, -1] *= -1
        R_clean = U @ Vt
    return R_clean


def _build_skeleton(
    ctx: ExportContext, model: TMDModel, mlib: MLIBFile,
    use_mlib_rotations: bool = False,
) -> int:
    """Build skeleton nodes and return armature index.

    Two approaches based on use_mlib_rotations:
    - False (avatars): TMD rotation matrices for rest pose (no scale needed)
    - True (monsters with reflections): MLIB stand frame 0 rotations as rest
      pose (pure quaternions, no scale/reflection). TMD positions for placement.
    When False but called with anim_correction=True (monsters without
    reflections): TMD rotations + SVD scale are used so the bind-pose mesh
    can be deformed by animations.
    """
    gltf = ctx.gltf
    parent_map = _build_parent_map(model, mlib)
    ctx.original_parent_map = dict(parent_map)

    # Detect and apply equip bone reparenting (unless skipped)
    ctx.equip_reparent = {} if ctx.skip_reparent else _detect_equip_reparents(model, parent_map)
    if ctx.equip_reparent:
        for bone_idx, new_parent_idx in ctx.equip_reparent.items():
            parent_map[bone_idx] = new_parent_idx

    # Get world positions from TMD
    world_pos = []
    for bone in model.bones:
        world_pos.append([
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            bone.world_transform.translation.z,
        ])

    if use_mlib_rotations:
        # MLIB approach: pure quaternion rotations from stand frame 0
        ref_motion = None
        for motion in mlib.motions:
            if "stand" in motion.name:
                ref_motion = motion
                break
        if ref_motion is None and mlib.motions:
            ref_motion = mlib.motions[0]

        world_rot = [None] * len(model.bones)
        for tmd_idx in range(len(model.bones)):
            mlib_idx = ctx.tmd_to_mlib.get(tmd_idx)
            if ref_motion and mlib_idx is not None and mlib_idx < ref_motion.bone_count:
                r = ref_motion.rotations[0][mlib_idx]
                local_rot = [r.x, r.y, r.z, r.w]
            else:
                local_rot = [0.0, 0.0, 0.0, 1.0]
            parent_idx = parent_map.get(tmd_idx, -1)
            if parent_idx < 0 or world_rot[parent_idx] is None:
                world_rot[tmd_idx] = local_rot
            else:
                world_rot[tmd_idx] = _quat_normalize(
                    _quat_multiply(world_rot[parent_idx], local_rot)
                )
        world_scale = [[1.0, 1.0, 1.0]] * len(model.bones)

        # IBM uses MLIB-derived rotation matrices (pure rotation, no scale)
        ctx.world_rot_full = []
        for q in world_rot:
            x, y, z, w = q
            xx, yy, zz = x*x, y*y, z*z
            xy, xz, yz = x*y, x*z, y*z
            wx, wy, wz = w*x, w*y, w*z
            ctx.world_rot_full.append([
                [1-2*(yy+zz), 2*(xy-wz), 2*(xz+wy)],
                [2*(xy+wz), 1-2*(xx+zz), 2*(yz-wx)],
                [2*(xz-wy), 2*(yz+wx), 1-2*(xx+yy)],
            ])
    else:
        # TMD approach: rotation matrices (with optional scale extraction)
        world_rot = []
        world_scale = []
        ctx.world_rot_full = []
        for bone in model.bones:
            R_full = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
            R_clean = _normalize_rotation_matrix(R_full)
            world_rot.append(_rotation_matrix_to_quaternion(R_clean))
            ctx.world_rot_full.append(R_full)
            _, S, _ = np.linalg.svd(R_full)
            if np.linalg.det(R_full) < 0:
                S[2] = -S[2]
            world_scale.append(S.tolist())

    # Compute LOCAL transforms
    # Compute local transforms using ORIGINAL parents (for FK in animation)
    ctx.local_pos = []
    ctx.local_rot = []
    for bone_idx in range(len(model.bones)):
        orig_parent = ctx.original_parent_map.get(bone_idx, -1)
        if orig_parent < 0:
            ctx.local_pos.append(world_pos[bone_idx])
            ctx.local_rot.append(world_rot[bone_idx])
        else:
            parent_RS = np.array(ctx.world_rot_full[orig_parent])
            diff = np.array(world_pos[bone_idx]) - np.array(world_pos[orig_parent])
            lp = np.linalg.solve(parent_RS, diff).tolist()
            ctx.local_pos.append(lp)

            parent_rot_inv = _quat_conjugate(world_rot[orig_parent])
            lr = _quat_multiply(parent_rot_inv, world_rot[bone_idx])
            ctx.local_rot.append(lr)

    # Compute node transforms using REPARENTED parents (for skeleton hierarchy)
    local_pos = []
    local_scale = []
    for bone_idx in range(len(model.bones)):
        parent_idx = parent_map.get(bone_idx, -1)
        if parent_idx < 0:
            local_pos.append(world_pos[bone_idx])
            local_scale.append(world_scale[bone_idx])
        else:
            parent_RS = np.array(ctx.world_rot_full[parent_idx])
            diff = np.array(world_pos[bone_idx]) - np.array(world_pos[parent_idx])
            lp = np.linalg.solve(parent_RS, diff).tolist()
            local_pos.append(lp)

            ls = [world_scale[bone_idx][j] / world_scale[parent_idx][j]
                  if abs(world_scale[parent_idx][j]) > 1e-6 else 1.0
                  for j in range(3)]
            local_scale.append(ls)

    # Create armature node
    armature_node = Node(name="Armature")
    gltf.nodes.append(armature_node)
    armature_idx = len(gltf.nodes) - 1

    # Create bone nodes with LOCAL transforms (including scale when needed)
    ctx.bone_node_indices = []
    for i, bone in enumerate(model.bones):
        s = local_scale[i]
        has_scale = any(abs(v - 1.0) > 0.001 for v in s)
        lp = local_pos[i]
        # Apply position tweaks (per-bone offset in parent-local space)
        if i in ctx.pos_tweaks:
            offset = ctx.pos_tweaks[i]
            lp = [lp[j] + offset[j] for j in range(3)]
        node = Node(
            name=bone.name.strip(),
            translation=lp,
            rotation=ctx.local_rot[i],
            scale=s if has_scale else None,
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
    ibm_data = _build_inverse_bind_matrices(model, world_pos, ctx.world_rot_full)

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


def _build_inverse_bind_matrices(
    model: TMDModel,
    world_pos: list[list[float]],
    world_rot_full: list,
) -> list[float]:
    """Build inverse bind matrices from world transforms (including scale)."""
    ibm_data = []

    for bone_idx in range(len(model.bones)):
        pos = np.array(world_pos[bone_idx])
        R = np.array(world_rot_full[bone_idx])

        R_inv = np.linalg.inv(R)
        t_inv = -R_inv @ pos

        # Column-major 4x4 matrix
        ibm = [
            R_inv[0, 0], R_inv[1, 0], R_inv[2, 0], 0.0,
            R_inv[0, 1], R_inv[1, 1], R_inv[2, 1], 0.0,
            R_inv[0, 2], R_inv[1, 2], R_inv[2, 2], 0.0,
            t_inv[0], t_inv[1], t_inv[2], 1.0,
        ]
        ibm_data.extend(ibm)

    return ibm_data


def _build_skinning_data(ctx: ExportContext, model: TMDModel, mesh) -> tuple[list[int], list[float]]:
    """Build JOINTS_0 and WEIGHTS_0 data from TMD skinning."""
    joints = []
    weights = []

    vertex_count = len(mesh.vertices)

    for v_idx in range(vertex_count):
        v_weights = mesh.vertex_skinning.get(v_idx)

        if v_weights:
            sorted_weights = sorted(v_weights, key=lambda x: -x[1])[:4]
            while len(sorted_weights) < 4:
                sorted_weights.append((0, 0.0))

            total_weight = sum(w for _, w in sorted_weights)
            if total_weight > 0:
                sorted_weights = [(b, w / total_weight) for b, w in sorted_weights]

            for mlib_bone_idx, weight in sorted_weights:
                tmd_bone_idx = ctx.mlib_to_tmd.get(mlib_bone_idx, 0)
                joints.append(tmd_bone_idx)
                weights.append(weight)
        else:
            joints.extend([0, 0, 0, 0])
            weights.extend([1.0, 0.0, 0.0, 0.0])

    return joints, weights


def _compute_fk_world_rotations(
    ctx: ExportContext, model, motion,
) -> list[list[list[float]]]:
    """Compute world-space rotations for all bones at every frame using ORIGINAL parent chain.

    Returns: fk[frame][tmd_idx] = [x, y, z, w] quaternion
    """
    parent_map = ctx.original_parent_map
    num_bones = len(model.bones)
    fk = []
    for frame in range(motion.frame_count):
        world = [None] * num_bones
        for tmd_idx in range(num_bones):
            mlib_idx = ctx.tmd_to_mlib.get(tmd_idx)
            if mlib_idx is not None and mlib_idx < motion.bone_count:
                r = motion.rotations[frame][mlib_idx]
                local_q = [r.x, r.y, r.z, r.w]
            else:
                local_q = list(ctx.local_rot[tmd_idx])

            parent_idx = parent_map.get(tmd_idx, -1)
            if parent_idx < 0 or world[parent_idx] is None:
                world[tmd_idx] = local_q
            else:
                world[tmd_idx] = _quat_normalize(
                    _quat_multiply(world[parent_idx], local_q)
                )
        fk.append(world)
    return fk


def _fk_world_position(
    ctx: ExportContext, model, motion, frame: int, tmd_idx: int,
    fk_world_rot: list,
) -> list[float]:
    """Compute world-space position of a bone at a given frame using FK.

    Uses precomputed bind-pose local positions (parent-local space) and
    animated parent rotations through the ORIGINAL hierarchy.
    """
    parent_map = ctx.original_parent_map
    # Trace chain from root to this bone
    chain = []
    idx = tmd_idx
    while idx >= 0:
        chain.append(idx)
        idx = parent_map.get(idx, -1)
    chain.reverse()  # root first

    pos = [0.0, 0.0, 0.0]
    for i, bone_idx in enumerate(chain):
        local_offset = ctx.local_pos[bone_idx]
        if i == 0:
            # Root bone: local_pos is world position
            pos = list(local_offset)
        else:
            # Rotate local offset by parent's animated world rotation
            parent_idx = chain[i - 1]
            parent_world_q = fk_world_rot[frame][parent_idx]
            rot_mat = _quat_to_matrix(parent_world_q)
            rotated = [
                sum(rot_mat[r][j] * local_offset[j] for j in range(3))
                for r in range(3)
            ]
            pos = [pos[j] + rotated[j] for j in range(3)]
    return pos


def _quat_to_matrix(q: list[float]) -> list[list[float]]:
    """Convert quaternion [x,y,z,w] to 3x3 rotation matrix."""
    x, y, z, w = q
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z
    return [
        [1-2*(yy+zz), 2*(xy-wz), 2*(xz+wy)],
        [2*(xy+wz), 1-2*(xx+zz), 2*(yz-wx)],
        [2*(xz-wy), 2*(yz+wx), 1-2*(xx+yy)],
    ]


def _add_animation(ctx: ExportContext, model: TMDModel, motion: MLIBMotion) -> None:
    """Add animation to GLTF."""
    gltf = ctx.gltf

    anim_name = motion.name.replace("male_", "")
    anim = Animation(name=anim_name, channels=[], samplers=[])

    # Time values
    duration = motion.frame_count / motion.fps
    times = [i / motion.fps for i in range(motion.frame_count)]
    time_bin = np.array(times, dtype=np.float32).tobytes()
    time_offset = len(ctx.buffer)
    ctx.buffer.extend(time_bin)

    gltf.bufferViews.append(BufferView(buffer=0, byteOffset=time_offset, byteLength=len(time_bin)))
    time_bv = len(gltf.bufferViews) - 1

    gltf.accessors.append(Accessor(
        bufferView=time_bv,
        componentType=FLOAT,
        count=motion.frame_count,
        type=SCALAR,
        min=[0.0],
        max=[duration],
    ))
    time_acc = len(gltf.accessors) - 1

    # For reparented equip bones, we need FK to compute world-space transforms.
    # Pre-compute world rotations per frame using the ORIGINAL parent chain.
    fk_world_rot = None
    if ctx.equip_reparent:
        # Collect all bones that need FK (reparented bones + their original ancestors + new parents)
        fk_world_rot = _compute_fk_world_rotations(ctx, model, motion)

    # Rotation (and translation for reparented bones) channels per bone
    for tmd_idx in range(len(model.bones)):
        bone_name = model.bones[tmd_idx].name.strip()
        mlib_idx = ctx.tmd_to_mlib.get(tmd_idx)

        is_reparented = tmd_idx in ctx.equip_reparent
        new_parent_idx = ctx.equip_reparent.get(tmd_idx)

        # Collect quaternions (and translations for reparented) per frame
        quats = []
        translations = [] if is_reparented else None
        prev_q = None
        for frame in range(motion.frame_count):
            if is_reparented and fk_world_rot is not None:
                # Reparented bone: compute local rotation relative to new parent
                equip_world = fk_world_rot[frame][tmd_idx]
                parent_world = fk_world_rot[frame][new_parent_idx]
                parent_inv = _quat_conjugate(parent_world)
                q = _quat_normalize(_quat_multiply(parent_inv, equip_world))

                # Use bind-pose offset in new parent's local space (constant)
                # The skeleton node already has this as its rest translation,
                # but we re-emit it each frame to ensure GLTF applies it.
                equip_bind = model.bones[tmd_idx].world_transform.translation
                hand_bind = model.bones[new_parent_idx].world_transform.translation
                diff = [equip_bind.x - hand_bind.x,
                        equip_bind.y - hand_bind.y,
                        equip_bind.z - hand_bind.z]
                # Transform into hand's bind-pose local space
                hand_R = np.array(ctx.world_rot_full[new_parent_idx])
                local_t = np.linalg.solve(hand_R, diff).tolist()
                # Apply position tweak if configured
                if tmd_idx in ctx.pos_tweaks:
                    offset = ctx.pos_tweaks[tmd_idx]
                    local_t = [local_t[j] + offset[j] for j in range(3)]
                translations.append(local_t)
            elif mlib_idx is not None and mlib_idx < motion.bone_count:
                mlib_rot = motion.rotations[frame][mlib_idx]
                # MLIB [w,x,y,z] -> GLTF [x,y,z,w] (no X-mirror)
                q = [mlib_rot.x, mlib_rot.y, mlib_rot.z, mlib_rot.w]
            else:
                q = list(ctx.local_rot[tmd_idx])

            # Ensure quaternion continuity: flip sign if dot product with
            # previous frame is negative to prevent "long path" interpolation
            if prev_q is not None:
                dot = sum(a * b for a, b in zip(prev_q, q))
                if dot < 0:
                    q = [-c for c in q]
            prev_q = q
            quats.append(q)

        # Smooth physics bones (skirt, hair, breast) to reduce baked cloth sim pops
        is_physics = (
            any(bone_name.startswith(p) for p in _PHYSICS_BONE_PREFIXES)
            or tmd_idx in ctx.smooth_bone_indices
        )
        if is_physics:
            quats = _smooth_physics_rotations(quats)

        rot_values = []
        for q in quats:
            rot_values.extend(q)

        rot_bin = np.array(rot_values, dtype=np.float32).tobytes()
        rot_offset = len(ctx.buffer)
        ctx.buffer.extend(rot_bin)

        gltf.bufferViews.append(BufferView(buffer=0, byteOffset=rot_offset, byteLength=len(rot_bin)))
        rot_bv = len(gltf.bufferViews) - 1

        gltf.accessors.append(Accessor(
            bufferView=rot_bv,
            componentType=FLOAT,
            count=motion.frame_count,
            type=VEC4,
        ))
        rot_acc = len(gltf.accessors) - 1

        anim.samplers.append(AnimationSampler(input=time_acc, output=rot_acc))
        anim.channels.append(AnimationChannel(
            sampler=len(anim.samplers) - 1,
            target=AnimationChannelTarget(node=ctx.bone_node_indices[tmd_idx], path="rotation"),
        ))

        # Translation channel for reparented bones
        if translations:
            trans_values = []
            for t in translations:
                trans_values.extend(t)
            trans_bin = np.array(trans_values, dtype=np.float32).tobytes()
            trans_offset = len(ctx.buffer)
            ctx.buffer.extend(trans_bin)

            gltf.bufferViews.append(BufferView(buffer=0, byteOffset=trans_offset, byteLength=len(trans_bin)))
            trans_bv = len(gltf.bufferViews) - 1

            gltf.accessors.append(Accessor(
                bufferView=trans_bv,
                componentType=FLOAT,
                count=motion.frame_count,
                type=VEC3,
            ))
            trans_acc = len(gltf.accessors) - 1

            anim.samplers.append(AnimationSampler(input=time_acc, output=trans_acc))
            anim.channels.append(AnimationChannel(
                sampler=len(anim.samplers) - 1,
                target=AnimationChannelTarget(node=ctx.bone_node_indices[tmd_idx], path="translation"),
            ))

    # Root bone translation channel
    if motion.root_positions:
        # Root translation applies to bone index 0 (hierarchy root),
        # not necessarily the bone named @Root (which may be deeper).
        root_tmd_idx = 0
        if root_tmd_idx < len(model.bones):
            root_bone = model.bones[root_tmd_idx]
            bind_pos = root_bone.world_transform.translation
            is_moving = (motion.option & 1) != 0  # MOP_MOVING bitmask

            if is_moving:
                # MOP_MOVING: normalize Y to zero-mean, then add bind position.
                # Matches original engine's NormalizeYValue() behavior.
                mean_y = sum(rp.y for rp in motion.root_positions) / len(motion.root_positions)
                trans_values = []
                for rp in motion.root_positions:
                    trans_values.extend([
                        rp.x + bind_pos.x,
                        (rp.y - mean_y) + bind_pos.y,
                        rp.z + bind_pos.z,
                    ])
            else:
                # Non-moving: root positions are absolute world positions
                trans_values = []
                for rp in motion.root_positions:
                    trans_values.extend([rp.x, rp.y, rp.z])

            trans_bin = np.array(trans_values, dtype=np.float32).tobytes()
            trans_offset = len(ctx.buffer)
            ctx.buffer.extend(trans_bin)

            gltf.bufferViews.append(BufferView(buffer=0, byteOffset=trans_offset, byteLength=len(trans_bin)))
            trans_bv = len(gltf.bufferViews) - 1

            gltf.accessors.append(Accessor(
                bufferView=trans_bv,
                componentType=FLOAT,
                count=motion.frame_count,
                type=VEC3,
            ))
            trans_acc = len(gltf.accessors) - 1

            anim.samplers.append(AnimationSampler(input=time_acc, output=trans_acc))
            anim.channels.append(AnimationChannel(
                sampler=len(anim.samplers) - 1,
                target=AnimationChannelTarget(node=ctx.bone_node_indices[root_tmd_idx], path="translation"),
            ))

    gltf.animations.append(anim)


def _split_mesh_by_material(mesh) -> list[tuple[int, list]]:
    """Split a mesh's faces into groups by vertex material index.

    Returns list of (material_index, face_list) tuples. Only splits when
    the mesh has multiple per-vertex material assignments.
    """
    if not mesh.vertex_materials:
        return [(mesh.material_index, mesh.faces)]

    unique_mats = set(mesh.vertex_materials.values())
    if len(unique_mats) <= 1:
        mat_idx = next(iter(unique_mats)) if unique_mats else mesh.material_index
        return [(mat_idx, mesh.faces)]

    # Group faces by material (a face belongs to the material of its first vertex)
    mat_faces: dict[int, list] = {}
    for face in mesh.faces:
        face_mat = mesh.vertex_materials.get(face[0], mesh.material_index)
        mat_faces.setdefault(face_mat, []).append(face)

    return sorted(mat_faces.items())


def _build_primitive(ctx, mesh, face_list, v_flip: bool) -> Primitive:
    """Build a GLTF Primitive from a subset of a mesh's faces."""
    gltf = ctx.gltf

    # Collect unique vertices referenced by these faces, build re-index map
    old_indices = set()
    for face in face_list:
        old_indices.update(face)
    old_to_new = {old: new for new, old in enumerate(sorted(old_indices))}

    # Build vertex arrays for this subset
    positions = []
    normals_list = []
    uvs = []
    joints_data = []
    weights_data = []

    for old_idx in sorted(old_indices):
        v = mesh.vertices[old_idx]
        positions.extend([v.x, v.y, v.z])
        n = mesh.normals[old_idx]
        normals_list.extend([n.x, n.y, n.z])
        uv = mesh.uvs[old_idx]
        uvs.extend([uv.u, 1.0 - uv.v if v_flip else uv.v])

        # Skinning
        v_weights = mesh.vertex_skinning.get(old_idx)
        if v_weights:
            sorted_weights = sorted(v_weights, key=lambda x: -x[1])[:4]
            while len(sorted_weights) < 4:
                sorted_weights.append((0, 0.0))
            total = sum(w for _, w in sorted_weights)
            if total > 0:
                sorted_weights = [(b, w / total) for b, w in sorted_weights]
            for mlib_bone_idx, weight in sorted_weights:
                tmd_bone_idx = ctx.mlib_to_tmd.get(mlib_bone_idx, 0)
                joints_data.append(tmd_bone_idx)
                weights_data.append(weight)
        else:
            joints_data.extend([0, 0, 0, 0])
            weights_data.extend([1.0, 0.0, 0.0, 0.0])

    # Re-indexed face indices
    indices = []
    for face in face_list:
        indices.extend([old_to_new[face[0]], old_to_new[face[1]], old_to_new[face[2]]])

    vertex_count = len(old_to_new)
    pos_array = np.array(positions, dtype=np.float32).reshape(-1, 3)

    pos_bin = np.array(positions, dtype=np.float32).tobytes()
    pos_offset = len(ctx.buffer); ctx.buffer.extend(pos_bin)
    norm_bin = np.array(normals_list, dtype=np.float32).tobytes()
    norm_offset = len(ctx.buffer); ctx.buffer.extend(norm_bin)
    uv_bin = np.array(uvs, dtype=np.float32).tobytes()
    uv_offset = len(ctx.buffer); ctx.buffer.extend(uv_bin)
    joints_bin = np.array(joints_data, dtype=np.uint16).tobytes()
    joints_offset = len(ctx.buffer); ctx.buffer.extend(joints_bin)
    weights_bin = np.array(weights_data, dtype=np.float32).tobytes()
    weights_offset = len(ctx.buffer); ctx.buffer.extend(weights_bin)
    idx_bin = np.array(indices, dtype=np.uint16).tobytes()
    idx_offset = len(ctx.buffer); ctx.buffer.extend(idx_bin)

    bv_start = len(gltf.bufferViews)
    gltf.bufferViews.extend([
        BufferView(buffer=0, byteOffset=pos_offset, byteLength=len(pos_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=norm_offset, byteLength=len(norm_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=uv_offset, byteLength=len(uv_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=joints_offset, byteLength=len(joints_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=weights_offset, byteLength=len(weights_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=idx_offset, byteLength=len(idx_bin), target=ELEMENT_ARRAY_BUFFER),
    ])

    acc_start = len(gltf.accessors)
    gltf.accessors.extend([
        Accessor(bufferView=bv_start + 0, componentType=FLOAT, count=vertex_count, type=VEC3,
                 min=pos_array.min(axis=0).tolist(), max=pos_array.max(axis=0).tolist()),
        Accessor(bufferView=bv_start + 1, componentType=FLOAT, count=vertex_count, type=VEC3),
        Accessor(bufferView=bv_start + 2, componentType=FLOAT, count=vertex_count, type=VEC2),
        Accessor(bufferView=bv_start + 3, componentType=UNSIGNED_SHORT, count=vertex_count, type=VEC4),
        Accessor(bufferView=bv_start + 4, componentType=FLOAT, count=vertex_count, type=VEC4),
        Accessor(bufferView=bv_start + 5, componentType=UNSIGNED_SHORT, count=len(indices), type=SCALAR),
    ])

    return Primitive(
        attributes=Attributes(
            POSITION=acc_start + 0, NORMAL=acc_start + 1, TEXCOORD_0=acc_start + 2,
            JOINTS_0=acc_start + 3, WEIGHTS_0=acc_start + 4,
        ),
        indices=acc_start + 5,
    )


def export_with_animations(
    model: TMDModel,
    mlib: MLIBFile,
    output_path: Path | str,
    animation_names: list[str] | None = None,
    validate: bool = True,
    v_flip: bool = True,
    anim_correction: bool = False,
    split_materials: bool = False,
    force_tmd_scale: bool = False,
    smooth_bone_indices: set[int] | None = None,
    pos_tweaks: dict[int, list[float]] | None = None,
    skip_reparent: bool = False,
) -> None:
    """
    Export TMD model with skeleton and animations as GLB.

    Args:
        model: Parsed TMD model
        mlib: Parsed MLIB file
        output_path: Path to output GLB file
        animation_names: List of animation names to include (None = all)
        validate: Run validation before export
        v_flip: Apply UV V-flip (True for avatars, False for monsters)
        anim_correction: Apply per-bone rotation correction for TMD/MLIB
            rest-pose mismatch (True for monsters, False for avatars)
        split_materials: Split meshes with per-vertex materials into separate
            primitives (True for monsters with multi-texture, False for avatars)
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

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.animation_exporter"))
    ctx = ExportContext(gltf=gltf, buffer=bytearray(),
                        smooth_bone_indices=smooth_bone_indices or set(),
                        pos_tweaks=pos_tweaks or {},
                        skip_reparent=skip_reparent)
    ctx.mlib_to_tmd = _build_mlib_to_tmd_map(model, mlib)
    ctx.tmd_to_mlib = _build_tmd_to_mlib_map(model, mlib)
    ctx.tmd_name_to_idx = {b.name.strip(): i for i, b in enumerate(model.bones)}
    ctx.mlib_name_to_idx = {b.name.strip(): i for i, b in enumerate(mlib.bones)}

    # Build skeleton. For monsters (anim_correction=True), auto-detect:
    # - Reflected bones (det < 0): MLIB rotations (quaternions can't represent
    #   reflections). Fixes ct0016 orientation, ct0003 animations.
    # - No reflections: TMD + scale (preserves bind-pose deformation for
    #   T-pose monsters like ct0013). Weapon bones may drift ~8° (known).
    if anim_correction:
        has_reflections = any(
            np.linalg.det(np.array(b.world_transform.rotation.data).reshape(3, 3).T) < 0
            for b in model.bones
        )
        # Allow caller to override (e.g. cn0007 has physics-only reflections)
        if force_tmd_scale:
            has_reflections = False
        armature_idx = _build_skeleton(
            ctx, model, mlib, use_mlib_rotations=has_reflections,
        )
    else:
        armature_idx = _build_skeleton(ctx, model, mlib)

    # Build mesh — one or more primitives per TMD mesh
    primitives = []
    # Track material index per primitive for texture assignment
    primitive_materials = []
    for mesh in model.meshes:
        if split_materials:
            # Split mesh by per-vertex material assignments
            mat_groups = _split_mesh_by_material(mesh)
            for mat_idx, face_list in mat_groups:
                prim = _build_primitive(ctx, mesh, face_list, v_flip)
                primitives.append(prim)
                primitive_materials.append(mat_idx)
            continue

        # Default path: one primitive per mesh (avatar behavior)
        positions = []
        for v in mesh.vertices:
            positions.extend([v.x, v.y, v.z])

        normals = []
        for n in mesh.normals:
            normals.extend([n.x, n.y, n.z])

        uvs = []
        for uv in mesh.uvs:
            uvs.extend([uv.u, 1.0 - uv.v if v_flip else uv.v])

        indices = []
        for face in mesh.faces:
            indices.extend([face[0], face[1], face[2]])

        joints_data, weights_data = _build_skinning_data(ctx, model, mesh)

        pos_array = np.array(positions, dtype=np.float32).reshape(-1, 3)
        min_bound = pos_array.min(axis=0).tolist()
        max_bound = pos_array.max(axis=0).tolist()

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

        bv_start = len(gltf.bufferViews)
        gltf.bufferViews.extend([
            BufferView(buffer=0, byteOffset=pos_offset, byteLength=len(pos_bin), target=ARRAY_BUFFER),
            BufferView(buffer=0, byteOffset=norm_offset, byteLength=len(norm_bin), target=ARRAY_BUFFER),
            BufferView(buffer=0, byteOffset=uv_offset, byteLength=len(uv_bin), target=ARRAY_BUFFER),
            BufferView(buffer=0, byteOffset=joints_offset, byteLength=len(joints_bin), target=ARRAY_BUFFER),
            BufferView(buffer=0, byteOffset=weights_offset, byteLength=len(weights_bin), target=ARRAY_BUFFER),
            BufferView(buffer=0, byteOffset=idx_offset, byteLength=len(idx_bin), target=ELEMENT_ARRAY_BUFFER),
        ])

        acc_start = len(gltf.accessors)
        gltf.accessors.extend([
            Accessor(bufferView=bv_start + 0, componentType=FLOAT, count=vertex_count, type=VEC3, min=min_bound, max=max_bound),
            Accessor(bufferView=bv_start + 1, componentType=FLOAT, count=vertex_count, type=VEC3),
            Accessor(bufferView=bv_start + 2, componentType=FLOAT, count=vertex_count, type=VEC2),
            Accessor(bufferView=bv_start + 3, componentType=UNSIGNED_SHORT, count=vertex_count, type=VEC4),
            Accessor(bufferView=bv_start + 4, componentType=FLOAT, count=vertex_count, type=VEC4),
            Accessor(bufferView=bv_start + 5, componentType=UNSIGNED_SHORT, count=len(indices), type=SCALAR),
        ])

        primitives.append(Primitive(
            attributes=Attributes(
                POSITION=acc_start + 0,
                NORMAL=acc_start + 1,
                TEXCOORD_0=acc_start + 2,
                JOINTS_0=acc_start + 3,
                WEIGHTS_0=acc_start + 4,
            ),
            indices=acc_start + 5,
        ))
        primitive_materials.append(mesh.material_index)

    gltf_mesh = Mesh(name="monster_mesh", primitives=primitives)
    gltf.meshes.append(gltf_mesh)

    mesh_node = Node(name="avatar", mesh=0, skin=0)
    gltf.nodes.append(mesh_node)
    mesh_node_idx = len(gltf.nodes) - 1

    # Add animations
    if animation_names is None:
        motions = mlib.motions
    else:
        motions = [mlib.get_motion_by_name(name) for name in animation_names]
        motions = [m for m in motions if m is not None]

    for motion in motions:
        _add_animation(ctx, model, motion)

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
