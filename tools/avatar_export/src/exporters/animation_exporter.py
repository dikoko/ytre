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
    # Faithful MLIB-pose mode (NPCs): translation tracks from the MLIB
    # skeleton's parent-local offsets, no equip reparenting, no node scale
    # on MLIB-driven bones (scale/reflection lives only in the IBMs, so
    # joint globals stay pure R*T like the engine's bone matrices)
    mlib_translations: bool = False
    mlib: object = None  # MLIBFile, needed for bone offsets in _add_animation
    # MLIB bone indices with live scale keys (option & MOTION_FLAG_SCALING) in ANY
    # motion — these get a scale track in EVERY animation (constant 1s when
    # the motion's gate is off) so scale never leaks across animations.
    scale_track_bones: set[int] = field(default_factory=set)
    # Subset of scale_track_bones whose scale axis is not identity: the
    # engine local is T*R*(Rsa*S*Rsa^T), which one TRS node cannot express.
    # These bones get a factor chain of two extra nodes: bone node T*R ->
    # "{name}_SAS" node Rsa*S -> "{name}_SA" carrier Rsa^T, with the skin
    # joint and child bones on the carrier. Each engine factor lives on
    # its OWN node so Godot's per-node interpolation (slerp rotations,
    # lerp scale) equals the engine's per-factor interpolation at EVERY
    # time, not just on keys: slerp(Rsa^T) == slerp(Rsa)^T, so the
    # carrier cancellation holds mid-key. (A single fused node was only
    # exact ON keys; re-diagonalized gauges spin at scale-eigenvalue
    # crossings and flicker between keys — cn0007's sleeves.)
    sa_track_bones: set[int] = field(default_factory=set)
    # Per-TMD-bone node used as skin joint / parent for children: the SA
    # carrier where one exists, else the bone node itself.
    joint_node_indices: list[int] = field(default_factory=list)
    # TMD bone idx -> "{name}_SAS" node idx (Rsa*S factor node)
    sas_node_indices: dict[int, int] = field(default_factory=dict)


# Motion option bit 3: scale/scale-axis tracks are live only when the
# bit is set; keys with the bit off are dead data the engine never
# samples.
MOTION_FLAG_SCALING = 8

# D3D LH -> glTF RH handedness conversion (same as the ytlevel prop
# pipeline): the whole model is mirrored about Z. Positions/normals get
# z negated, triangle winding reverses, and every transform conjugates by
# S = diag(1,1,-1): rotation matrices R -> S R S, quaternions
# (x,y,z,w) -> (-x,-y,z,w), translations (x,y,z) -> (x,y,-z). Without
# this the render is left-right mirrored (visible on clothing text).
_MIRROR_S = np.diag([1.0, 1.0, -1.0])


def _mirror_quat_xyzw(q):
    return [-q[0], -q[1], q[2], q[3]]


def _base64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode('utf-8')


def _quat_xyzw_to_matrix(q: list[float]) -> np.ndarray:
    """[x, y, z, w] quaternion to 3x3 rotation matrix (column-major math)."""
    x, y, z, w = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
        [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)],
    ])


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
    "@Manteau", "@Rosary",                               # NPC cloth/accessories
)
# NOTE: "@Pipe" was smoothed here until 2026-07-19 — a compensation for the
# pre-MLIB-translations FK drift. It is a rigid held prop; smoothing blurs
# its authored hand-tracking motion.

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


def _build_parent_map(model: TMDModel, mlib: MLIBFile,
                      ordinal: bool = False) -> dict[int, int]:
    """Build parent map using MLIB hierarchy.

    Uses _build_tmd_to_mlib_map for TMD→MLIB mapping (handles name mismatches
    and duplicate names). For parent lookup, uses the inverse of that mapping
    (MLIB parent index → TMD index). ordinal=True uses pure index identity
    (engine binding) — required when MLIB and TMD name the same bone
    differently (ct0079's '@Stage1' is the TMD's '@Root').
    """
    tmd_to_mlib = _build_tmd_to_mlib_map(model, mlib, ordinal=ordinal)
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


