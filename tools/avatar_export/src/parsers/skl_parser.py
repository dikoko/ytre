"""SKL parser — skill scripts (`.skl`, class-tagged archive serialization).

`.skl` files use an MFC-like object archive. The class-name strings that
appear below (`LsCMotion`, `LsCCmdPlay`, …) are literal ASCII type tags
stored verbatim in the shipped files — they are data, and matching on
them is how the format is decodable at all. Two framing details matter
for byte-exact decoding, both established by byte-level analysis of the
shipped fleet:

1. Strings are plain NUL-terminated ASCII — no BYTE/WORD/DWORD length
   prefix exists anywhere in this format.
2. Polymorphic pointers tag by CLASS, not by object: `WORD tag`.
   `tag == 0xFFFF` introduces a new class: `WORD version` (with bit
   0x8000 always set), `WORD name_len`, `name_len` bytes of ASCII class
   name — then the object's own payload follows immediately (no length
   prefix; the reader must understand the payload shape to know where it
   ends). Any other tag has the `0x8000` bit set; its low 15 bits
   0-based-index a per-archive class table (built in first-seen order,
   shared by every polymorphic pointer in the file) — reused classes
   carry no version/name, just the payload. The schema for a class is
   its version WORD from first appearance, masked with `& 0x7FFF`; that
   masked schema applies to every later use of the class in the file.

Field tables below were established by a full, byte-for-byte
(`fully_consumed`) decode of the complete 742-file fleet, seeded from
the four warp fixtures (sk100001-sk100004).

    Top-level animation record (tag "LsCAnimation"; schema 7 in the warp four):
        int32   id
        float32 fps
        int32   frame_count
        int32   component_count
        component_count * (polymorphic component pointer)
        [schema >= 2] int32 region_count; region_count * region:
            schema >= 6: uint16 base_sort, uint16 target_type
            schema <  6: char base_sort, char target_type (legacy
                char-type upgrade applies)
            9 * float32 (3 XYZ triangle points)
        [schema >= 3] int32 path_count; path_count * (polymorphic path
            pointer — a genuinely distinct payload from the never-hit
            "path as a component" case discussed below; exposed as
            Skill.paths, see its own field table further down);
            int32 activating_frame
        [schema >= 4] int32 notifying_frame     (exposed as Skill.notify_frame)
        [schema >= 7] int32 attack_frame (defaults to 0 if schema < 7)
        [schema >= 5] int32 repeat (0/1 bool-as-int)

    Component common prefix (every concrete component type):
        char    byte_type          (component-type enum, redundant with
                                     the class-tag name — informational)
        cstring name                (component/editor label, NOT an asset
                                     ref — e.g. "female_basic_stand", not
                                     "female.MLIB")
        int32   path_id             (-1 == no path)
        track list:
            int32 track_count
            track_count * (
                int32 frame          (shared by every command below it)
                int32 command_count
                command_count * (polymorphic command pointer)
            )
        <type-specific payload follows AFTER the common prefix — i.e.
         after the whole track/command list, not before it>

    Type-specific trailing payload:
        "LsCTMD" (schema 2 in the warp four):
            cstring tmd_filename
            [schema == 1] filename += ".TMD"
        "LsCMotion" (schema 2):
            cstring motion_lib_name
            int32   motion_id
            [schema == 1] char char_type -> legacy upgrade
            [schema >= 2] uint16 char_type
        "LsCSound" (schema 1, no schema switch):
            cstring sound_filename
        "LsCSFX" (not in the warp four; schema 2):
            cstring sfx_filename
            [schema == 1] filename += ".sfd"
            (no other payload — everything else the runtime needs is
            loaded from the referenced .sfd, not stored here)
        "LsCColor" (not in the warp four; schema 2):
            [schema == 1] char character -> legacy upgrade
            [schema >= 2] uint16 character
            (exposed as params["character_type"] — selects which
            character's material the runtime tints; component name is
            the editor label, there is no filename for this kind)
        "LsCCameraCom" / "LsCSwordTrace" (not in the warp four): no
            payload at all beyond the common prefix (verified across the
            fleet — every runtime field is command-driven, not stored).
        "LsCPath" as a *component*: never legitimately occurs — "path"
            only maps a class name to a Component.kind for completeness.
            Confirmed unreachable across the full 742-file fleet (zero
            occurrences as a component tag); still raises loudly rather
            than silently mis-decoding if it ever did.

    Path record, as an *animation-level* polymorphic pointer (tag
    "LsCPath"; schema 3 in the fleet; key arrays fixed 10-long):
        int32   num_input_points
        num_input_points * 3 * float32   (raw bspline control points, XYZ)
        [schema == 1] char base_character (legacy upgrade); char
            base_bone; char target_character (legacy upgrade); char
            target_bone
        [schema in (2, 3)] uint16 base_character; char base_bone; uint16
            target_character; char target_bone
        [schema < 3] bone id 9 was the old "Local"; upgraded to 11 —
            same rule as the base command's bone field
        10 * quaternion  (raw block — x, y, z, w; 160B)
        10 * vector3 (raw block — X, Y, Z; 120B)
        10 * float32 (raw block, spline parameters; 40B)
    Exposed per-path as one dict in Skill.paths — cataloged, not
    resolved into playback (path playback is deferred; the catalog only
    needs the data to exist and be inspectable). 50/742 fleet files
    carry at least one path.

    Command common prefix (every concrete command type):
        char cmd_type    (command-type enum, redundant with the class-tag
                           name, like the component's byte_type)
        <type-specific payload>
    Per-command payload:
        "LsCCmdPlay" / "LsCCmdStop": none.
        "LsCCmdSetSFXRealTime": float32 real_time.
        "LsCCmdBase" (schema 6 in the warp four; full switch below):
            schema >= 5: uint16 base_character
            schema <= 4: char base_character -> legacy upgrade
            schema == 1: no more fields (all defaulted)
            schema == 2: char base_bone
            schema == 3: char base_bone; int32 inherit_pos; int32
                inherit_rot (two SEPARATE stored ints, not one shared
                value); float32 offset_y (x/z default 0, no rotation
                fields)
            schema in (4, 5, 6): char base_bone; int32 inherit_pos;
                int32 inherit_rot; 3*float32 offset_xyz; 3*float32 rot_xyz
        "LsCCmdPath":
            schema == 1: float32 play_time (path_id defaults to -1)
            schema == 2: int32 path_id; float32 play_time
        "LsCCmdColor": int32 total_frame; 2 * 16 float32
            (D3D-style material blocks self/target:
            Ambient/Diffuse/Specular/Emissive, each r,g,b,a)
        "LsCCmdCameraCom": int32 type; float32 offset; float32 speed.
        "LsCCmdSwordTrace": float32 factor.

Ground-truth note: a full byte-for-byte decode of all four warp `.skl`
files shows `frame_count` is 60 in ALL FOUR (arrive and depart alike)
and `notifying_frame` is 29 in all four — an ANIMATION-level field (the
end-of-skill notify hook), not a per-command one; every track in every
one of the four files has `frame == 0`. Nothing in the `.skl` bytes
distinguishes a 30-frame "effective" duration for the two arrive skills
from the two depart skills — the referenced *TMD asset's own* frame
count is a fact about a different file, unreachable from `.skl` bytes
alone. `total_frames` is `frame_count` verbatim (60 for all four warp
skills) and `notify_frame` is `notifying_frame` verbatim (29 for all
four); `Command.frame` is always its owning track's frame.
"""
import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Command:
    frame: int
    kind: str
    params: dict


