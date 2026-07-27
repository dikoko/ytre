"""
WTR Parser — per-map water mesh + region data.

Binary format follows the retail client's water-info serialization order
verbatim, with NO archive class header — the client opens the file and
serializes the single object directly (validated byte-level:
SF001001.wtr begins with the four int32 counts 4,0,1,0).

Layout:
  int32 num_vertex, num_side_vertex, num_mesh, num_side_mesh
  water vertices [num_vertex], then [num_side_vertex] — 44 bytes each:
      pos 3f, normal 3f, diffuse ARGB dword, uv1 2f, uv2 2f
  per mesh (then per side mesh):
      int32 num_triangle; uint16 strip[num_triangle + 2]  (TRIANGLESTRIP)
  bounding spheres: centers 3f*num_mesh + radii f*num_mesh, then side
  int32 num_texture; NUL-terminated names
  beach params: int32 size_u, size_n; float delta, frequency, velocity,
      life; int32 beach_texture_ids[2]
  int32 num_water_object; per object (retail water-object serialization order):
      dword fog_color; float fog_start, fog_end; int32 grp_id;
      byte tex0, tex1, side_tex0, side_tex1; float water_height;
      int32 type (0 flowing / 1 still);
      int32 n + int32 mesh_ids[n]; int32 m + int32 side_mesh_ids[m];
      int32 num_beach + shore arrays Normal[], U[], Position[] — three
      CONTIGUOUS 3f arrays (each array written whole, not interleaved),
      U non-unit (carries per-point quad half-width);
      MatInfo[4] — 12 floats each (a0,a1,b0,b1,c0,c1,d0,d1,e0,e1,f0,f1)

The second UV set is parsed but dead at render time: the original renderer
points both texture stages at UV set 0.
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WaterVertex:
    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    diffuse: int  # D3D ARGB dword
    uv1: tuple[float, float]
    uv2: tuple[float, float]


@dataclass
class WaterMesh:
    num_triangles: int
    strip_indices: list[int]


@dataclass
class WaterObject:
    fog_color: int
    fog_start: float
    fog_end: float
    grp_id: int
    texture0: int
    texture1: int
    side_texture0: int
    side_texture1: int
    water_height: float
    type: int  # 0 flowing / 1 still (GKEWATERMATTYPE)
    mesh_ids: list[int]
    side_mesh_ids: list[int]
    num_beach: int
    mat_info: list[list[float]]  # 4 rows x 12 coefficients
    beach_normals: list[tuple[float, float, float]] = field(default_factory=list)
    beach_us: list[tuple[float, float, float]] = field(default_factory=list)
    beach_positions: list[tuple[float, float, float]] = field(default_factory=list)


@dataclass
class WaterInfo:
    vertices: list[WaterVertex]
    side_vertices: list[WaterVertex]
    meshes: list[WaterMesh]
    side_meshes: list[WaterMesh]
    textures: list[str]
    beach_texture_ids: tuple[int, int]
    water_objects: list[WaterObject]
    bytes_consumed: int = 0
    # beach emitter params (file-level, shared by all water objects)
    beach_size_u: int = 0
    beach_size_n: int = 0
    beach_delta: float = 0.0
    beach_frequency: float = 0.0
    beach_velocity: float = 0.0
    beach_life: float = 0.0


def strip_to_triangles(strip: list[int]) -> list[tuple[int, int, int]]:
    """D3D TRIANGLESTRIP -> triangle list with alternating winding;
    degenerate (repeated-index) triangles dropped."""
    tris = []
    for i in range(len(strip) - 2):
        a, b, c = strip[i], strip[i + 1], strip[i + 2]
        if a == b or b == c or a == c:
            continue
        if i % 2 == 0:
            tris.append((a, b, c))
        else:
            tris.append((b, a, c))  # D3D odd-triangle order
    return tris


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.off = 0

    def read(self, fmt: str):
        vals = struct.unpack_from("<" + fmt, self.data, self.off)
        self.off += struct.calcsize("<" + fmt)
        return vals

    def i32(self) -> int:
        return self.read("i")[0]

    def string(self) -> str:
        # Strings are stored as raw bytes + NUL
        end = self.data.index(b"\0", self.off)
        s = self.data[self.off:end].decode("cp949", errors="replace")
        self.off = end + 1
        return s


def _read_vertices(r: _Reader, count: int) -> list[WaterVertex]:
    out = []
    for _ in range(count):
        v = r.read("6f I 4f".replace(" ", ""))
        out.append(WaterVertex(
            position=v[0:3], normal=v[3:6], diffuse=v[6],
            uv1=v[7:9], uv2=v[9:11],
        ))
    return out


def _read_meshes(r: _Reader, count: int) -> list[WaterMesh]:
    out = []
    for _ in range(count):
        n_tri = r.i32()
        strip = list(r.read(f"{n_tri + 2}H")) if n_tri + 2 > 0 else []
        out.append(WaterMesh(num_triangles=n_tri, strip_indices=strip))
    return out


class WTRParser:
    def parse(self, path: Path | str) -> WaterInfo:
        data = Path(path).read_bytes()
        r = _Reader(data)

        n_vtx, n_side_vtx, n_mesh, n_side_mesh = r.read("4i")
        vertices = _read_vertices(r, n_vtx)
        side_vertices = _read_vertices(r, n_side_vtx)
        meshes = _read_meshes(r, n_mesh)
        side_meshes = _read_meshes(r, n_side_mesh)

        # bounding spheres (unused downstream, skipped over)
        r.read(f"{3 * n_mesh}f")
        r.read(f"{n_mesh}f")
        r.read(f"{3 * n_side_mesh}f")
        r.read(f"{n_side_mesh}f")

        textures = [r.string() for _ in range(r.i32())]

        beach_size_u, beach_size_n = r.read("2i")
        beach_delta, beach_freq, beach_vel, beach_life = r.read("4f")
        beach_tex = tuple(r.read("2i"))

        objects = []
        for _ in range(r.i32()):
            fog_color = r.read("I")[0]
            fog_start, fog_end = r.read("2f")
            grp_id = r.i32()
            t0, t1, st0, st1 = r.read("4B")
            water_height = r.read("f")[0]
            obj_type = r.i32()
            mesh_ids = list(r.read(f"{r.i32()}i"))
            side_mesh_ids = list(r.read(f"{r.i32()}i"))
            num_beach = r.i32()
            beach_normals = [r.read("3f") for _ in range(num_beach)]
            beach_us = [r.read("3f") for _ in range(num_beach)]
            beach_positions = [r.read("3f") for _ in range(num_beach)]
            mat_info = [list(r.read("12f")) for _ in range(4)]
            objects.append(WaterObject(
                fog_color=fog_color, fog_start=fog_start, fog_end=fog_end,
                grp_id=grp_id, texture0=t0, texture1=t1,
                side_texture0=st0, side_texture1=st1,
                water_height=water_height, type=obj_type,
                mesh_ids=mesh_ids, side_mesh_ids=side_mesh_ids,
                num_beach=num_beach, mat_info=mat_info,
                beach_normals=beach_normals, beach_us=beach_us,
                beach_positions=beach_positions,
            ))

        return WaterInfo(
            vertices=vertices, side_vertices=side_vertices,
            meshes=meshes, side_meshes=side_meshes,
            textures=textures, beach_texture_ids=beach_tex,
            water_objects=objects, bytes_consumed=r.off,
            beach_size_u=beach_size_u, beach_size_n=beach_size_n,
            beach_delta=beach_delta, beach_frequency=beach_freq,
            beach_velocity=beach_vel, beach_life=beach_life,
        )
