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
    Animation, AnimationChannel, AnimationChannelTarget, AnimationSampler,
    UNSIGNED_SHORT, UNSIGNED_INT, FLOAT, SCALAR, VEC2, VEC3, VEC4,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDModel
from src.exporters.prop_animation import (
    build_animation_plan, d3d_rotation_matrix, godot_local_factors, has_shear,
    local_trs_d3d, quat_from_d3d_matrix, to_godot_basis, to_godot_matrix,
    to_godot_translation,
)

# Godot's RenderingServer refuses surfaces past this per-mesh cap
# (RS::MAX_MESH_SURFACES) — meshes with more primitives get truncated with
# per-surface import errors, so export_prop chunks across multiple meshes.
MAX_MESH_SURFACES = 256


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
    flip_winding: bool,
    mirror_x: bool = False,
    node_rot_T: np.ndarray | None = None,
    node_rot_inv: np.ndarray | None = None,
    node_trans: np.ndarray | None = None,
) -> Primitive:
    """Build a GLTF Primitive from a subset of faces — no skinning data.

    node_rot_T / node_rot_inv / node_trans: per-object TMD world transform
    (rotation transpose, rotation inverse, translation), or None for an
    untransformed (identity) node. See the baking comment below.
    """
    # Collect unique vertices, build re-index map
    old_indices = set()
    for face in face_list:
        old_indices.update(face)
    old_indices_sorted = sorted(old_indices)
    old_to_new = {old: new for new, old in enumerate(old_indices_sorted)}

    raw_pos = np.array([mesh.vertices[i].to_tuple() for i in old_indices_sorted], dtype=np.float64)
    raw_norm = np.array([mesh.normals[i].to_tuple() for i in old_indices_sorted], dtype=np.float64)

    # Bake TMD per-object world transforms into vertices/normals.
    #
    # These are RENDER transforms, not metadata: the original client
    # stores the per-object world matrix on the object at load time and
    # composes it onto the vertex stream at draw time. Vertices/normals
    # as stored in the TMD file are
    # therefore raw/LOCAL model space, not the authored world-space geometry
    # — ~300 non-identity objects (recount: 309) in SF001001's models alone carry
    # non-identity world transforms (mirrors, rotations, scale up to det 5.56,
    # translations up to 8.6 units). We must apply that matrix ourselves before the
    # D3D->Godot conversion below, in D3D space (row-vector convention,
    # p' = p . M): p_d3d = R.T @ v + t.
    if node_rot_T is not None:
        baked_pos = (node_rot_T @ raw_pos.T).T
        if node_trans is not None:
            baked_pos = baked_pos + node_trans
    else:
        baked_pos = raw_pos

    if node_rot_inv is not None:
        # Normal transform uses the inverse (not transpose) of the rotation
        # so non-uniform scale/shear in the node matrix doesn't distort
        # normal direction: n_d3d = inv(R) @ n, renormalized.
        baked_norm = (node_rot_inv @ raw_norm.T).T
        lengths = np.linalg.norm(baked_norm, axis=1)
        zero_mask = lengths < 1e-12
        safe_lengths = np.where(zero_mask, 1.0, lengths)
        baked_norm = baked_norm / safe_lengths[:, None]
        if np.any(zero_mask):
            # Baked normal collapsed to zero for this vertex — fall back to
            # the raw authored normal; the per-vertex sign-alignment pass
            # below still corrects its direction.
            baked_norm[zero_mask] = raw_norm[zero_mask]
    else:
        # Singular node rotation (det(R) ~ 0 — degenerate/flattened-effect
        # objects exist in the data) — baking the normal is ill-defined.
        # Fall back to the raw authored normal; sign-alignment handles
        # direction from there.
        baked_norm = raw_norm

    positions = []
    normals_list = []
    uvs = []
    exported_pos = {}
    exported_norm = {}

    for new_idx, old_idx in enumerate(old_indices_sorted):
        bp = baked_pos[new_idx]
        # Base D3D->Godot conversion mirrors Z. mirror_x layers ONE additional
        # mirror across X on top of that (used for negative-determinant map
        # placements that need a mesh mirrored across X — see write_tscn in
        # scripts/30_export_map.py) — positions/normals both pick up the extra
        # x negation.
        pos = (-bp[0] if mirror_x else bp[0], bp[1], -bp[2])
        positions.extend(pos)
        exported_pos[old_idx] = pos
        bn = baked_norm[new_idx]
        # Mirror transform: with vertices Z-negated, normals mirror the same way
        # (n.x, n.y, -n.z). The previous (-n.x, -n.y, n.z) was the negation of
        # this — the root cause of dark flat props.
        norm = (-bn[0] if mirror_x else bn[0], bn[1], -bn[2])
        normals_list.extend(norm)
        exported_norm[old_idx] = norm
        uv = mesh.uvs[old_idx]
        uvs.extend([uv.u, 1.0 - uv.v if v_flip else uv.v])

    # Round 5: uniform winding reversal.
    #
    # D3D renders with counter-clockwise culling — i.e. the
    # front face is the one whose vertex order is CW in D3D's left-handed
    # view, which is the same side as the RH cross product of the stored
    # index order. Godot's front face is also the +RH-cross side of its
    # (right-handed, CCW-front) index order. So absent any mirroring, D3D
    # order and Godot order agree and no reversal is needed.
    #
    # Node transforms (including any object-level mirror, det(rotation) ==
    # -1 for ~300 objects library-wide) are now baked directly into the
    # vertex positions/normals (see the node-transform baking comment above
    # and export_prop's node_rot_T/node_rot_inv). That means the baked
    # geometry this function receives already equals D3D-world geometry —
    # any mirror the object's own transform carried has already been
    # applied to the vertices, not left for winding to compensate for.
    #
    # Our D3D->Godot conversion then negates Z on every vertex/normal (see
    # the position/normal comments above), which is a mirror: it flips
    # handedness once, and only once, for every object, regardless of that
    # object's own det. Since front-face is defined the same way (+RH-cross
    # side) in both engines, that single Z-mirror is the only flip in play
    # for every exported mesh, so the stored index order must be REVERSED
    # uniformly to keep the same physical faces visible.
    #
    # Evidence: with baking landed but the old det-aware rule still in
    # place, det<0 props (a_SEtrack01/02/03, a_SEstand03_1 — the same
    # objects that used to need manual mirror/flip overrides in the old
    # Godot-runtime-override pipeline) rendered backface-culled (edge-on
    # slivers, near-black). Switching those objects to the same reversal as
    # every other object fixes it: winding is uniformly reversed for the baked
    # geometry itself, independent of the object's own det<0 status.
    #
    # flip_winding is passed in by export_prop as a constant True, XORed
    # with mirror_x (an extra, separate mirror layered on top for
    # negative-determinant map placements — see export_prop's docstring).
    indices = []
    emitted_faces = []
    for face in face_list:
        i0, i1, i2 = face
        n0, n1, n2 = old_to_new[i0], old_to_new[i1], old_to_new[i2]
        if flip_winding:
            indices.extend([n0, n2, n1])
            emitted_faces.append((i0, i2, i1))
        else:
            indices.extend([n0, n1, n2])
            emitted_faces.append((i0, i1, i2))

    vertex_count = len(old_to_new)

    # Normal sign-alignment.
    #
    # A census of the TMD data shows authored normals are unreliable: most
    # props' normals equal the RH cross product of their D3D winding — i.e.
    # they point out the CULLED side, not the rendered front — while some
    # (e.g. the running track) are authored the opposite way (consistently),
    # and others are internally mixed (c_SEbench03: 56/56 faces each way).
    # The original engine hid this: fixed-function D3D9 with a forced
    # material ambient of 0.7 (the loader's default-material path) was
    # ambient-dominant, so normal direction barely affected shading. Godot's
    # lighting exposes it directly (props render near-black when their
    # normals face away from the camera/light).
    #
    # Convention: triangle winding stays authoritative for visibility
    # (decided above, uniform Z-mirror reversal); each vertex normal's SIGN is
    # instead aligned to the geometric front of its adjacent exported faces, one
    # vote per face-vertex incidence. This preserves authored
    # smoothing/direction up to sign — it does not re-derive normals from
    # scratch, only flips them where they disagree with the geometry they
    # shade. Runs AFTER winding is decided, using the EMITTED face order so
    # the geometric normal g matches what Godot will treat as front (safety
    # net for meshes with genuinely inconsistent authored normals, e.g.
    # c_SEbench03, 56/56 mixed).
    votes = [0.0] * vertex_count
    for face in emitted_faces:
        i0, i1, i2 = face
        q0 = np.array(exported_pos[i0])
        q1 = np.array(exported_pos[i1])
        q2 = np.array(exported_pos[i2])
        g = np.cross(q1 - q0, q2 - q0)
        g_len = np.linalg.norm(g)
        if g_len == 0.0:
            continue
        for i in (i0, i1, i2):
            n = np.array(exported_norm[i])
            n_len = np.linalg.norm(n)
            if n_len == 0.0:
                continue
            d = np.dot(g, n)
            if d > 0.0:
                votes[old_to_new[i]] += 1.0
            elif d < 0.0:
                votes[old_to_new[i]] -= 1.0
            # d == 0.0 (perpendicular): no vote

    normals_arr = np.array(normals_list, dtype=np.float32).reshape(-1, 3)
    for new_idx, vote in enumerate(votes):
        if vote < 0.0:
            normals_arr[new_idx] *= -1.0
    normals_list = normals_arr.reshape(-1).tolist()

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


