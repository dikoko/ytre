#!/usr/bin/env python3
"""
Debug Animation Script

Exports skeleton cubes with basic_pick animation to verify animation math
works independently of mesh skinning.

Key fix: Build proper bone hierarchy so child bones move when parents rotate.

Output: debug_anim.glb (cubes at bone positions with animation)
"""

import sys
import math
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import base64
import numpy as np
from pygltflib import (
    GLTF2, Asset, Scene, Node, Mesh, Primitive, Attributes,
    Accessor, BufferView, Buffer,
    Animation, AnimationChannel, AnimationChannelTarget, AnimationSampler,
    UNSIGNED_SHORT, FLOAT, SCALAR, VEC3, VEC4,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER,
)

from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser, Quaternion as MLIBQuat

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
MLIB_PATH = AVATAR_IRD / "motion" / "male" / "male.mlib"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "debug_anim.glb"

# Test multiple animations
TEST_ANIMATIONS = [
    "male_basic_pick",
    "male_basic_run",
    "male_basic_stand",
]


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


def quat_conjugate(q):
    """Conjugate of quaternion [x, y, z, w] (inverse for unit quaternions)."""
    return [-q[0], -q[1], -q[2], q[3]]


def quat_multiply(q1, q2):
    """Multiply two quaternions [x, y, z, w]."""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return [
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
    ]


def rotate_vector_by_quat(v, q):
    """Rotate vector v by quaternion q."""
    # v' = q * v * q^-1
    vq = [v[0], v[1], v[2], 0]
    q_inv = quat_conjugate(q)
    result = quat_multiply(quat_multiply(q, vq), q_inv)
    return [result[0], result[1], result[2]]