@dataclass
class Component:
    kind: str
    name: str
    params: dict


@dataclass
class Track:
    component: Component
    commands: list[Command] = field(default_factory=list)


@dataclass
class Skill:
    skill_id: int
    fps: float
    total_frames: int
    notify_frame: int
    tracks: list[Track] = field(default_factory=list)
    paths: list[dict] = field(default_factory=list)


CLASS_KINDS = {
    "LsCTMD": "tmd", "LsCMotion": "motion", "LsCSFX": "sfx",
    "LsCSound": "sound", "LsCColor": "color", "LsCCameraCom": "camera",
    "LsCPath": "path", "LsCSwordTrace": "sword_trace",
}

COMMAND_KINDS = {
    "LsCCmdPlay": "play", "LsCCmdBase": "base", "LsCCmdStop": "stop",
    "LsCCmdColor": "color", "LsCCmdSetSFXRealTime": "sfx_realtime",
    "LsCCmdCameraCom": "camera", "LsCCmdPath": "path",
    "LsCCmdSwordTrace": "sword_trace",
}

# Schema bit — OR'd into a class's stored version WORD; mask it off to
# get the schema number the payload layout switches on.
_SCHEMA_BIT = 0x8000
_NEW_CLASS_TAG = 0xFFFF

# Fixed key-array length in path records, serialized as raw blocks with
# no per-element framing.
_PATH_KEY_COUNT = 10