def _mirror_x_conjugate(basis: np.ndarray) -> np.ndarray:
    """Layer the extra X mirror onto an already-Godot-space basis."""
    mx = np.diag([-1.0, 1.0, 1.0])
    return mx @ basis @ mx


def _decompose_trs(basis: np.ndarray, trans) -> tuple[list, list, list]:
    """Godot-space basis + translation -> glTF (translation, rotation, scale).

    Scale comes from the column norms. A negative determinant cannot be
    carried by a rotation quaternion, so the reflection is folded into the
    X scale — glTF permits negative scale and Godot honours it.
    """
    scale = np.linalg.norm(basis, axis=0)
    safe = np.where(scale < 1e-12, 1.0, scale)
    rot_only = basis / safe
    scale = scale.astype(np.float64).copy()
    if np.linalg.det(rot_only) < 0.0:
        rot_only = rot_only.copy()
        rot_only[:, 0] *= -1.0
        scale[0] *= -1.0
    # quat_from_d3d_matrix expects the D3D (row-vector) orientation, which is
    # the transpose of the column-vector basis we hold here.
    quat = quat_from_d3d_matrix(rot_only.T)
    return ([float(v) for v in trans], list(quat), [float(s) for s in scale])


def _node_trs_from_local(anim, mirror_x: bool, key_index: int = 0):
    """glTF TRS for an animated node at a key index."""
    basis_d3d, trans_d3d = local_trs_d3d(anim, key_index)
    basis = to_godot_basis(basis_d3d)
    trans = to_godot_translation(trans_d3d)
    if mirror_x:
        basis = _mirror_x_conjugate(basis)
        trans = (-trans[0], trans[1], trans[2])
    return _decompose_trs(basis, trans)


