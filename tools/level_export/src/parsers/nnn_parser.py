"""NNN parser — navigation mesh (walkable prop surfaces).

Reader matches the retail client's navmesh loading behavior; the format was
written by the map editor tooling.

Layout (little-endian, BYTE-PACKED — the 6-byte mesh header leaves every
cell float misaligned, so records must be unpacked individually):

  uint32 mesh_count
  per mesh: uint16 mesh_id (IGNORED — the editor assigns IDs inside the
            per-cell loop, so zero-cell meshes keep a stale value; the
            runtime keys meshes by load index), uint32 cell_count,
            cell_count x 88 bytes
  trailing tile index, present iff bytes remain (the client's EOF test is
  pos >= size — true of all 325 shipped files):
      uint32 tile_count
      per tile: uint16 x, uint16 z, uint16 n, n x (uint16 mesh, uint16 cell)

Nav cell record (88 bytes): int32 id; float normal[3]; float d;
float vtx0/1/2[3]; 4 x int32 connected-object ids; int32
neighbor[3]; uint32 unique_id. Only normal/d/verts are kept: the runtime
rebuilds neighbours from vertex sharing at load, the connected-object ids
are editor provenance the runtime never reads, and unique_id is
uninitialised stack memory (0xCCCCCCCC in all 120,041 shipped cells).

Vertices are absolute WORLD coordinates despite being stored per placed
object: the editor bakes the placed object's world matrix in before storing
and the runtime applies no transform. Kept verbatim in original (D3D) space.
"""
import struct
from dataclasses import dataclass, field
from pathlib import Path

CELL_SIZE = 88
_CELL = struct.Struct("<i3ff3f3f3f4i3iI")
## Un-normalized projected-cross-product floor used by the original
## client's cell height lookup: cells at or below it are near-vertical
## wall faces the original silently skips.
VERTICAL_EPSILON = 0.0001


@dataclass
class NavCell:
    normal: tuple[float, float, float]
    d: float
    verts: tuple[tuple[float, float, float], tuple[float, float, float],
                 tuple[float, float, float]]


@dataclass
class NavMesh:
    cells: list[NavCell] = field(default_factory=list)
    mesh_cell_ranges: list[tuple[int, int]] = field(default_factory=list)
    tiles: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    bytes_consumed: int = 0


def is_standable(cell: NavCell) -> bool:
    (x0, _, z0), (x1, _, z1), (x2, _, z2) = cell.verts
    ux, uz = x1 - x0, z1 - z0
    vx, vz = x2 - x0, z2 - z0
    return abs(uz * vx - ux * vz) > VERTICAL_EPSILON


def parse_nnn(path: Path | str) -> NavMesh:
    data = Path(path).read_bytes()
    nav = NavMesh()
    off = 0
    mesh_count = struct.unpack_from("<I", data, off)[0]
    off += 4
    for _ in range(mesh_count):
        # mesh_id at `off` is deliberately ignored (see module docstring).
        cell_count = struct.unpack_from("<I", data, off + 2)[0]
        off += 6
        start = len(nav.cells)
        for _ in range(cell_count):
            f = _CELL.unpack_from(data, off)
            nav.cells.append(NavCell(
                normal=(f[1], f[2], f[3]),
                d=f[4],
                verts=((f[5], f[6], f[7]), (f[8], f[9], f[10]),
                       (f[11], f[12], f[13])),
            ))
            off += CELL_SIZE
        nav.mesh_cell_ranges.append((start, cell_count))

    if off < len(data):
        tile_count = struct.unpack_from("<I", data, off)[0]
        off += 4
        for _ in range(tile_count):
            tx, tz, n = struct.unpack_from("<3H", data, off)
            off += 6
            refs: list[int] = []
            for _ in range(n):
                mesh_idx, cell_idx = struct.unpack_from("<2H", data, off)
                off += 4
                start, count = nav.mesh_cell_ranges[mesh_idx]
                if cell_idx < count:
                    refs.append(start + cell_idx)
            nav.tiles[(tx, tz)] = refs
    nav.bytes_consumed = off
    return nav