def _upgrade_char_type(byte_old_type: int) -> int:
    """Upgrade the legacy character-sort/type byte (old-schema files) to
    the newer packed unsigned short. Only old files use this; none of
    the warp four do."""
    if byte_old_type < 0:
        byte_old_type += 256
    new_type = ((byte_old_type & 0xF0) << 4) & 0xFFFF
    new_type |= (byte_old_type & 0x04) >> 2
    if byte_old_type & 0x02:
        new_type |= 0x0008  # same-team flag
    if byte_old_type & 0x01:
        new_type |= 0x0002 | 0x0004 | 0x0010  # monster | other-team | active-object
    return new_type


class _Archive:
    """Minimal reader for the archive framing: fixed-width
    primitives, NUL-terminated strings, and class-tagged polymorphic
    pointers (see the module docstring for the full framing writeup)."""

    def __init__(self, data: bytes, path: str | None = None):
        self.data = data
        self.pos = 0
        self.path = path  # source filename, for ValueError messages only
        self.classes: list[tuple[str, int]] = []  # (name, masked_schema), first-seen order

    def fail(self, message: str, at: int | None = None) -> ValueError:
        """Build (not raise — callers `raise ar.fail(...)`) a ValueError
        carrying the source file and byte offset, so unknown class tags /
        trailing bytes fail loudly and locatably."""
        offset = self.pos if at is None else at
        label = self.path if self.path is not None else "<bytes>"
        return ValueError(f"{label}: offset {offset}: {message}")

    def u8(self) -> int:
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def f32(self) -> float:
        v = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return v

    def f32_array(self, count: int) -> tuple[float, ...]:
        """Read `count` back-to-back float32s as one raw block — matches
        the format's raw bulk blocks (path key arrays), which carry no
        per-element framing of their own."""
        v = struct.unpack_from(f"<{count}f", self.data, self.pos)
        self.pos += 4 * count
        return v

    def cstring(self) -> str:
        """NUL-terminated ASCII string, no length prefix."""
        start = self.pos
        end = self.data.index(0, start)
        s = self.data[start:end].decode("cp949", errors="replace")
        self.pos = end + 1
        return s

    def read_class(self) -> tuple[str, int]:
        """Consume a polymorphic-pointer class tag; return (class_name,
        masked_schema). New classes register into the shared per-archive
        table; back-references (tag & 0x8000) index into it directly
        (0-based)."""
        tag = self.u16()
        if tag == _NEW_CLASS_TAG:
            raw_version = self.u16()
            name_len = self.u16()
            name = self.data[self.pos:self.pos + name_len].decode("ascii")
            self.pos += name_len
            schema = raw_version & ~_SCHEMA_BIT
            self.classes.append((name, schema))
            return name, schema
        idx = tag & ~_SCHEMA_BIT
        return self.classes[idx]


def _parse_cmd_base(ar: _Archive, schema: int) -> dict:
    if schema >= 5:
        base_character = ar.u16()
    else:
        base_character = _upgrade_char_type(ar.u8())

    if schema == 1:
        return dict(
            base_character=base_character, base_bone=11,
            inherit_pos=False, inherit_rot=False,
            offset=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0),
        )
    if schema == 2:
        base_bone = ar.u8()
        return dict(
            base_character=base_character, base_bone=base_bone,
            inherit_pos=False, inherit_rot=False,
            offset=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0),
        )
    if schema == 3:
        base_bone = ar.u8()
        # Schema 3 stores TWO separate inherit ints here (verified
        # byte-exactly against shipped files) — NOT one shared value
        # copied to both. 1+4+4+4 = 13 bytes.
        inherit_pos = bool(ar.i32())
        inherit_rot = bool(ar.i32())
        offset_y = ar.f32()
        return dict(
            base_character=base_character, base_bone=base_bone,
            inherit_pos=inherit_pos, inherit_rot=inherit_rot,
            offset=(0.0, offset_y, 0.0), rot=(0.0, 0.0, 0.0),
        )
    if schema in (4, 5, 6):
        base_bone = ar.u8()
        inherit_pos = bool(ar.i32())
        inherit_rot = bool(ar.i32())
        offset = (ar.f32(), ar.f32(), ar.f32())
        rot = (ar.f32(), ar.f32(), ar.f32())
        # pre-schema-6 files store the Local bone as 9; newer use 11
        if schema < 6 and base_bone == 9:
            base_bone = 11
        return dict(
            base_character=base_character, base_bone=base_bone,
            inherit_pos=inherit_pos, inherit_rot=inherit_rot,
            offset=offset, rot=rot,
        )
    raise NotImplementedError(f"LsCCmdBase schema {schema} not supported")