def _rotation_list(basis: np.ndarray, mirror_x: bool) -> list[float]:
    """glTF rotation quaternion for a pure-rotation Godot-space basis."""
    if mirror_x:
        basis = _mirror_x_conjugate(basis)
    if np.linalg.det(basis) < 0.0:
        # Shouldn't happen for A/Q (both proper rotations), but never emit a
        # reflection as a quaternion — it would silently drop the mirror.
        raise ValueError("reflection passed to _rotation_list")
    return list(quat_from_d3d_matrix(basis.T))


def _column_major(m: np.ndarray) -> list[float]:
    """glTF node.matrix is column-major (glTF 2.0 spec)."""
    return [float(v) for v in np.asarray(m, dtype=np.float64).T.reshape(-1)]


def _push_sampler(gltf: GLTF2, buf: bytearray, samplers: list,
                  frames: list[float], values: np.ndarray, fps: float) -> int:
    """Pack one animation sampler into the GLB; returns its index in `samplers`.

    Interpolation is LINEAR for every track: the original client lerps
    position and scale and slerps rotation, and the slerp's `spin` term
    always evaluates to 0 (|w1-w0| <= 2 < 2*pi), so it is
    plain shortest-path slerp. glTF LINEAR plus Godot's Quaternion.slerp
    match that exactly, so sparse keys need no resampling.
    """
    times = np.asarray([f / fps for f in frames], dtype=np.float32)
    values = np.asarray(values, dtype=np.float32)

    t_bin = times.tobytes()
    t_offset = len(buf)
    buf.extend(t_bin)
    v_bin = values.tobytes()
    v_offset = len(buf)
    buf.extend(v_bin)

    bv = len(gltf.bufferViews)
    gltf.bufferViews.extend([
        BufferView(buffer=0, byteOffset=t_offset, byteLength=len(t_bin)),
        BufferView(buffer=0, byteOffset=v_offset, byteLength=len(v_bin)),
    ])
    acc = len(gltf.accessors)
    gltf.accessors.extend([
        Accessor(bufferView=bv, componentType=FLOAT, count=len(times),
                 type=SCALAR, min=[float(times.min())], max=[float(times.max())]),
        Accessor(bufferView=bv + 1, componentType=FLOAT, count=len(values),
                 type=VEC4 if values.shape[1] == 4 else VEC3),
    ])
    samplers.append(AnimationSampler(input=acc, output=acc + 1,
                                     interpolation="LINEAR"))
    return len(samplers) - 1


