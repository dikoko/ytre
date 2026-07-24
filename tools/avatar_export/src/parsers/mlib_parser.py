"""
MLIB (Motion Library) Parser

Parses Yogurting MLIB animation files containing bone hierarchy and motion data.

MLIB Format (MLIB_HEADER_EX = 0x2385adce):
1. Header (4 bytes): Magic number
2. Bone data
3. Motion count (4 bytes)
4. Motion data for each motion
5. Ground vector (12 bytes)
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO


# Constants
MLIB_HEADER = 0x2385ADBF
MLIB_HEADER_EX = 0x2385ADCE
MAX_MOTION_NAME = 40
M_INFO_SU = 50

# Motion types
MOTION_TYPE_BASIC = 0      # rotations only
MOTION_TYPE_EX = 1         # + per-bone translations
MOTION_TYPE_EX2 = 2        # + per-bone scales
MOTION_TYPE_EX3 = 3        # + scale axes
MOTION_TYPE_KEY = 4        # keyframe tracks


@dataclass
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class Quaternion:
    """Quaternion stored as [w, x, y, z] in MLIB files."""
    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class MLIBBone:
    """Bone definition from MLIB."""
    name: str = ""
    parent_id: int = -1
    position: Vector3 = field(default_factory=Vector3)


@dataclass
class MLIBMotion:
    """Animation motion data."""
    motion_id: int = 0
    motion_type: int = 0
    name: str = ""
    frame_count: int = 0
    bone_count: int = 0
    fps: int = 30
    option: int = 0

    # Per-frame root positions
    root_positions: list[Vector3] = field(default_factory=list)

    # Per-frame, per-bone rotations: rotations[frame][bone]
    rotations: list[list[Quaternion]] = field(default_factory=list)

    # Per-frame, per-bone translations (extended motion types)
    translations: list[list[Vector3]] = field(default_factory=list)

    # Per-frame, per-bone scales (extended types 2/3 and KEY motions).
    # LIVE only when option bit 3 (value 8) is set; keys with the
    # gate off are dead data the engine never samples.
    scales: list[list[Vector3]] = field(default_factory=list)

    # Per-frame, per-bone scale-axis quaternions (KEY motions / Ex3).
    # Engine local matrix is SA^-1 * S * SA * R.
    scale_axes: list[list[Quaternion]] = field(default_factory=list)

    # Origin and orientation
    origin: Vector3 = field(default_factory=Vector3)
    orient: Quaternion = field(default_factory=Quaternion)


@dataclass
class MLIBFile:
    """Parsed MLIB file."""
    bones: list[MLIBBone] = field(default_factory=list)
    motions: list[MLIBMotion] = field(default_factory=list)
    ground_vector: Vector3 = field(default_factory=Vector3)

    def get_motion_by_id(self, motion_id: int) -> MLIBMotion | None:
        for motion in self.motions:
            if motion.motion_id == motion_id:
                return motion
        return None

    def get_motion_by_name(self, name: str) -> MLIBMotion | None:
        for motion in self.motions:
            if motion.name == name:
                return motion
        return None


class MLIBParser:
    """Parser for MLIB animation files."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def parse(self, path: str | Path) -> MLIBFile:
        """Parse an MLIB file."""
        path = Path(path)

        with open(path, 'rb') as f:
            return self._parse_file(f)

    def _parse_file(self, f: BinaryIO) -> MLIBFile:
        """Parse MLIB from file handle."""
        header = struct.unpack('<I', f.read(4))[0]

        if header == MLIB_HEADER_EX:
            return self._parse_ex(f)
        elif header == MLIB_HEADER:
            return self._parse_old(f)
        else:
            raise ValueError(f"Unknown MLIB header: 0x{header:08x}")

    def _parse_ex(self, f: BinaryIO) -> MLIBFile:
        """Parse extended MLIB format."""
        result = MLIBFile()

        result.bones = self._parse_bones(f)
        motion_count = struct.unpack('<I', f.read(4))[0]

        for i in range(motion_count):
            motion_id = struct.unpack('<I', f.read(4))[0]
            motion_type = struct.unpack('<I', f.read(4))[0]

            motion = self._parse_motion(f, motion_type, len(result.bones))
            motion.motion_id = motion_id
            motion.motion_type = motion_type

            result.motions.append(motion)

        gv = struct.unpack('<3f', f.read(12))
        result.ground_vector = Vector3(gv[0], gv[1], gv[2])

        return result

    def _parse_old(self, f: BinaryIO) -> MLIBFile:
        """Parse old MLIB format (no motion IDs)."""
        result = MLIBFile()

        result.bones = self._parse_bones(f)
        motion_count = struct.unpack('<I', f.read(4))[0]

        for i in range(motion_count):
            motion_type = struct.unpack('<I', f.read(4))[0]

            motion = self._parse_motion(f, motion_type, len(result.bones))
            motion.motion_id = i
            motion.motion_type = motion_type

            result.motions.append(motion)

        gv = struct.unpack('<3f', f.read(12))
        result.ground_vector = Vector3(gv[0], gv[1], gv[2])

        return result

    def _parse_bones(self, f: BinaryIO) -> list[MLIBBone]:
        """Parse one bone record."""
        bones = []

        bone_count = struct.unpack('<I', f.read(4))[0]
        parent_ids = struct.unpack(f'<{bone_count}i', f.read(4 * bone_count))

        positions = []
        for i in range(bone_count):
            pos = struct.unpack('<3f', f.read(12))
            positions.append(Vector3(pos[0], pos[1], pos[2]))

        limb_count = struct.unpack('<I', f.read(4))[0]
        if limb_count > 0:
            f.read(16 * limb_count)

        names = []
        for i in range(bone_count):
            name_bytes = f.read(MAX_MOTION_NAME)
            name = name_bytes.split(b'\x00')[0].decode('utf-8', errors='replace')
            names.append(name)

        for i in range(bone_count):
            bone = MLIBBone(
                name=names[i],
                parent_id=parent_ids[i],
                position=positions[i],
            )
            bones.append(bone)

        return bones

    def _parse_motion(self, f: BinaryIO, motion_type: int, bone_count: int) -> MLIBMotion:
        """Parse one motion record based on motion type."""
        if motion_type == MOTION_TYPE_KEY:
            return self._parse_key_motion(f)
        else:
            return self._parse_basic_motion(f, motion_type)

    def _parse_basic_motion(self, f: BinaryIO, motion_type: int) -> MLIBMotion:
        """Parse a basic/extended motion record."""
        motion = MLIBMotion()

        motion.frame_count = struct.unpack('<I', f.read(4))[0]
        motion.bone_count = struct.unpack('<I', f.read(4))[0]

        name_bytes = f.read(MAX_MOTION_NAME)
        motion.name = name_bytes.split(b'\x00')[0].decode('utf-8', errors='replace')

        motion.option = struct.unpack('<I', f.read(4))[0]

        # Tags and weights
        f.read(motion.frame_count)
        f.read(4 * motion.bone_count)

        # Root positions
        for i in range(motion.frame_count):
            pos = struct.unpack('<3f', f.read(12))
            motion.root_positions.append(Vector3(pos[0], pos[1], pos[2]))

        # Rotations: [w, x, y, z]
        for frame in range(motion.frame_count):
            frame_rotations = []
            for bone in range(motion.bone_count):
                q = struct.unpack('<4f', f.read(16))
                frame_rotations.append(Quaternion(q[0], q[1], q[2], q[3]))
            motion.rotations.append(frame_rotations)

        motion.fps = struct.unpack('<I', f.read(4))[0]

        # Info
        f.read(2 * M_INFO_SU)

        # Limb data
        limb_count = struct.unpack('<I', f.read(4))[0]
        if limb_count > 0:
            f.read(16 * motion.frame_count)

        # Origin vector
        origin = struct.unpack('<3f', f.read(12))
        motion.origin = Vector3(origin[0], origin[1], origin[2])

        # Orient quaternion
        orient = struct.unpack('<4f', f.read(16))
        motion.orient = Quaternion(orient[0], orient[1], orient[2], orient[3])

        # Callback info
        cbinfo = struct.unpack('<B', f.read(1))[0]
        if cbinfo:
            f.read(8 * motion.frame_count)

        # Handle extended motion types
        if motion_type == MOTION_TYPE_EX:
            self._parse_motion_ex(f, motion)
        elif motion_type == MOTION_TYPE_EX2:
            self._parse_motion_ex(f, motion)
            self._parse_motion_scales(f, motion)
        elif motion_type == MOTION_TYPE_EX3:
            self._parse_motion_ex(f, motion)
            self._parse_motion_scales(f, motion)
            self._parse_motion_scale_axes(f, motion)

        return motion

    def _parse_key_motion(self, f: BinaryIO) -> MLIBMotion:
        """Parse a keyframe-track motion record."""
        motion = MLIBMotion()

        motion.frame_count = struct.unpack('<I', f.read(4))[0]
        motion.bone_count = struct.unpack('<I', f.read(4))[0]

        name_bytes = f.read(MAX_MOTION_NAME)
        motion.name = name_bytes.split(b'\x00')[0].decode('utf-8', errors='replace')

        motion.option = struct.unpack('<I', f.read(4))[0]

        f.read(motion.frame_count)
        f.read(4 * motion.bone_count)

        for i in range(motion.frame_count):
            pos = struct.unpack('<3f', f.read(12))
            motion.root_positions.append(Vector3(pos[0], pos[1], pos[2]))

        # Keyframe data per bone
        rotation_keys: list[list[tuple[int, Quaternion]]] = []
        translation_keys: list[list[tuple[int, Vector3]]] = []
        scale_keys: list[list[tuple[int, Vector3]]] = []
        scale_axis_keys: list[list[tuple[int, Quaternion]]] = []

        for bone_idx in range(motion.bone_count):
            # Rotation keys
            rot_key_count = struct.unpack('<I', f.read(4))[0]
            bone_rot_keys = []
            if rot_key_count > 0:
                key_indices = struct.unpack(f'<{rot_key_count}i', f.read(4 * rot_key_count))
                for i in range(rot_key_count):
                    q = struct.unpack('<4f', f.read(16))
                    bone_rot_keys.append((key_indices[i], Quaternion(q[0], q[1], q[2], q[3])))
            rotation_keys.append(bone_rot_keys)

            # Translation keys
            trans_key_count = struct.unpack('<I', f.read(4))[0]
            bone_trans_keys = []
            if trans_key_count > 0:
                key_indices = struct.unpack(f'<{trans_key_count}i', f.read(4 * trans_key_count))
                for i in range(trans_key_count):
                    v = struct.unpack('<3f', f.read(12))
                    bone_trans_keys.append((key_indices[i], Vector3(v[0], v[1], v[2])))
            translation_keys.append(bone_trans_keys)

            # Scale keys
            scale_key_count = struct.unpack('<I', f.read(4))[0]
            bone_scale_keys = []
            if scale_key_count > 0:
                key_indices = struct.unpack(f'<{scale_key_count}i', f.read(4 * scale_key_count))
                for i in range(scale_key_count):
                    v = struct.unpack('<3f', f.read(12))
                    bone_scale_keys.append((key_indices[i], Vector3(v[0], v[1], v[2])))
            scale_keys.append(bone_scale_keys)

            # Scale axis keys (w-first quats, like rotation keys)
            scale_axis_key_count = struct.unpack('<I', f.read(4))[0]
            bone_sa_keys = []
            if scale_axis_key_count > 0:
                key_indices = struct.unpack(f'<{scale_axis_key_count}i', f.read(4 * scale_axis_key_count))
                for i in range(scale_axis_key_count):
                    q = struct.unpack('<4f', f.read(16))
                    bone_sa_keys.append((key_indices[i], Quaternion(q[0], q[1], q[2], q[3])))
            scale_axis_keys.append(bone_sa_keys)

        motion.rotations = self._expand_rotation_keys(rotation_keys, motion.frame_count, motion.bone_count)
        # The engine samples translation keys for EVERY bone i>=1 in
        # keyframe motions — the skeleton bind offsets are NOT used at
        # runtime. No keys / before first key -> (0,0,0).
        motion.translations = self._expand_vector_keys(
            translation_keys, motion.frame_count, motion.bone_count,
            Vector3(0.0, 0.0, 0.0))
        motion.scales = self._expand_vector_keys(
            scale_keys, motion.frame_count, motion.bone_count,
            Vector3(1.0, 1.0, 1.0))
        motion.scale_axes = self._expand_rotation_keys(
            scale_axis_keys, motion.frame_count, motion.bone_count)

        motion.fps = struct.unpack('<I', f.read(4))[0]
        f.read(2 * M_INFO_SU)

        limb_count = struct.unpack('<I', f.read(4))[0]
        if limb_count > 0:
            f.read(16 * motion.frame_count)

        origin = struct.unpack('<3f', f.read(12))
        motion.origin = Vector3(origin[0], origin[1], origin[2])

        orient = struct.unpack('<4f', f.read(16))
        motion.orient = Quaternion(orient[0], orient[1], orient[2], orient[3])

        cbinfo = struct.unpack('<B', f.read(1))[0]
        if cbinfo:
            f.read(8 * motion.frame_count)

        return motion

    def _expand_vector_keys(
        self,
        vector_keys: list[list[tuple[int, Vector3]]],
        frame_count: int,
        bone_count: int,
        default: Vector3,
    ) -> list[list[Vector3]]:
        """Expand keyframed vectors per frame with engine sampling
        (nearest-previous key + lerp; before first key -> default;
        past last key -> last value)."""
        result = []
        for frame in range(frame_count):
            frame_vals = []
            for bone_idx in range(bone_count):
                keys = vector_keys[bone_idx]
                if not keys or frame < keys[0][0]:
                    frame_vals.append(default)
                    continue
                prev = keys[0]
                nxt = None
                for kf, v in keys:
                    if kf <= frame:
                        prev = (kf, v)
                    else:
                        nxt = (kf, v)
                        break
                if nxt is None or prev[0] == nxt[0]:
                    frame_vals.append(prev[1])
                else:
                    t = (frame - prev[0]) / (nxt[0] - prev[0])
                    p, n = prev[1], nxt[1]
                    frame_vals.append(Vector3(
                        p.x + t * (n.x - p.x),
                        p.y + t * (n.y - p.y),
                        p.z + t * (n.z - p.z),
                    ))
            result.append(frame_vals)
        return result

    def _expand_rotation_keys(
        self,
        rotation_keys: list[list[tuple[int, Quaternion]]],
        frame_count: int,
        bone_count: int
    ) -> list[list[Quaternion]]:
        """Expand keyframe rotations to per-frame data."""
        result = []
        for frame in range(frame_count):
            frame_rotations = []
            for bone_idx in range(bone_count):
                keys = rotation_keys[bone_idx]
                if not keys:
                    frame_rotations.append(Quaternion(1.0, 0.0, 0.0, 0.0))
                elif len(keys) == 1:
                    frame_rotations.append(keys[0][1])
                else:
                    q = self._interpolate_rotation_key(keys, frame)
                    frame_rotations.append(q)
            result.append(frame_rotations)
        return result

    def _interpolate_rotation_key(
        self,
        keys: list[tuple[int, Quaternion]],
        frame: int
    ) -> Quaternion:
        """Interpolate rotation from keyframes."""
        prev_key = keys[0]
        next_key = keys[-1]

        for i, (key_frame, q) in enumerate(keys):
            if key_frame <= frame:
                prev_key = (key_frame, q)
            if key_frame >= frame:
                next_key = (key_frame, q)
                break

        if prev_key[0] == next_key[0]:
            return prev_key[1]

        t = (frame - prev_key[0]) / (next_key[0] - prev_key[0])
        p = prev_key[1]
        n = next_key[1]

        # Engine-exact: hemisphere correction + shortest-path slerp,
        # matching the original client. Component lerp WITHOUT
        # normalization diverges badly on sparse keys (e.g. cn0062's
        # @Netbag scale-axis keys, 45 degrees apart -> |q| dips to 0.925).
        import math
        dot = p.w * n.w + p.x * n.x + p.y * n.y + p.z * n.z
        if dot < 0:
            n = Quaternion(w=-n.w, x=-n.x, y=-n.y, z=-n.z)
            dot = -dot
        if dot > 1.0 - 1e-6:
            # near-parallel: nlerp
            q = [p.w + t * (n.w - p.w), p.x + t * (n.x - p.x),
                 p.y + t * (n.y - p.y), p.z + t * (n.z - p.z)]
            norm = math.sqrt(sum(c * c for c in q)) or 1.0
            return Quaternion(w=q[0] / norm, x=q[1] / norm,
                              y=q[2] / norm, z=q[3] / norm)
        theta = math.acos(max(-1.0, min(1.0, dot)))
        sinom = math.sin(theta)
        wa = math.sin((1 - t) * theta) / sinom
        wb = math.sin(t * theta) / sinom
        return Quaternion(
            w=wa * p.w + wb * n.w,
            x=wa * p.x + wb * n.x,
            y=wa * p.y + wb * n.y,
            z=wa * p.z + wb * n.z,
        )

    def _parse_motion_ex(self, f: BinaryIO, motion: MLIBMotion) -> None:
        """Parse extended motion data (per-bone translations)."""
        for frame in range(motion.frame_count):
            frame_translations = []
            for bone in range(motion.bone_count):
                pos = struct.unpack('<3f', f.read(12))
                frame_translations.append(Vector3(pos[0], pos[1], pos[2]))
            motion.translations.append(frame_translations)

    def _parse_motion_scales(self, f: BinaryIO, motion: MLIBMotion) -> None:
        """Parse extended motion data (per-bone scales)."""
        for frame in range(motion.frame_count):
            frame_scales = []
            for bone in range(motion.bone_count):
                scale = struct.unpack('<3f', f.read(12))
                frame_scales.append(Vector3(scale[0], scale[1], scale[2]))
            motion.scales.append(frame_scales)

    def _parse_motion_scale_axes(self, f: BinaryIO, motion: MLIBMotion) -> None:
        """Parse extended motion data (scale axes as quaternions)."""
        f.read(16 * motion.frame_count * motion.bone_count)