def _parse_cmd_path(ar: _Archive, schema: int) -> dict:
    if schema == 1:
        return dict(path_id=-1, play_time=ar.f32())
    if schema == 2:
        path_id = ar.i32()
        return dict(path_id=path_id, play_time=ar.f32())
    raise NotImplementedError(f"LsCCmdPath schema {schema} not supported")


def _parse_cmd_color(ar: _Archive) -> dict:
    total_frame = ar.i32()

    def material():
        return dict(
            ambient=(ar.f32(), ar.f32(), ar.f32(), ar.f32()),
            diffuse=(ar.f32(), ar.f32(), ar.f32(), ar.f32()),
            specular=(ar.f32(), ar.f32(), ar.f32(), ar.f32()),
            emissive=(ar.f32(), ar.f32(), ar.f32(), ar.f32()),
        )

    return dict(total_frame=total_frame, self=material(), target=material())


def _parse_command(ar: _Archive, frame: int) -> Command:
    start = ar.pos
    cname, cschema = ar.read_class()
    kind = COMMAND_KINDS.get(cname)
    if kind is None:
        raise ar.fail(f"unknown command class {cname!r}", start)
    ar.u8()  # command-type byte — redundant with the class-tag name, discarded

    if kind in ("play", "stop"):
        params: dict = {}
    elif kind == "base":
        params = _parse_cmd_base(ar, cschema)
    elif kind == "sfx_realtime":
        params = {"real_time": ar.f32()}
    elif kind == "color":
        params = _parse_cmd_color(ar)
    elif kind == "camera":
        params = {"type": ar.i32(), "offset": ar.f32(), "speed": ar.f32()}
    elif kind == "path":
        params = _parse_cmd_path(ar, cschema)
    elif kind == "sword_trace":
        params = {"factor": ar.f32()}
    else:  # pragma: no cover - COMMAND_KINDS is exhaustive over kind literals
        raise NotImplementedError(f"command kind {kind!r} is not supported")

    return Command(frame=frame, kind=kind, params=params)


def _parse_track(ar: _Archive) -> Track:
    start = ar.pos
    cname, cschema = ar.read_class()
    kind = CLASS_KINDS.get(cname)
    if kind is None:
        raise ar.fail(f"unknown component class {cname!r}", start)

    # Component common prefix (every concrete component type reads it).
    ar.u8()  # component-type byte — redundant with the class-tag name, discarded
    editor_name = ar.cstring()  # component label, NOT an asset ref
    ar.i32()  # path id — indexes the animation-level path list; unused by warp four

    track_count = ar.i32()
    commands: list[Command] = []
    for _ in range(track_count):
        frame = ar.i32()
        cmd_count = ar.i32()
        for _ in range(cmd_count):
            commands.append(_parse_command(ar, frame))

    # Component-specific trailing payload (stored AFTER the common
    # prefix — i.e. after the whole track list).
    if kind == "tmd":
        name = ar.cstring()
        if cschema == 1:
            name += ".TMD"
        params = {}
    elif kind == "motion":
        lib_name = ar.cstring()
        motion_id = ar.i32()
        char_type = _upgrade_char_type(ar.u8()) if cschema == 1 else ar.u16()
        name = lib_name
        params = {"motion_id": motion_id, "character_type": char_type}
    elif kind == "sound":
        name = ar.cstring()
        params = {}
    elif kind == "sfx":
        # The sfx component stores only the filename — everything else
        # the runtime needs lives in the referenced .sfd, not in this
        # file, so there is no further payload to type.
        name = ar.cstring()
        if cschema == 1:
            name += ".sfd"
        params = {}
    elif kind == "color":
        if cschema == 1:
            character = _upgrade_char_type(ar.u8())
        elif cschema >= 2:
            character = ar.u16()
        else:
            raise ar.fail(f"LsCColor schema {cschema} not supported")
        # No filename for this kind — the character field picks which
        # character's material the runtime tints; editor_name is the
        # closest thing to a display name.
        name = editor_name
        params = {"character_type": character}
    elif kind in ("camera", "sword_trace"):
        # Camera / sword-trace components add nothing beyond the common
        # prefix already consumed above (verified across the fleet — see
        # module docstring).
        name = editor_name
        params = {}
    else:  # "path" — see the module docstring: not reachable in shipped data.
        raise ar.fail(f"component kind {kind!r} (class {cname!r}) is not supported", start)

    return Track(component=Component(kind=kind, name=name, params=params), commands=commands)