def _build_mlib_to_tmd_map(model: TMDModel, mlib: MLIBFile,
                           ordinal: bool = False) -> dict[int, int]:
    """Build MLIB bone index to TMD bone index mapping.

    ordinal=True (faithful/mlib_translations mode): identity over the
    shared range — the engine binds MLIB bone i to object i
    unconditionally; names are labels only (ct0079's MLIB reuses
    '@Root' for four sub-roots the TMD disambiguates).
    Otherwise: match by name, index fallback (legacy avatar/monster path).
    """
    if ordinal:
        n = min(len(model.bones), len(mlib.bones))
        return {i: i for i in range(n)}
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


def _build_tmd_to_mlib_map(model: TMDModel, mlib: MLIBFile,
                           ordinal: bool = False) -> dict[int, int]:
    """Build TMD bone index to MLIB bone index mapping.

    ordinal=True: identity over the shared range (see _build_mlib_to_tmd_map).
    Otherwise: match by name (1:1 only), index fallback.
    """
    if ordinal:
        n = min(len(model.bones), len(mlib.bones))
        return {i: i for i in range(n)}
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
    parent_map = _build_parent_map(model, mlib, ordinal=ctx.mlib_translations)
    ctx.original_parent_map = dict(parent_map)

    # Detect and apply equip bone reparenting (unless skipped).
    # mlib_translations mode never reparents: the MLIB hierarchy already
    # parents equips correctly and translation tracks carry the offsets.
    if ctx.mlib_translations or ctx.skip_reparent:
        ctx.equip_reparent = {}
    else:
        ctx.equip_reparent = _detect_equip_reparents(model, parent_map)
    if ctx.equip_reparent:
        for bone_idx, new_parent_idx in ctx.equip_reparent.items():
            parent_map[bone_idx] = new_parent_idx

    # Get world positions from TMD (z negated: LH -> RH mirror)
    world_pos = []
    for bone in model.bones:
        world_pos.append([
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            -bone.world_transform.translation.z,
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
                local_rot = _mirror_quat_xyzw([r.x, r.y, r.z, r.w])
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
            R_full = _MIRROR_S @ R_full @ _MIRROR_S
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
        if ctx.mlib_translations and ctx.tmd_to_mlib.get(i) is not None:
            # Engine joint globals are pure R*T (MLIB); TMD scale/reflection
            # enters only through the IBMs. Node scale would distort the
            # MLIB translation tracks under Godot's TRS composition.
            has_scale = False
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

    # SA factor chain: bone node T*R -> "{name}_SAS" (Rsa*S) ->
    # "{name}_SA" carrier (Rsa^T), children + skin joint on the carrier —
    # composing to the exact engine T*R*(Rsa*S*Rsa^T) at every
    # interpolated time (each factor interpolates on its own node exactly
    # as the engine interpolates it).
    ctx.joint_node_indices = list(ctx.bone_node_indices)
    if ctx.mlib_translations and ctx.sa_track_bones:
        for bone_idx in range(len(model.bones)):
            mlib_idx = ctx.tmd_to_mlib.get(bone_idx)
            if mlib_idx is None or mlib_idx not in ctx.sa_track_bones:
                continue
            bone_node_idx = ctx.bone_node_indices[bone_idx]
            bone_node = gltf.nodes[bone_node_idx]
            carrier = Node(name=bone_node.name + "_SA",
                           children=bone_node.children)
            gltf.nodes.append(carrier)
            carrier_idx = len(gltf.nodes) - 1
            sas = Node(name=bone_node.name + "_SAS",
                       children=[carrier_idx])
            gltf.nodes.append(sas)
            sas_idx = len(gltf.nodes) - 1
            bone_node.children = [sas_idx]
            ctx.sas_node_indices[bone_idx] = sas_idx
            ctx.joint_node_indices[bone_idx] = carrier_idx

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

    # Create skin (joints are the SA carriers where present — their world
    # transform is the full engine bone matrix)
    skin = Skin(
        name="AvatarSkin",
        joints=ctx.joint_node_indices,
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
    """Build inverse bind matrices from the TMD STATIC world transforms.

    The original client skins vertices with W_runtime @ inv(static world) —
    the authored TMD bone world transforms VERBATIM, embedded scale and
    reflections included. Node rest poses in the GLB are cosmetic
    (animation tracks overwrite them), but the IBMs are load-bearing:
    deriving them from any re-posed or cleaned rotation set (the old
    stand-frame-0 hybrid for reflection rigs, or SVD-polished matrices)
    skews every skinned vertex even while node FK stays exact — the
    ct0016/cn0090 "walking library" distortion, 10 reflection rigs
    fleet-wide (2026-07-26). glTF allows arbitrary IBM matrices, so the
    authored transform goes in untouched, mirrored by S=diag(1,1,-1) like
    all rig data. Scale-axis carrier joints share the bone's static bind:
    at bind time scale is 1, so the carrier world equals the bone world.

    world_pos/world_rot_full are unused now (kept for signature stability
    with the node-rest builder, which still needs them).
    """
    ibm_data = []

    for bone_idx in range(len(model.bones)):
        bone = model.bones[bone_idx]
        R_authored = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
        R = _MIRROR_S @ R_authored @ _MIRROR_S
        t = bone.world_transform.translation
        pos = np.array([t.x, t.y, -t.z])

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


def _slerp_xyzw(a, b, t):
    """Slerp with hemisphere correction, [x,y,z,w] lists/arrays."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 1 - 1e-9:
        q = a + t * (b - a)
    else:
        th = np.arccos(min(1.0, d))
        q = (np.sin((1 - t) * th) * a + np.sin(t * th) * b) / np.sin(th)
    return q / np.linalg.norm(q)


def _sample_expanded(motion: MLIBMotion, mlib_idx: int, fr: float):
    """(rotation quat [x,y,z,w], scale-axis quat, scale vec) at fractional
    frame fr — slerp/lerp of the expanded per-frame tracks, which matches
    the engine's key interpolation (subdividing a slerp geodesic stays on
    the geodesic; keys sit on integer frames)."""
    f0 = int(fr)
    f1 = min(f0 + 1, motion.frame_count - 1)
    t = fr - f0
    r0, r1 = motion.rotations[f0][mlib_idx], motion.rotations[f1][mlib_idx]
    q = _slerp_xyzw([r0.x, r0.y, r0.z, r0.w], [r1.x, r1.y, r1.z, r1.w], t)
    sa = None
    if motion.scale_axes:
        a0, a1 = motion.scale_axes[f0][mlib_idx], motion.scale_axes[f1][mlib_idx]
        sa = _slerp_xyzw([a0.x, a0.y, a0.z, a0.w], [a1.x, a1.y, a1.z, a1.w], t)
    s0, s1 = motion.scales[f0][mlib_idx], motion.scales[f1][mlib_idx]
    sv = np.array([
        (1 - t) * s0.x + t * s1.x,
        (1 - t) * s0.y + t * s1.y,
        (1 - t) * s0.z + t * s1.z,
    ])
    return q, sa, sv


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
        sa_live = (bool(motion.option & MOTION_FLAG_SCALING) and bool(motion.scales)
                   and bool(motion.scale_axes)
                   and mlib_idx is not None
                   and mlib_idx < motion.bone_count)
        is_sa_bone = (mlib_idx is not None
                      and tmd_idx in ctx.sas_node_indices)

        # Faithful MLIB-pose mode: every MLIB-driven bone gets a translation
        # track from the MLIB skeleton's parent-local offsets (per-frame for
        # extended motions, else the constant bind offset). The engine
        # FKs the MLIB hierarchy with exactly these offsets.
        # Bone 0 is excluded when root_positions provides its channel.
        if (
            ctx.mlib_translations
            and mlib_idx is not None
            and mlib_idx < motion.bone_count
            and not (tmd_idx == 0 and motion.root_positions)
        ):
            b = ctx.mlib.bones[mlib_idx]
            if motion.translations:
                translations = [
                    [t.x, t.y, -t.z]
                    for t in (motion.translations[f][mlib_idx]
                              for f in range(motion.frame_count))
                ]
            else:
                translations = [[b.position.x, b.position.y, -b.position.z]
                                ] * motion.frame_count
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
                # MLIB [w,x,y,z] -> GLTF [x,y,z,w], conjugated by the
                # LH -> RH mirror
                q = _mirror_quat_xyzw(
                    [mlib_rot.x, mlib_rot.y, mlib_rot.z, mlib_rot.w])
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

        # Smooth physics bones (skirt, hair, breast) to reduce baked cloth
        # sim pops. NEVER smooth SA bones: their rotation couples with the
        # Rsa*S*Rsa^T factor chain and their engine-truth motion is
        # already smooth now that real key tracks are exported (cn0007
        # cape).
        is_physics = (
            any(bone_name.startswith(p) for p in _PHYSICS_BONE_PREFIXES)
            or tmd_idx in ctx.smooth_bone_indices
        )
        if is_physics and not is_sa_bone:
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
            count=len(quats),
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

        # Scale channel (plain scale bones, identity Rsa): engine FK
        # composes S*R locals through the parent's full matrix,
        # matching glTF TRS with a scale track. SA
        # bones carry their scale on the _SAS factor node instead.
        if (mlib_idx is not None and mlib_idx in ctx.scale_track_bones
                and not is_sa_bone):
            live = bool(motion.option & MOTION_FLAG_SCALING) and bool(motion.scales)
            scale_values = []
            for frame in range(motion.frame_count):
                if live and mlib_idx < motion.bone_count:
                    s = motion.scales[frame][mlib_idx]
                    scale_values.extend([s.x, s.y, s.z])
                else:
                    scale_values.extend([1.0, 1.0, 1.0])
            scale_bin = np.array(scale_values, dtype=np.float32).tobytes()
            scale_offset = len(ctx.buffer)
            ctx.buffer.extend(scale_bin)

            gltf.bufferViews.append(BufferView(
                buffer=0, byteOffset=scale_offset, byteLength=len(scale_bin)))
            gltf.accessors.append(Accessor(
                bufferView=len(gltf.bufferViews) - 1,
                componentType=FLOAT,
                count=motion.frame_count,
                type=VEC3,
            ))
            anim.samplers.append(AnimationSampler(
                input=time_acc, output=len(gltf.accessors) - 1))
            anim.channels.append(AnimationChannel(
                sampler=len(anim.samplers) - 1,
                target=AnimationChannelTarget(
                    node=ctx.bone_node_indices[tmd_idx], path="scale"),
            ))

        # SA factor-chain channels: the AUTHORED factors, each on its own
        # node — _SAS rotation = Rsa, _SAS scale = S, carrier rotation =
        # Rsa^T (identity/unit when the motion's scale gate is off;
        # tracked in every animation to avoid leaks). Godot slerps Rsa
        # and Rsa^T and lerps S per node exactly as the engine does per
        # factor, so the composed
        # product matches engine truth at EVERY playback time. Do NOT
        # fuse or re-diagonalize these factors: fused gauges spin at
        # scale-eigenvalue crossings and flicker between keys.
        if is_sa_bone:
            sa_quats = []
            scale_vals = []
            prev_sq = None
            for frame in range(motion.frame_count):
                if sa_live:
                    a = motion.scale_axes[frame][mlib_idx]
                    # scale-axis rotation conjugates with the LH -> RH
                    # mirror like every other rotation (S Rsa S); the
                    # diagonal scale values are mirror-invariant
                    sq = _mirror_quat_xyzw([a.x, a.y, a.z, a.w])
                    s = motion.scales[frame][mlib_idx]
                    scale_vals.extend([s.x, s.y, s.z])
                else:
                    sq = [0.0, 0.0, 0.0, 1.0]
                    scale_vals.extend([1.0, 1.0, 1.0])
                if prev_sq is not None and sum(
                        a_ * b_ for a_, b_ in zip(prev_sq, sq)) < 0:
                    sq = [-c for c in sq]
                prev_sq = sq
                sa_quats.append(sq)

            sas_rot = []
            carrier_rot = []
            for sq in sa_quats:
                sas_rot.extend(sq)
                carrier_rot.extend([-sq[0], -sq[1], -sq[2], sq[3]])

            for vals, ncomp, vtype, node, path in (
                (sas_rot, 4, VEC4, ctx.sas_node_indices[tmd_idx], "rotation"),
                (scale_vals, 3, VEC3, ctx.sas_node_indices[tmd_idx], "scale"),
                (carrier_rot, 4, VEC4, ctx.joint_node_indices[tmd_idx], "rotation"),
            ):
                vbin = np.array(vals, dtype=np.float32).tobytes()
                voff = len(ctx.buffer)
                ctx.buffer.extend(vbin)
                gltf.bufferViews.append(BufferView(
                    buffer=0, byteOffset=voff, byteLength=len(vbin)))
                gltf.accessors.append(Accessor(
                    bufferView=len(gltf.bufferViews) - 1,
                    componentType=FLOAT,
                    count=motion.frame_count,
                    type=vtype,
                ))
                anim.samplers.append(AnimationSampler(
                    input=time_acc, output=len(gltf.accessors) - 1))
                anim.channels.append(AnimationChannel(
                    sampler=len(anim.samplers) - 1,
                    target=AnimationChannelTarget(node=node, path=path),
                ))

    # Root bone translation channel
    if motion.root_positions:
        # Root translation applies to bone index 0 (hierarchy root),
        # not necessarily the bone named @Root (which may be deeper).
        root_tmd_idx = 0
        if root_tmd_idx < len(model.bones):
            # Root rule, matching retail client behavior: the skeleton
            # root's X/Y come from bone 0's own translation track — the
            # authored absolute pose (walk/run crouches live here). The
            # separate root-position track is the ENTITY displacement
            # track: per-frame deltas when the locomotion flag (bit 0) is
            # set (equal to the frame-derivative of bone 0's track in
            # shipped data), which the original client integrates into
            # entity movement with X/Y zeroed — never applied to the
            # skeleton. Root Z pins at the motion origin while moving
            # (viewers play in place; forward travel belongs to the
            # entity) and follows the root-position track otherwise. The
            # fixed-Y flag (bit 4) freezes Y the same way (no shipped
            # motion sets it). The previous "zero-mean + bind height"
            # normalization was an invention — every moving walk/run
            # hovered at standing height (ct0021: +0.45 too high).
            is_moving = (motion.option & 1) != 0    # locomotion flag
            fix_y = (motion.option & 16) != 0       # fixed-Y flag
            origin = motion.origin
            trans_values = []
            for f, rp in enumerate(motion.root_positions):
                frame_tk = motion.translations[f] if motion.translations else None
                if frame_tk:
                    x, y = frame_tk[0].x, frame_tk[0].y
                else:
                    x, y = rp.x, rp.y   # no translation tracks: legacy absolute root
                if is_moving:
                    z = origin.z
                    if fix_y:
                        y = origin.y
                else:
                    z = rp.z
                    if fix_y:
                        y = rp.y
                trans_values.extend([x, y, -z])  # z negated: LH -> RH

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
        positions.extend([v.x, v.y, -v.z])
        n = mesh.normals[old_idx]
        normals_list.extend([n.x, n.y, -n.z])
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

    # Re-indexed face indices (winding reversed: the Z mirror flips
    # triangle orientation)
    indices = []
    for face in face_list:
        indices.extend([old_to_new[face[0]], old_to_new[face[2]], old_to_new[face[1]]])

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


def _extend_bones_with_animation_targets(model: TMDModel, mlib: MLIBFile) -> None:
    """Rebuild model.bones as bone AND dummy objects in object order when
    that aligns the list ordinally with the MLIB skeleton.

    The engine binds MLIB tracks by ordinal over the FULL object
    list; DUMMY-chunk objects
    (e.g. cn0090's Dummy01 animation root) are animation targets too.
    The parser's filtered bone list drops them, shifting every later bone
    out of the MLIB index space — name matching papered over most of this,
    but fails when dummy targets carry unique animated transforms.

    Only swaps the list when it strictly improves ordinal name agreement,
    so models without interleaved dummies are untouched.
    """
    from src.parsers.tmd_parser import TMDBone

    mlib_names = [b.name.strip() for b in mlib.bones]
    cur_names = [b.name.strip() for b in model.bones]
    ext_objs = [o for o in model.objects if o.object_type in ("bone", "dummy")]
    ext_names = [o.name.strip() for o in ext_objs]

    score_cur = sum(1 for a, b in zip(mlib_names, cur_names) if a == b)
    score_ext = sum(1 for a, b in zip(mlib_names, ext_names) if a == b)
    if score_ext <= score_cur:
        return

    model.bones = [
        TMDBone(
            name=o.name,
            object_id=o.object_id,
            world_transform=o.world_transform,
            local_transform=o.local_transform,
        )
        for o in ext_objs
    ]


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
    mlib_translations: bool = False,
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

    if mlib_translations:
        _extend_bones_with_animation_targets(model, mlib)

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
                        skip_reparent=skip_reparent,
                        mlib_translations=mlib_translations, mlib=mlib)
    ctx.mlib_to_tmd = _build_mlib_to_tmd_map(model, mlib,
                                             ordinal=mlib_translations)
    ctx.tmd_to_mlib = _build_tmd_to_mlib_map(model, mlib,
                                             ordinal=mlib_translations)
    ctx.tmd_name_to_idx = {b.name.strip(): i for i, b in enumerate(model.bones)}
    ctx.mlib_name_to_idx = {b.name.strip(): i for i, b in enumerate(mlib.bones)}

    # Bones with live scale keys anywhere get scale tracks in every anim
    for m in mlib.motions:
        if not (m.option & MOTION_FLAG_SCALING) or not m.scales:
            continue
        for fr in m.scales:
            for bi, s in enumerate(fr):
                if (abs(s.x - 1) > 1e-4 or abs(s.y - 1) > 1e-4
                        or abs(s.z - 1) > 1e-4):
                    ctx.scale_track_bones.add(bi)
    # Scaled bones with a non-identity scale axis need the SA carrier chain
    for m in mlib.motions:
        if not (m.option & MOTION_FLAG_SCALING) or not m.scale_axes:
            continue
        for fr in m.scale_axes:
            for bi, q in enumerate(fr):
                if bi in ctx.scale_track_bones and abs(abs(q.w) - 1.0) > 1e-4:
                    ctx.sa_track_bones.add(bi)

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

        # Default path: one primitive per mesh (avatar behavior).
        # Z negated + winding reversed: LH -> RH mirror.
        positions = []
        for v in mesh.vertices:
            positions.extend([v.x, v.y, -v.z])

        normals = []
        for n in mesh.normals:
            normals.extend([n.x, n.y, -n.z])

        uvs = []
        for uv in mesh.uvs:
            uvs.extend([uv.u, 1.0 - uv.v if v_flip else uv.v])

        indices = []
        for face in mesh.faces:
            indices.extend([face[0], face[2], face[1]])

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