def main():
    print(f"Parsing TMD: {TMD_PATH}")
    tmd_parser = TMDParser()
    model = tmd_parser.parse(TMD_PATH)
    print(f"  Bones: {len(model.bones)}")

    print(f"Parsing MLIB: {MLIB_PATH}")
    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(MLIB_PATH)
    print(f"  MLIB Bones: {len(mlib.bones)}")

    # Get test animations
    motions = []
    for anim_name in TEST_ANIMATIONS:
        motion = mlib.get_motion_by_name(anim_name)
        if motion:
            motions.append(motion)
            print(f"  Animation: {motion.name}, {motion.frame_count} frames, {motion.fps} fps")
        else:
            print(f"  WARNING: Could not find {anim_name}")

    if not motions:
        print("ERROR: No animations found")
        return

    # Build name mappings
    tmd_name_to_idx = {b.name.strip(): i for i, b in enumerate(model.bones)}
    mlib_name_to_idx = {b.name.strip(): i for i, b in enumerate(mlib.bones)}
    mlib_idx_to_name = {i: b.name.strip() for i, b in enumerate(mlib.bones)}

    # Build parent map: tmd_idx -> tmd_parent_idx (using MLIB hierarchy)
    parent_map = {}
    for tmd_idx, tmd_bone in enumerate(model.bones):
        mlib_idx = mlib_name_to_idx.get(tmd_bone.name.strip())
        if mlib_idx is not None and mlib_idx < len(mlib.bones):
            mlib_parent_idx = mlib.bones[mlib_idx].parent_id
            if mlib_parent_idx >= 0 and mlib_parent_idx < len(mlib.bones):
                mlib_parent_name = mlib_idx_to_name[mlib_parent_idx]
                tmd_parent_idx = tmd_name_to_idx.get(mlib_parent_name, -1)
                parent_map[tmd_idx] = tmd_parent_idx
            else:
                parent_map[tmd_idx] = -1
        else:
            parent_map[tmd_idx] = -1

    # Find root bones (those with parent -1)
    root_bones = [i for i in range(len(model.bones)) if parent_map.get(i, -1) == -1]
    print(f"  Root bones: {len(root_bones)}")
    for rb in root_bones:
        print(f"    - {model.bones[rb].name.strip()}")

    # Build children map
    children_map = {i: [] for i in range(len(model.bones))}
    for tmd_idx, parent_idx in parent_map.items():
        if parent_idx >= 0:
            children_map[parent_idx].append(tmd_idx)

    # Get TMD world transforms
    tmd_world_pos = []
    tmd_world_rot = []  # [x, y, z, w]
    for bone in model.bones:
        t = [
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            bone.world_transform.translation.z,
        ]
        R = np.array(bone.world_transform.rotation.data).reshape(3, 3).T
        q = _rotation_matrix_to_quaternion(R)
        tmd_world_pos.append(t)
        tmd_world_rot.append(q)

    # Compute local transforms from world transforms
    # local_pos = parent_world_rot^-1 * (world_pos - parent_world_pos)
    # local_rot = parent_world_rot^-1 * world_rot
    local_pos = []
    local_rot = []
    for tmd_idx in range(len(model.bones)):
        parent_idx = parent_map.get(tmd_idx, -1)
        if parent_idx < 0:
            # Root bone: local = world
            local_pos.append(tmd_world_pos[tmd_idx])
            local_rot.append(tmd_world_rot[tmd_idx])
        else:
            # Child bone: compute relative to parent
            parent_pos = tmd_world_pos[parent_idx]
            parent_rot = tmd_world_rot[parent_idx]
            parent_rot_inv = quat_conjugate(parent_rot)

            # Local position: rotate (world_pos - parent_pos) by parent_rot^-1
            diff = [
                tmd_world_pos[tmd_idx][0] - parent_pos[0],
                tmd_world_pos[tmd_idx][1] - parent_pos[1],
                tmd_world_pos[tmd_idx][2] - parent_pos[2],
            ]
            lp = rotate_vector_by_quat(diff, parent_rot_inv)
            local_pos.append(lp)

            # Local rotation: parent_rot^-1 * world_rot
            lr = quat_multiply(parent_rot_inv, tmd_world_rot[tmd_idx])
            local_rot.append(lr)

    # Create GLTF
    gltf = GLTF2(asset=Asset(version="2.0", generator="debug_anim"))
    buffer = bytearray()

    # Create cube mesh
    h = 0.03 / 2
    vertices = [
        -h, -h, h,   h, -h, h,   h, h, h,  -h, h, h,
        -h, -h, -h, -h, h, -h,   h, h, -h,  h, -h, -h,
    ]
    indices = [
        0, 1, 2, 2, 3, 0,
        4, 5, 6, 6, 7, 4,
        3, 2, 6, 6, 5, 3,
        0, 3, 5, 5, 4, 0,
        1, 7, 6, 6, 2, 1,
        4, 7, 1, 1, 0, 4,
    ]

    v_bin = np.array(vertices, dtype=np.float32).tobytes()
    v_offset = len(buffer)
    buffer.extend(v_bin)

    i_bin = np.array(indices, dtype=np.uint16).tobytes()
    i_offset = len(buffer)
    buffer.extend(i_bin)

    gltf.bufferViews.extend([
        BufferView(buffer=0, byteOffset=v_offset, byteLength=len(v_bin), target=ARRAY_BUFFER),
        BufferView(buffer=0, byteOffset=i_offset, byteLength=len(i_bin), target=ELEMENT_ARRAY_BUFFER),
    ])

    gltf.accessors.extend([
        Accessor(bufferView=0, componentType=FLOAT, count=8, type=VEC3, min=[-h,-h,-h], max=[h,h,h]),
        Accessor(bufferView=1, componentType=UNSIGNED_SHORT, count=len(indices), type=SCALAR),
    ])

    gltf.meshes.append(Mesh(primitives=[Primitive(attributes=Attributes(POSITION=0), indices=1)]))

    # Create bone nodes with LOCAL transforms and parent-child hierarchy
    bone_node_indices = []
    for i, bone in enumerate(model.bones):
        node = Node(
            name=bone.name.strip(),
            translation=local_pos[i],
            rotation=local_rot[i],
            mesh=0,  # cube
            children=[],  # will be filled below
        )
        gltf.nodes.append(node)
        bone_node_indices.append(len(gltf.nodes) - 1)

    # Set up parent-child relationships
    for tmd_idx, children in children_map.items():
        node_idx = bone_node_indices[tmd_idx]
        gltf.nodes[node_idx].children = [bone_node_indices[c] for c in children]

    # Create animations for each motion
    for motion in motions:
        anim_name = motion.name.replace("male_", "")  # Shorten name
        anim = Animation(name=anim_name, channels=[], samplers=[])

        # Time values
        duration = motion.frame_count / motion.fps
        times = [i / motion.fps for i in range(motion.frame_count)]
        time_bin = np.array(times, dtype=np.float32).tobytes()
        time_offset = len(buffer)
        buffer.extend(time_bin)

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

        # Rotation channels per bone
        # MLIB rotations are LOCAL rotations - apply directly
        for tmd_idx in range(len(model.bones)):
            bone_name = model.bones[tmd_idx].name.strip()
            mlib_idx = mlib_name_to_idx.get(bone_name)

            # Build rotation values for all frames
            rot_values = []
            for frame in range(motion.frame_count):
                if mlib_idx is not None and mlib_idx < motion.bone_count:
                    # Get MLIB rotation for this frame (local rotation)
                    mlib_rot = motion.rotations[frame][mlib_idx]
                    # MLIB stores [w,x,y,z], GLTF needs [x,y,z,w]
                    rot_values.extend([mlib_rot.x, mlib_rot.y, mlib_rot.z, mlib_rot.w])
                else:
                    # Use bind pose local rotation
                    rot_values.extend(local_rot[tmd_idx])

            # Add accessor for rotations
            rot_bin = np.array(rot_values, dtype=np.float32).tobytes()
            rot_offset = len(buffer)
            buffer.extend(rot_bin)

            gltf.bufferViews.append(BufferView(buffer=0, byteOffset=rot_offset, byteLength=len(rot_bin)))
            rot_bv = len(gltf.bufferViews) - 1

            gltf.accessors.append(Accessor(
                bufferView=rot_bv,
                componentType=FLOAT,
                count=motion.frame_count,
                type=VEC4,
            ))
            rot_acc = len(gltf.accessors) - 1

            # Add sampler and channel
            anim.samplers.append(AnimationSampler(input=time_acc, output=rot_acc))
            anim.channels.append(AnimationChannel(
                sampler=len(anim.samplers) - 1,
                target=AnimationChannelTarget(node=bone_node_indices[tmd_idx], path="rotation"),
            ))

        gltf.animations.append(anim)

    # Create scene with only root bones (children are linked via hierarchy)
    scene = Scene(nodes=[bone_node_indices[i] for i in root_bones])
    gltf.scenes.append(scene)
    gltf.scene = 0

    # Finalize buffer
    gltf.buffers.append(Buffer(
        byteLength=len(buffer),
        uri="data:application/octet-stream;base64," + _base64_encode(bytes(buffer)),
    ))

    # Save
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    gltf.save(str(OUTPUT_PATH))
    print(f"\nCreated: {OUTPUT_PATH}")

    print("\nGodot checkpoint:")
    print("  - Open debug_anim.glb")
    print(f"  - Animations available: {[m.name.replace('male_', '') for m in motions]}")
    print("  - basic_pick: arm reaching motion")
    print("  - basic_run: running cycle")
    print("  - basic_stand: idle stance")


if __name__ == "__main__":
    main()