def _skip_regions(ar: _Archive, schema: int, count: int) -> None:
    for _ in range(count):
        if schema >= 6:
            ar.u16()
            ar.u16()
        else:
            _upgrade_char_type(ar.u8())
            _upgrade_char_type(ar.u8())
        for _ in range(9):  # 3 triangle points * XYZ
            ar.f32()


def _parse_path(ar: _Archive) -> dict:
    """Path record as an *animation-level* polymorphic pointer — a
    genuinely different call site from the unreachable "path as a
    component" case in _parse_track. See the module docstring's field
    table."""
    start = ar.pos
    cname, schema = ar.read_class()
    if cname != "LsCPath":
        raise ar.fail(f"expected LsCPath class tag, got {cname!r}", start)

    num_input_points = ar.i32()
    input_points = [(ar.f32(), ar.f32(), ar.f32()) for _ in range(num_input_points)]

    if schema == 1:
        base_character = _upgrade_char_type(ar.u8())
        base_bone = ar.u8()
        target_character = _upgrade_char_type(ar.u8())
        target_bone = ar.u8()
    elif schema in (2, 3):
        base_character = ar.u16()
        base_bone = ar.u8()
        target_character = ar.u16()
        target_bone = ar.u8()
    else:
        raise ar.fail(f"LsCPath schema {schema} not supported", start)

    # Old files store the Local bone as 9, newer as 11 — same bone-id
    # upgrade rule as the base command, applied independently per endpoint.
    if schema < 3:
        if base_bone == 9:
            base_bone = 11
        if target_bone == 9:
            target_bone = 11

    # Three raw blocks, fixed 10-long arrays with no per-element
    # framing of their own.
    quat_keys = [ar.f32_array(4) for _ in range(_PATH_KEY_COUNT)]  # (x, y, z, w) each
    vec_keys = [ar.f32_array(3) for _ in range(_PATH_KEY_COUNT)]  # (x, y, z) each
    parameters = list(ar.f32_array(_PATH_KEY_COUNT))

    return dict(
        input_points=input_points,
        base_character=base_character, base_bone=base_bone,
        target_character=target_character, target_bone=target_bone,
        quat_keys=quat_keys, vec_keys=vec_keys, parameters=parameters,
    )


def parse_skl(path: Path | str) -> Skill:
    path = Path(path)
    data = path.read_bytes()
    ar = _Archive(data, path=str(path))

    start = ar.pos
    class_name, schema = ar.read_class()
    if class_name != "LsCAnimation":
        raise ar.fail(f"expected LsCAnimation at file root, got {class_name!r}", start)

    # Top-level animation record — see the module docstring for the full
    # field table (region/path/frame tail fields are schema-gated and
    # consumed for correct byte alignment, but not part of the Skill
    # dataclass's public surface).
    skill_id = ar.i32()
    fps = ar.f32()
    total_frames = ar.i32()
    # Pre-schema-4 files store no notify frame; the default is
    # frame_count - 1, overwritten below if the file's schema stores one.
    notify_frame = total_frames - 1

    component_count = ar.i32()
    tracks = [_parse_track(ar) for _ in range(component_count)]

    if schema >= 2:
        region_count = ar.i32()
        _skip_regions(ar, schema, region_count)
    paths: list[dict] = []
    if schema >= 3:
        path_count = ar.i32()
        paths = [_parse_path(ar) for _ in range(path_count)]
        ar.i32()  # activating_frame
    if schema >= 4:
        notify_frame = ar.i32()  # notifying_frame
    if schema >= 7:
        ar.i32()  # attack_frame
    if schema >= 5:
        ar.i32()  # repeat flag (int 0/1)

    if ar.pos != len(data):
        raise ar.fail(f"{len(data) - ar.pos} trailing byte(s) after full parse")

    return Skill(
        skill_id=skill_id, fps=fps, total_frames=total_frames,
        notify_frame=notify_frame, tracks=tracks, paths=paths,
    )
