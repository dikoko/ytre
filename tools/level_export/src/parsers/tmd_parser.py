"""
TMD (Tokenized Model Definition) Parser

Parses Yogurting's 3D model format. TMD is a chunk-based binary format
containing meshes, materials, bones, and animations.

Based on Gate3D3 library from the original client.
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO


# TMD Version constants
TMD_VERSION_20021011 = 20021011  # Initial version
TMD_VERSION_20030402 = 20030402  # Soft skinning
TMD_VERSION_20031110 = 20031110  # Vertex animation
TMD_VERSION_20031118 = 20031118  # User define chunks
TMD_VERSION_20031214 = 20031214  # Self-illumination
TMD_VERSION_20031217 = 20031217  # Material self-illum
TMD_VERSION_20031218 = 20031218  # Bone face
TMD_VERSION_20040202 = 20040202  # Skinned object fix
TMD_VERSION_20040304 = 20040304  # Stretch rotate
TMD_VERSION_20040715 = 20040715  # DX shader materials
TMD_VERSION_20041005 = 20041005  # World coordinate skinning
TMD_VERSION_20041124 = 20041124  # Parent by StartID
TMD_VERSION = TMD_VERSION_20041124

# Chunk IDs
TMDCHUNK_MAIN = 0x00000005
TMDCHUNK_GLOBALBLOCK = 0x00001000
TMDCHUNK_ALLFRAME = 0x00001001
TMDCHUNK_FRAMESPEED = 0x00001002
TMDCHUNK_TICKPERFRAME = 0x00001003
TMDCHUNK_GLOBALAMBIENT = 0x00001004

TMDCHUNK_OBJECTBLOCK = 0x00002000
TMDCHUNK_MATERIALTRACK = 0x00002100
TMDCHUNK_MATERIAL = 0x00002101
TMDCHUNK_FXMATERIAL = 0x00002102

TMDCHUNK_OBJECTTRACK = 0x00003000
TMDCHUNK_STARTOBJECTID = 0x00003001
TMDCHUNK_OBJECTNAME = 0x00003100
TMDCHUNK_WORLDMATRIX = 0x00003200
TMDCHUNK_STATICLOCALMATRIX = 0x00003300

TMDCHUNK_GEOMETRY = 0x00003400
TMDCHUNK_MESHROW = 0x00003410
TMDCHUNK_STANDARDMESH = 0x00003411
TMDCHUNK_VERTEXLIST = 0x00003412
TMDCHUNK_NORMALLIST = 0x00003413
TMDCHUNK_TEXTUREVERTEXLIST = 0x00003414
TMDCHUNK_FACELIST = 0x00003415
TMDCHUNK_MATERIALNUMBER = 0x00003416
TMDCHUNK_VERTEXINDEXLIST = 0x00003417
TMDCHUNK_FACENORMALLIST = 0x00003418
TMDCHUNK_VERTEXCOLORLIST = 0x00003419
TMDCHUNK_RIGIDSKINTRACK = 0x0000341A
TMDCHUNK_SOFTSKINTRACK = 0x0000341B
TMDCHUNK_VERTEXANIMATIONLIST = 0x0000341C
TMDCHUNK_OLD_RIGIDSKINTRACK = 0x00003901

TMDCHUNK_MORPH = 0x00003500
TMDCHUNK_MORPHTRACK = 0x00003501
TMDCHUNK_LINWAVE = 0x00003600
TMDCHUNK_LINWAVEOBJECTTRACK = 0x00003601
TMDCHUNK_DUMMY = 0x00003700
TMDCHUNK_BONE = 0x00003800
TMDCHUNK_SKIN = 0x00003900

TMDCHUNK_CAMERA = 0x00003A00
TMDCHUNK_CAMERATRACK = 0x00003A01
TMDCHUNK_CAMERAANIMATION = 0x00003A02

TMDCHUNK_LIGHT = 0x00003B00
TMDCHUNK_LIGHTTRACK = 0x00003B01
TMDCHUNK_LIGHTANIMATION = 0x00003B02

TMDCHUNK_PICKBOX = 0x00003C00

TMDCHUNK_VISIBILITYTRACK = 0x00004000
TMDCHUNK_VISIBILITYOBJECT = 0x00004100
TMDCHUNK_SPACEWARPTRACK = 0x00005000
TMDCHUNK_SPACEWARPOBJECT = 0x00005100

TMDCHUNK_XFORMBLOCK = 0x00006000
TMDCHUNK_XFORMOBJECT = 0x00006100
TMDCHUNK_XFORMOBJECT_NUM = 0x00006101
TMDCHUNK_XFORMOBJECT_PARENTNUM = 0x00006102
TMDCHUNK_XFORMOBJECT_PARENTNAME = 0x00006103
TMDCHUNK_POSITIONLIST = 0x00006201
TMDCHUNK_ROTATELIST = 0x00006202
TMDCHUNK_SCALELIST = 0x00006203
TMDCHUNK_ROLLLIST = 0x00006204
TMDCHUNK_SCALEAXISLIST = 0x00006205
TMDCHUNK_INHERITANCEFLAG = 0x00006206

TMDCHUNK_USERDEFINEBLOCK = 0x00007000
TMDCHUNK_NOTEBLOCK = 0x00008000
TMDCHUNK_NOTETRACK = 0x00008100
TMDCHUNK_PROPERTYBLOCK = 0x00009000
TMDCHUNK_PROPERTYTRACK = 0x00009100


@dataclass
class Vector3:
    """3D vector."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z]