def _same_hemisphere(quats: np.ndarray) -> np.ndarray:
    """Make consecutive quaternions lie in the same hemisphere.

    q and -q are the same rotation, but a LINEAR sampler interpolates the raw
    components — a sign flip between neighbouring keys would spin the long way
    round. The original client handles this at sample time (the `flip` term in
    quaternion slerp); glTF has to bake it into the data.
    """
    out = np.asarray(quats, dtype=np.float64).copy()
    for i in range(1, len(out)):
        if float(np.dot(out[i - 1], out[i])) < 0.0:
            out[i] = -out[i]
    return out


def _track_frames(keys) -> list[float]:
    return [float(k.frame) for k in keys]


def _build_animations(gltf: GLTF2, buf: bytearray, plan, anim_targets: dict,
                      mirror_x: bool) -> None:
    """Emit glTF animation channels for every animated object in the plan.

    Each authored track maps onto exactly one node so nothing has to be
    resampled or merged: position and rotation drive the outer node, scale
    drives the diagonal node, and the scale-axis drives the two rotation
    nodes that bracket it (as Q^T and Q).
    """
    fps = plan.fps or 30.0
    samplers: list = []
    channels: list = []

    def add(node_idx: int, path: str, frames: list[float], values) -> None:
        if node_idx is None or len(frames) < 2:
            return
        idx = _push_sampler(gltf, buf, samplers, frames, values, fps)
        channels.append(AnimationChannel(
            sampler=idx,
            target=AnimationChannelTarget(node=node_idx, path=path),
        ))

    for obj_index, node in plan.animated.items():
        targets = anim_targets.get(obj_index)
        if not targets:
            continue
        anim = node.animation
        sheared = "axis" in targets

        if len(anim.position_keys) > 1:
            vals = np.array([to_godot_translation(k.position.to_list())
                             for k in anim.position_keys])
            if mirror_x:
                vals = vals.copy()
                vals[:, 0] *= -1.0
            add(targets["translation"], "translation",
                _track_frames(anim.position_keys), vals)

        if len(anim.rotation_keys) > 1:
            quats = []
            for k in anim.rotation_keys:
                basis = to_godot_basis(d3d_rotation_matrix(k.rotation))
                if mirror_x:
                    basis = _mirror_x_conjugate(basis)
                quats.append(quat_from_d3d_matrix(basis.T))
            add(targets["rotation"], "rotation",
                _track_frames(anim.rotation_keys), _same_hemisphere(quats))

        if len(anim.scale_keys) > 1:
            if sheared:
                # The diagonal factor D; the tilt lives on the axis nodes.
                vals = np.array([k.scale.to_list() for k in anim.scale_keys])
                add(targets["scale"], "scale",
                    _track_frames(anim.scale_keys), vals)
            else:
                # No shear: fold scale straight onto the single TRS node,
                # recomputing per key so a mirror stays in the scale sign.
                vals = []
                for k in range(len(anim.scale_keys)):
                    trs = _node_trs_from_local(anim, mirror_x, k)
                    vals.append(trs[2])
                add(targets["scale"], "scale",
                    _track_frames(anim.scale_keys), np.array(vals))

        if sheared and len(anim.scale_axis_keys) > 1:
            frames = _track_frames(anim.scale_axis_keys)
            q_quats, qt_quats = [], []
            for k in range(len(anim.scale_axis_keys)):
                _a, qt_m, _d, q_m = godot_local_factors(anim, k)
                if mirror_x:
                    q_m = _mirror_x_conjugate(q_m)
                    qt_m = _mirror_x_conjugate(qt_m)
                q_quats.append(quat_from_d3d_matrix(q_m.T))
                qt_quats.append(quat_from_d3d_matrix(qt_m.T))
            add(targets["axis"], "rotation", frames, _same_hemisphere(q_quats))
            add(targets["axis_inv"], "rotation", frames,
                _same_hemisphere(qt_quats))

    if not channels:
        return

    # One full-timeline animation. Named ranges are NOT emitted as glTF
    # animations: they would be full-length copies under a range name, which
    # the runtime once mistook for trimmed clips (the street lamp played its
    # entire off->on->off cycle instead of holding idle). Range windows live
    # in the sidecar; the runtime seeks within "default".
    gltf.animations.append(
        Animation(name="default", samplers=samplers, channels=channels)
    )