@dataclass
class Vector2:
    """2D vector (UV coordinates)."""
    u: float = 0.0
    v: float = 0.0

    def to_tuple(self) -> tuple[float, float]:
        return (self.u, self.v)


@dataclass
class Quaternion:
    """Rotation quaternion."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0


@dataclass
class Matrix3x3:
    """3x3 rotation/scale matrix (row-major)."""
    data: list[float] = field(default_factory=lambda: [1, 0, 0, 0, 1, 0, 0, 0, 1])


@dataclass
class Transform:
    """Object transformation (rotation matrix + translation)."""
    rotation: Matrix3x3 = field(default_factory=Matrix3x3)
    translation: Vector3 = field(default_factory=Vector3)


@dataclass
class TMDMaterial:
    """Material definition."""
    name: str = ""
    ambient: tuple[float, float, float] = (0.2, 0.2, 0.2)
    diffuse: tuple[float, float, float] = (0.8, 0.8, 0.8)
    specular: tuple[float, float, float] = (0.0, 0.0, 0.0)
    two_sided: bool = False
    alpha_map: bool = False
    self_illumination: float = 0.0
    texture_filename: str = ""


@dataclass
class TMDMesh:
    """Mesh geometry data."""
    name: str = ""
    vertices: list[Vector3] = field(default_factory=list)
    normals: list[Vector3] = field(default_factory=list)
    uvs: list[Vector2] = field(default_factory=list)
    faces: list[tuple[int, int, int]] = field(default_factory=list)
    vertex_colors: list[tuple[float, float, float]] = field(default_factory=list)
    material_index: int = -1

    # Skinning data (legacy)
    rigid_skin_bones: list[int] = field(default_factory=list)
    rigid_skin_vertex_bones: list[int] = field(default_factory=list)
    soft_skin_bones: list[int] = field(default_factory=list)
    soft_skin_weights: list[list[tuple[int, float]]] = field(default_factory=list)

    # Unified vertex skinning dict - maps merged vertex index to [(mlib_bone_idx, weight), ...]
    vertex_skinning: dict[int, list[tuple[int, float]]] = field(default_factory=dict)

    # Per-vertex material index - maps vertex index to material index
    # Populated during meshrow merging to preserve submesh material info
    vertex_materials: dict[int, int] = field(default_factory=dict)


@dataclass
class TMDBone:
    """Skeletal bone."""
    name: str = ""
    object_id: int = -1
    parent_id: int = -1
    world_transform: Transform = field(default_factory=Transform)
    local_transform: Transform = field(default_factory=Transform)


@dataclass
class TMDPositionKey:
    """Position animation keyframe."""
    frame: int = 0
    position: Vector3 = field(default_factory=Vector3)
    tension: float = 0.0
    continuity: float = 0.0
    bias: float = 0.0


@dataclass
class TMDRotationKey:
    """Rotation animation keyframe."""
    frame: int = 0
    rotation: Quaternion = field(default_factory=Quaternion)
    tension: float = 0.0
    continuity: float = 0.0
    bias: float = 0.0


@dataclass
class TMDScaleKey:
    """Scale animation keyframe."""
    frame: int = 0
    scale: Vector3 = field(default_factory=Vector3)
    tension: float = 0.0
    continuity: float = 0.0
    bias: float = 0.0


@dataclass
class TMDAnimation:
    """Animation track for an object."""
    object_id: int = -1
    object_name: str = ""
    parent_id: int = -1
    parent_name: str = ""
    position_keys: list[TMDPositionKey] = field(default_factory=list)
    rotation_keys: list[TMDRotationKey] = field(default_factory=list)
    scale_keys: list[TMDScaleKey] = field(default_factory=list)


@dataclass
class TMDObject:
    """A single object in the TMD hierarchy."""
    object_id: int = -1
    name: str = ""
    object_type: str = "unknown"  # geometry, bone, dummy, camera, light, etc.
    world_transform: Transform = field(default_factory=Transform)
    local_transform: Transform = field(default_factory=Transform)
    mesh: TMDMesh | None = None


@dataclass
class TMDModel:
    """Complete TMD model."""
    version: int = TMD_VERSION
    total_frames: float = 0.0
    frame_speed: float = 30.0
    ticks_per_frame: float = 160.0
    ambient_color: tuple[int, int, int] = (128, 128, 128)

    materials: list[TMDMaterial] = field(default_factory=list)
    objects: list[TMDObject] = field(default_factory=list)
    bones: list[TMDBone] = field(default_factory=list)
    animations: list[TMDAnimation] = field(default_factory=list)

    @property
    def meshes(self) -> list[TMDMesh]:
        """Get all meshes from objects."""
        return [obj.mesh for obj in self.objects if obj.mesh is not None]

    def get_stats(self) -> dict:
        """Get model statistics."""
        meshes = self.meshes
        total_vertices = sum(len(m.vertices) for m in meshes)
        total_faces = sum(len(m.faces) for m in meshes)

        return {
            "version": self.version,
            "total_frames": self.total_frames,
            "frame_speed": self.frame_speed,
            "material_count": len(self.materials),
            "object_count": len(self.objects),
            "mesh_count": len(meshes),
            "bone_count": len(self.bones),
            "animation_count": len(self.animations),
            "total_vertices": total_vertices,
            "total_faces": total_faces,
        }


class TMDParser:
    """Parser for TMD model files."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.version = TMD_VERSION
        self._file: BinaryIO | None = None
        self._model: TMDModel | None = None
        self._current_object: TMDObject | None = None
        self._current_mesh: TMDMesh | None = None
        self._current_animation: TMDAnimation | None = None
        self._start_object_id: int = 0
        self._meshrow_vertex_offset: int = 0
        self._skin_running_offset: int = 0

    def parse(self, path: str | Path) -> TMDModel:
        """Parse a TMD file and return the model."""
        path = Path(path)

        with open(path, "rb") as f:
            self._file = f
            self._model = TMDModel()

            # Read TMD header
            manufacturer = self._read_asciiz()
            extension = self._read_asciiz()
            if extension not in ("TMD", "PRT"):
                raise ValueError(f"Invalid TMD extension: {extension}")

            self.version = self._read_uint()
            self._model.version = self.version
            _export_date = self._read_uint()
            _export_time = self._read_uint()

            # Read chunks until EOF
            start_pos = f.tell()
            f.seek(0, 2)
            end_pos = f.tell()
            f.seek(start_pos)

            while f.tell() < end_pos:
                chunk = self._read_chunk_header()
                if chunk is None:
                    break
                chunk_id, chunk_len, chunk_end = chunk
                self._parse_chunk(chunk_id, chunk_len, chunk_end)

            return self._model

    def _read_bytes(self, size: int) -> bytes:
        """Read bytes from file."""
        data = self._file.read(size)
        if len(data) < size:
            return b""
        return data

    def _read_int(self) -> int:
        """Read a 32-bit signed integer."""
        data = self._read_bytes(4)
        if len(data) < 4:
            return 0
        return struct.unpack("<i", data)[0]

    def _read_uint(self) -> int:
        """Read a 32-bit unsigned integer."""
        data = self._read_bytes(4)
        if len(data) < 4:
            return 0
        return struct.unpack("<I", data)[0]

    def _read_float(self) -> float:
        """Read a 32-bit float."""
        data = self._read_bytes(4)
        if len(data) < 4:
            return 0.0
        return struct.unpack("<f", data)[0]

    def _read_vector3(self) -> Vector3:
        """Read a 3D vector."""
        return Vector3(
            x=self._read_float(),
            y=self._read_float(),
            z=self._read_float(),
        )

    def _read_quaternion(self) -> Quaternion:
        """Read a quaternion."""
        return Quaternion(
            x=self._read_float(),
            y=self._read_float(),
            z=self._read_float(),
            w=self._read_float(),
        )

    def _read_matrix3x3(self) -> Matrix3x3:
        """Read a 3x3 matrix."""
        data = [self._read_float() for _ in range(9)]
        return Matrix3x3(data=data)

    def _read_transform(self) -> Transform:
        """Read a transform (3x3 rotation + translation)."""
        rotation = self._read_matrix3x3()
        translation = self._read_vector3()
        return Transform(rotation=rotation, translation=translation)

    def _read_asciiz(self) -> str:
        """Read a null-terminated ASCII string."""
        chars = []
        while True:
            c = self._file.read(1)
            if not c or c == b"\x00":
                break
            chars.append(c)
        try:
            return b"".join(chars).decode("ascii", errors="replace")
        except Exception:
            return ""

    def _read_chunk_header(self) -> tuple[int, int, int] | None:
        """Read chunk header (id, length, end_pos)."""
        start_pos = self._file.tell()
        data = self._read_bytes(8)
        if len(data) < 8:
            return None
        chunk_id, chunk_len = struct.unpack("<II", data)
        end_pos = start_pos + chunk_len
        return chunk_id, chunk_len, end_pos

    def _skip_bytes(self, count: int) -> None:
        """Skip bytes in file."""
        self._file.seek(count, 1)

    def _parse_chunk(self, chunk_id: int, chunk_len: int, end_pos: int) -> None:
        """Parse a single chunk."""
        handler = self._get_handler(chunk_id)
        if handler:
            handler(end_pos)
        else:
            self._file.seek(end_pos)

        if self._file.tell() != end_pos:
            self._file.seek(end_pos)

    def _get_handler(self, chunk_id: int):
        """Get handler function for chunk type."""
        handlers = {
            TMDCHUNK_MAIN: self._handle_main,
            TMDCHUNK_GLOBALBLOCK: self._handle_container,
            TMDCHUNK_ALLFRAME: self._handle_allframe,
            TMDCHUNK_FRAMESPEED: self._handle_framespeed,
            TMDCHUNK_TICKPERFRAME: self._handle_tickperframe,
            TMDCHUNK_GLOBALAMBIENT: self._handle_globalambient,
            TMDCHUNK_OBJECTBLOCK: self._handle_container,
            TMDCHUNK_MATERIALTRACK: self._handle_container,
            TMDCHUNK_MATERIAL: self._handle_material,
            TMDCHUNK_OBJECTTRACK: self._handle_objecttrack,
            TMDCHUNK_STARTOBJECTID: self._handle_startobjectid,
            TMDCHUNK_OBJECTNAME: self._handle_objectname,
            TMDCHUNK_WORLDMATRIX: self._handle_worldmatrix,
            TMDCHUNK_STATICLOCALMATRIX: self._handle_staticlocalmatrix,
            TMDCHUNK_GEOMETRY: self._handle_geometry,
            TMDCHUNK_SKIN: self._handle_skin,
            TMDCHUNK_MESHROW: self._handle_meshrow,
            TMDCHUNK_STANDARDMESH: self._handle_standardmesh,
            TMDCHUNK_VERTEXLIST: self._handle_vertexlist,
            TMDCHUNK_NORMALLIST: self._handle_normallist,
            TMDCHUNK_TEXTUREVERTEXLIST: self._handle_texturevertexlist,
            TMDCHUNK_FACELIST: self._handle_facelist,
            TMDCHUNK_MATERIALNUMBER: self._handle_materialnumber,
            TMDCHUNK_VERTEXCOLORLIST: self._handle_vertexcolorlist,
            TMDCHUNK_RIGIDSKINTRACK: self._handle_rigidskintrack,
            TMDCHUNK_SOFTSKINTRACK: self._handle_softskintrack,
            TMDCHUNK_BONE: self._handle_bone,
            TMDCHUNK_DUMMY: self._handle_dummy,
            TMDCHUNK_XFORMBLOCK: self._handle_container,
            TMDCHUNK_XFORMOBJECT: self._handle_xformobject,
            TMDCHUNK_XFORMOBJECT_NUM: self._handle_xformobject_num,
            TMDCHUNK_XFORMOBJECT_PARENTNUM: self._handle_xformobject_parentnum,
            TMDCHUNK_XFORMOBJECT_PARENTNAME: self._handle_xformobject_parentname,
            TMDCHUNK_POSITIONLIST: self._handle_positionlist,
            TMDCHUNK_ROTATELIST: self._handle_rotatelist,
            TMDCHUNK_SCALELIST: self._handle_scalelist,
        }
        return handlers.get(chunk_id)

    def _handle_main(self, end_pos: int) -> None:
        """Handle MAIN chunk (container)."""
        while self._file.tell() < end_pos:
            chunk = self._read_chunk_header()
            if chunk is None:
                break
            self._parse_chunk(chunk[0], chunk[1], chunk[2])

    def _handle_container(self, end_pos: int) -> None:
        """Handle container chunks (read nested chunks)."""
        while self._file.tell() < end_pos:
            chunk = self._read_chunk_header()
            if chunk is None:
                break
            self._parse_chunk(chunk[0], chunk[1], chunk[2])

    def _handle_allframe(self, chunk_len: int) -> None:
        """Handle ALLFRAME chunk."""
        self._model.total_frames = self._read_float()

    def _handle_framespeed(self, chunk_len: int) -> None:
        """Handle FRAMESPEED chunk."""
        self._model.frame_speed = self._read_float()

    def _handle_tickperframe(self, chunk_len: int) -> None:
        """Handle TICKPERFRAME chunk."""
        self._model.ticks_per_frame = self._read_float()

    def _handle_globalambient(self, chunk_len: int) -> None:
        """Handle GLOBALAMBIENT chunk."""
        r = self._read_bytes(1)[0]
        g = self._read_bytes(1)[0]
        b = self._read_bytes(1)[0]
        self._model.ambient_color = (r, g, b)

    def _handle_material(self, chunk_len: int) -> None:
        """Handle MATERIAL chunk."""
        material = TMDMaterial()
        material.name = self._read_asciiz()
        material.ambient = (self._read_float(), self._read_float(), self._read_float())
        material.diffuse = (self._read_float(), self._read_float(), self._read_float())
        material.specular = (self._read_float(), self._read_float(), self._read_float())
        material.two_sided = bool(self._read_int())
        material.alpha_map = bool(self._read_int())

        if self.version >= TMD_VERSION_20031217:
            material.self_illumination = self._read_float()

        texture_count = self._read_int()
        if texture_count > 0:
            material.texture_filename = self._read_asciiz()

        self._model.materials.append(material)

    def _handle_objecttrack(self, end_pos: int) -> None:
        """Handle OBJECTTRACK chunk (container for objects)."""
        self._handle_container(end_pos)

    def _handle_startobjectid(self, chunk_len: int) -> None:
        """Handle STARTOBJECTID chunk."""
        self._start_object_id = self._read_int()
        if self._current_object:
            self._current_object.object_id = self._start_object_id

    def _handle_objectname(self, chunk_len: int) -> None:
        """Handle OBJECTNAME chunk."""
        name = self._read_asciiz()
        if self._current_object:
            self._current_object.name = name
        if self._current_animation:
            self._current_animation.object_name = name

    def _handle_worldmatrix(self, chunk_len: int) -> None:
        """Handle WORLDMATRIX chunk."""
        transform = self._read_transform()
        if self._current_object:
            self._current_object.world_transform = transform

    def _handle_staticlocalmatrix(self, chunk_len: int) -> None:
        """Handle STATICLOCALMATRIX chunk."""
        transform = self._read_transform()
        if self._current_object:
            self._current_object.local_transform = transform

    def _handle_geometry(self, end_pos: int) -> None:
        """Handle GEOMETRY chunk."""
        self._current_object = TMDObject()
        self._current_object.object_type = "geometry"
        self._current_mesh = None

        _divided_mesh_count = self._read_uint()
        _morph_target_count = self._read_uint()

        self._handle_container(end_pos)

        self._model.objects.append(self._current_object)
        self._current_object = None

    def _handle_skin(self, end_pos: int) -> None:
        """Handle SKIN chunk."""
        self._current_object = TMDObject()
        self._current_object.object_type = "skin"
        self._current_mesh = None

        _divided_mesh_count = self._read_uint()
        _morph_target_count = self._read_uint()

        self._handle_container(end_pos)

        self._model.objects.append(self._current_object)
        self._current_object = None

    def _handle_meshrow(self, end_pos: int) -> None:
        """Handle MESHROW chunk."""
        if self._current_object:
            if self._current_object.mesh is not None:
                self._meshrow_vertex_offset = len(self._current_object.mesh.vertices)
            else:
                self._meshrow_vertex_offset = 0

            self._skin_running_offset = self._meshrow_vertex_offset
            self._current_mesh = TMDMesh()
            self._current_mesh.name = self._current_object.name
            if self._current_object.mesh is None:
                self._current_object.mesh = self._current_mesh

        self._handle_container(end_pos)

        # Merge meshrow data into main mesh
        if self._current_object and self._current_object.mesh is not None and self._current_mesh is not None:
            main_mesh = self._current_object.mesh
            if main_mesh is not self._current_mesh:
                face_offset = len(main_mesh.vertices)
                main_mesh.vertices.extend(self._current_mesh.vertices)
                main_mesh.normals.extend(self._current_mesh.normals)
                main_mesh.uvs.extend(self._current_mesh.uvs)
                main_mesh.vertex_colors.extend(self._current_mesh.vertex_colors)

                for f in self._current_mesh.faces:
                    main_mesh.faces.append((f[0] + face_offset, f[1] + face_offset, f[2] + face_offset))

                main_mesh.vertex_skinning.update(self._current_mesh.vertex_skinning)

                # Track per-vertex material assignments from this meshrow
                meshrow_mat = self._current_mesh.material_index
                for v_idx in range(len(self._current_mesh.vertices)):
                    main_mesh.vertex_materials[face_offset + v_idx] = meshrow_mat
            else:
                # First meshrow becomes the main mesh - track its materials
                meshrow_mat = self._current_mesh.material_index
                for v_idx in range(len(self._current_mesh.vertices)):
                    main_mesh.vertex_materials[v_idx] = meshrow_mat

    def _handle_standardmesh(self, end_pos: int) -> None:
        """Handle STANDARDMESH chunk."""
        self._handle_container(end_pos)

    def _handle_vertexlist(self, chunk_len: int) -> None:
        """Handle VERTEXLIST chunk."""
        count = self._read_uint()
        mesh = self._current_mesh
        if mesh is None and self._current_object:
            if self._current_object.mesh is None:
                self._current_object.mesh = TMDMesh()
                self._current_object.mesh.name = self._current_object.name
            mesh = self._current_object.mesh

        if mesh:
            for _ in range(count):
                mesh.vertices.append(self._read_vector3())

    def _handle_normallist(self, chunk_len: int) -> None:
        """Handle NORMALLIST chunk."""
        count = self._read_uint()
        mesh = self._current_mesh or (self._current_object.mesh if self._current_object else None)
        if mesh:
            for _ in range(count):
                mesh.normals.append(self._read_vector3())

    def _handle_texturevertexlist(self, chunk_len: int) -> None:
        """Handle TEXTUREVERTEXLIST chunk."""
        count = self._read_uint()
        mesh = self._current_mesh or (self._current_object.mesh if self._current_object else None)
        if mesh:
            for _ in range(count):
                u = self._read_float()
                v = self._read_float()
                _w = self._read_float()
                mesh.uvs.append(Vector2(u=u, v=v))

    def _handle_facelist(self, chunk_len: int) -> None:
        """Handle FACELIST chunk."""
        count = self._read_uint()
        mesh = self._current_mesh or (self._current_object.mesh if self._current_object else None)
        if mesh:
            for _ in range(count):
                i0 = self._read_uint()
                i1 = self._read_uint()
                i2 = self._read_uint()
                mesh.faces.append((i0, i1, i2))

    def _handle_materialnumber(self, chunk_len: int) -> None:
        """Handle MATERIALNUMBER chunk."""
        mat_idx = self._read_int()
        mesh = self._current_mesh or (self._current_object.mesh if self._current_object else None)
        if mesh:
            mesh.material_index = mat_idx

    def _handle_vertexcolorlist(self, chunk_len: int) -> None:
        """Handle VERTEXCOLORLIST chunk."""
        count = self._read_uint()
        mesh = self._current_mesh or (self._current_object.mesh if self._current_object else None)
        if mesh:
            for _ in range(count):
                r = self._read_float()
                g = self._read_float()
                b = self._read_float()
                mesh.vertex_colors.append((r, g, b))

    def _handle_rigidskintrack(self, chunk_len: int) -> None:
        """Handle RIGIDSKINTRACK chunk (rigid skinning)."""
        mesh = self._current_mesh if self._current_mesh else (self._current_object.mesh if self._current_object else None)
        if not mesh:
            self._skip_bytes(chunk_len)
            return

        if self.version >= TMD_VERSION_20030402:
            bone_count = self._read_int()
            skin_bones = [self._read_int() for _ in range(bone_count)]
            mesh.rigid_skin_bones = skin_bones

            vertex_count = self._read_int()
            vertex_bones = [self._read_int() for _ in range(vertex_count)]
            mesh.rigid_skin_vertex_bones = vertex_bones

            vertex_offset = self._skin_running_offset
            for v_idx, local_bone_idx in enumerate(vertex_bones):
                if local_bone_idx < len(skin_bones):
                    global_bone_idx = skin_bones[local_bone_idx]
                else:
                    global_bone_idx = 0

                merged_vertex_idx = vertex_offset + v_idx
                mesh.vertex_skinning[merged_vertex_idx] = [(global_bone_idx, 1.0)]

            self._skin_running_offset += len(vertex_bones)

    def _handle_softskintrack(self, chunk_len: int) -> None:
        """Handle SOFTSKINTRACK chunk (skeletal skinning)."""
        mesh = self._current_mesh if self._current_mesh else (self._current_object.mesh if self._current_object else None)
        if not mesh:
            self._skip_bytes(chunk_len)
            return

        if self.version >= TMD_VERSION_20030402:
            bone_count = self._read_int()
            skin_bones = [self._read_int() for _ in range(bone_count)]
            mesh.soft_skin_bones = skin_bones

            total_influences = self._read_int()
            vertex_offset = self._skin_running_offset
            soft_vertex_idx = 0

            mesh.soft_skin_weights = []
            influences_read = 0
            while influences_read < total_influences:
                influence_count = self._read_int()
                vertex_weights = []
                unified_weights = []
                for _ in range(influence_count):
                    bone_id = self._read_int()
                    weight = self._read_float()
                    vertex_weights.append((bone_id, weight))
                    influences_read += 1

                    if bone_id < len(skin_bones):
                        global_bone_idx = skin_bones[bone_id]
                    else:
                        global_bone_idx = 0
                    unified_weights.append((global_bone_idx, weight))

                mesh.soft_skin_weights.append(vertex_weights)
                merged_vertex_idx = vertex_offset + soft_vertex_idx
                mesh.vertex_skinning[merged_vertex_idx] = unified_weights
                soft_vertex_idx += 1

            self._skin_running_offset += soft_vertex_idx

    def _handle_bone(self, end_pos: int) -> None:
        """Handle BONE chunk."""
        self._current_object = TMDObject()
        self._current_object.object_type = "bone"
        self._current_mesh = None

        self._handle_container(end_pos)

        bone = TMDBone(
            name=self._current_object.name,
            object_id=self._current_object.object_id,
            world_transform=self._current_object.world_transform,
            local_transform=self._current_object.local_transform,
        )
        self._model.bones.append(bone)
        self._model.objects.append(self._current_object)
        self._current_object = None

    def _handle_dummy(self, end_pos: int) -> None:
        """Handle DUMMY chunk."""
        self._current_object = TMDObject()
        self._current_object.object_type = "dummy"
        self._current_mesh = None

        self._handle_container(end_pos)

        self._model.objects.append(self._current_object)
        self._current_object = None

    def _handle_xformobject(self, end_pos: int) -> None:
        """Handle XFORMOBJECT chunk (animation track container)."""
        self._current_animation = TMDAnimation()
        self._handle_container(end_pos)

        if self._current_animation:
            self._model.animations.append(self._current_animation)
            self._current_animation = None

    def _handle_xformobject_num(self, chunk_len: int) -> None:
        """Handle XFORMOBJECT_NUM chunk."""
        obj_id = self._read_int()
        if self._current_animation:
            self._current_animation.object_id = obj_id

    def _handle_xformobject_parentnum(self, chunk_len: int) -> None:
        """Handle XFORMOBJECT_PARENTNUM chunk."""
        parent_id = self._read_int()
        if self._current_animation:
            self._current_animation.parent_id = parent_id

    def _handle_xformobject_parentname(self, chunk_len: int) -> None:
        """Handle XFORMOBJECT_PARENTNAME chunk."""
        parent_name = self._read_asciiz()
        if self._current_animation:
            self._current_animation.parent_name = parent_name

    def _read_ort(self) -> tuple[int, int]:
        """Read out-of-range types."""
        before = self._read_int()
        after = self._read_int()
        return before, after

    def _read_tcb_key(self) -> tuple[float, float, float, float, float]:
        """Read TCB key parameters."""
        tension = self._read_float()
        continuity = self._read_float()
        bias = self._read_float()
        ease_from = self._read_float()
        ease_to = self._read_float()
        return tension, continuity, bias, ease_from, ease_to

    def _handle_positionlist(self, chunk_len: int) -> None:
        """Handle POSITIONLIST chunk."""
        if not self._current_animation:
            self._skip_bytes(chunk_len)
            return

        key_count = self._read_uint()
        self._read_ort()

        for _ in range(key_count):
            frame = self._read_uint()
            position = self._read_vector3()
            tcb = self._read_tcb_key()

            key = TMDPositionKey(
                frame=frame,
                position=position,
                tension=tcb[0],
                continuity=tcb[1],
                bias=tcb[2],
            )
            self._current_animation.position_keys.append(key)

    def _handle_rotatelist(self, chunk_len: int) -> None:
        """Handle ROTATELIST chunk."""
        if not self._current_animation:
            self._skip_bytes(chunk_len)
            return

        key_count = self._read_uint()
        self._read_ort()

        for _ in range(key_count):
            frame = self._read_uint()
            rotation = self._read_quaternion()
            tcb = self._read_tcb_key()

            key = TMDRotationKey(
                frame=frame,
                rotation=rotation,
                tension=tcb[0],
                continuity=tcb[1],
                bias=tcb[2],
            )
            self._current_animation.rotation_keys.append(key)

    def _handle_scalelist(self, chunk_len: int) -> None:
        """Handle SCALELIST chunk."""
        if not self._current_animation:
            self._skip_bytes(chunk_len)
            return

        key_count = self._read_uint()
        self._read_ort()

        for _ in range(key_count):
            frame = self._read_uint()
            scale = self._read_vector3()
            tcb = self._read_tcb_key()

            key = TMDScaleKey(
                frame=frame,
                scale=scale,
                tension=tcb[0],
                continuity=tcb[1],
                bias=tcb[2],
            )
            self._current_animation.scale_keys.append(key)