def export_prop(
    model: TMDModel,
    output_path: Path | str,
    prop_id: str = "prop",
    v_flip: bool = False,
    mirror_x: bool = False,
) -> None:
    """Export TMD prop model as static GLB with multi-material support.

    Args:
        model: Parsed TMD model
        output_path: Path to output GLB file
        prop_id: Name for the root node (used in Godot scene tree)
        v_flip: Apply UV V-flip (False for props, same as monsters/NPCs)
        mirror_x: Apply one additional mirror across X on top of the base
            Z-mirror D3D->Godot conversion (positions/normals x-negated,
            winding XORed with the uniform base reversal). Used to produce
            `{prop_id}_mirrorx.glb` variants for negative-determinant map
            placements (see scripts/30_export_map.py write_tscn).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gltf = GLTF2(asset=Asset(version="2.0", generator="avatar_export.prop_exporter"))
    buf = bytearray()

    primitives = []
    # Iterate model.objects (not model.meshes) so each mesh keeps its object
    # association — node-transform baking (node_rot_T/node_rot_inv/trans) is
    # per-object, driven by that object's own world_transform. flip_winding
    # itself is now uniform (see the Round 5 comment in
    # _build_prop_primitive), not object-dependent. Primitive ORDER is no
    # longer stable across paths (animated meshes emit mid-walk, static
    # primitives chunk after it), so every primitive is stamped with its TMD
    # material index and embed_textures remaps by that stamp, never by
    # position.
    plan = build_animation_plan(model, prop_id)
    # glTF node index of each animated object's mesh-bearing node, so later
    # passes (parenting, animation channels) can find them by object index.
    anim_node_idx: dict[int, int] = {}
    anim_pivot_idx: dict[int, int] = {}
    # Which glTF node carries which authored track, per animated object.
    # Plain objects put everything on one TRS node; sheared objects spread
    # the four factors across the chain (see godot_local_factors).
    anim_targets: dict[int, dict[str, int]] = {}

    for obj_index, obj in enumerate(model.objects):
        mesh = obj.mesh
        if mesh is None:
            continue

        node = plan.animated.get(obj_index)
        if node is not None:
            # ---- animated path: geometry stays in object-LOCAL space ----
            #
            # The per-vertex Z-negation still happens inside
            # _build_prop_primitive, in the object's own frame. The node
            # transforms are the mirrored local matrix and pivot. Because
            # S.S == I, composing them reproduces the mirrored world result:
            #     godot(P) @ godot(L) @ (S.v) == S . (v . L . P)
            # so no extra compensation is needed anywhere.
            flip_winding = not mirror_x
            local_prims = []
            for mat_idx, face_list in _split_mesh_by_material(mesh):
                prim = _build_prop_primitive(
                    gltf, buf, mesh, face_list, v_flip, flip_winding, mirror_x,
                    node_rot_T=None, node_rot_inv=None, node_trans=None,
                )
                # Provisional TMD material index; embed_textures remaps it to
                # the real glTF material (see the comment on the static path).
                prim.material = mat_idx
                local_prims.append(prim)
            mesh_idx = len(gltf.meshes)
            gltf.meshes.append(
                Mesh(name=f"{node.node_name}_mesh", primitives=local_prims)
            )

            pivot_godot = to_godot_matrix(node.pivot_d3d)
            if mirror_x:
                mxm = np.diag([-1.0, 1.0, 1.0, 1.0])
                pivot_godot = mxm @ pivot_godot @ mxm
            pivot = Node(name=node.pivot_name, matrix=_column_major(pivot_godot))
            anim_pivot_idx[obj_index] = len(gltf.nodes)
            gltf.nodes.append(pivot)

            if has_shear(node.animation):
                # A scale about a tilted axis is a shear, which a single TRS
                # node cannot hold. Split it into the four factors of
                # godot_local_factors (M = A . Q^T . D . Q); each is
                # TRS-representable and each maps 1:1 onto one authored track,
                # so all four stay animatable rather than frozen.
                a_m, qt_m, d_v, q_m = godot_local_factors(node.animation, 0)
                _basis, trans_d3d = local_trs_d3d(node.animation, 0)
                trans = to_godot_translation(trans_d3d)
                if mirror_x:
                    trans = (-trans[0], trans[1], trans[2])

                chain = [
                    Node(name=f"{node.node_name}_a",
                         translation=list(trans),
                         rotation=_rotation_list(a_m, mirror_x)),
                    Node(name=f"{node.node_name}_axisinv",
                         rotation=_rotation_list(qt_m, mirror_x)),
                    Node(name=f"{node.node_name}_scale",
                         scale=[float(v) for v in d_v]),
                    Node(name=node.node_name, mesh=mesh_idx,
                         rotation=_rotation_list(q_m, mirror_x)),
                ]
                first = len(gltf.nodes)
                for offset, chain_node in enumerate(chain):
                    if offset + 1 < len(chain):
                        chain_node.children = [first + offset + 1]
                    gltf.nodes.append(chain_node)
                pivot.children = [first]
                anim_node_idx[obj_index] = first + len(chain) - 1
                anim_targets[obj_index] = {
                    "translation": first,       # _a  (position keys)
                    "rotation": first,          # _a  (rotation keys -> A)
                    "axis_inv": first + 1,      # _axisinv (scale-axis -> Q^T)
                    "scale": first + 2,         # _scale   (scale keys -> D)
                    "axis": first + 3,          # mesh node (scale-axis -> Q)
                }
                continue

            trs = _node_trs_from_local(node.animation, mirror_x, 0)
            anim_node = Node(name=node.node_name, mesh=mesh_idx,
                             translation=trs[0], rotation=trs[1], scale=trs[2])
            anim_node_idx[obj_index] = len(gltf.nodes)
            gltf.nodes.append(anim_node)
            pivot.children = [anim_node_idx[obj_index]]
            anim_targets[obj_index] = {
                "translation": anim_node_idx[obj_index],
                "rotation": anim_node_idx[obj_index],
                "scale": anim_node_idx[obj_index],
            }
            continue

        # ---- static path: unchanged, bake the world transform ----
        rot = np.array(obj.world_transform.rotation.data, dtype=np.float64).reshape(3, 3)
        trans = np.array(obj.world_transform.translation.to_tuple(), dtype=np.float64)
        det = np.linalg.det(rot)
        # Winding is uniformly reversed for the base export (see the Round 5
        # comment in _build_prop_primitive): node mirrors are baked into the
        # geometry itself now, so every exported mesh differs from D3D-world
        # geometry by exactly the base Z-mirror, independent of this
        # object's own det(rotation). mirror_x is a second, separate mirror
        # layered on top of that base Z-mirror conversion — each mirror
        # flips handedness once, so the two combine via XOR.
        flip_winding = not mirror_x
        # Node-transform baking (see _build_prop_primitive): rotation
        # transpose for positions (D3D row-vector convention), rotation
        # inverse for normals. Guard against singular rotations (det ~ 0 —
        # degenerate/flattened-effect objects exist in the data) where the
        # inverse doesn't exist; _build_prop_primitive falls back to raw
        # normals for those objects.
        node_rot_T = rot.T
        node_rot_inv = np.linalg.inv(rot) if abs(det) >= 1e-8 else None
        mat_groups = _split_mesh_by_material(mesh)
        for mat_idx, face_list in mat_groups:
            prim = _build_prop_primitive(
                gltf, buf, mesh, face_list, v_flip, flip_winding, mirror_x,
                node_rot_T=node_rot_T, node_rot_inv=node_rot_inv, node_trans=trans,
            )
            # Provisional TMD material index, remapped by embed_textures.
            # The old contract — embed_textures zips primitives against
            # model.meshes in object order — broke the day animated objects
            # started emitting their own meshes mid-walk while static
            # primitives collect into a chunk mesh after it (the 2026-08-08
            # street-lamp regression: glow quads wearing the lamp diffuse).
            # Stamping the index here makes the mapping order-independent.
            prim.material = mat_idx
            primitives.append(prim)

    # Godot caps a single Mesh at 256 surfaces (RS::MAX_MESH_SURFACES) and
    # silently DROPS everything past the cap with per-surface errors —
    # a_fountain01 has 314 (object x material) primitives. Chunk primitives
    # across as many meshes/nodes as needed; visually identical.
    node_ids = []
    for start in range(0, len(primitives), MAX_MESH_SURFACES):
        chunk = primitives[start:start + MAX_MESH_SURFACES]
        mesh_idx = len(gltf.meshes)
        suffix = "" if start == 0 else f"_{start // MAX_MESH_SURFACES}"
        gltf.meshes.append(Mesh(name=f"{prop_id}_mesh{suffix}", primitives=chunk))
        node_ids.append(len(gltf.nodes))
        gltf.nodes.append(Node(name=f"{prop_id}{suffix}", mesh=mesh_idx))

    # Parent each pivot under its parent object's ANIMATED node; pivots whose
    # object has no animated parent become scene roots. Done after the loop so
    # forward references (child emitted before parent) resolve.
    for obj_index, node in plan.animated.items():
        pivot_idx = anim_pivot_idx.get(obj_index)
        if pivot_idx is None:
            continue
        parent_idx = anim_node_idx.get(node.parent_object_index)
        if parent_idx is None:
            node_ids.append(pivot_idx)
            continue
        parent = gltf.nodes[parent_idx]
        if parent.children is None:
            parent.children = []
        parent.children.append(pivot_idx)

    _build_animations(gltf, buf, plan, anim_targets, mirror_x)

    scene = Scene(nodes=node_ids)
    gltf.scenes.append(scene)
    gltf.scene = 0

    gltf.buffers.append(Buffer(byteLength=len(buf)))
    gltf.set_binary_blob(bytes(buf))
    gltf.save_binary(str(output_path))
