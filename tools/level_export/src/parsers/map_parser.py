"""MAP parser — the movement attribute grid (the original's walkability data).

File layout (worked out against retail client behavior): two skipped int32
headers, a pathfinding cell grid (int32 dx/dy then dx*dy 4-byte records —
edge bookkeeping the original client reads and immediately discards), then
the attribute map (int32 dx/dy then dy rows x dx SIGNED bytes). Row j is
truncated world Z == j, column i is truncated world X == i — the original
client queries it at truncated world X/Z, the same 1 m cell convention as
the .opg wall grid, no scanline flip.

Movability: a cell is movable iff its SIGNED attribute > 0; out-of-bounds
is blocked. Attributes shipped fleet-wide: 0 (blocked, 74%), 1/2 (open
ground), 13/15/17/19 (sit targets — walkable; the motion table maps them to
sit motions), -51 (blocked, 23 cells). The original client also has a
trapped-start special case (movement out of a blocked start cell is
allowed) — the Godot runner ports the same idea.

This grid is the original's ONLY movement authority (its A* pathfinder
walks it; the .opg wall grid is line-of-sight data). Fleet: all 325 maps
ship a parseable .map with attribute dims == cell-grid dims.
"""
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MoveGrid:
    width: int    # dx — cells per row (truncated world X)
    height: int   # dy — rows (truncated world Z)
    attrs: bytes  # row-major SIGNED attribute bytes, row 0 == world Z 0

    def attr(self, x: int, z: int) -> int:
        """Signed attribute at cell (x, z); raises on out-of-bounds."""
        if not (0 <= x < self.width and 0 <= z < self.height):
            raise IndexError(f"cell ({x}, {z}) outside {self.width}x{self.height}")
        v = self.attrs[z * self.width + x]
        return v - 256 if v > 127 else v

    def movable(self, x: int, z: int) -> bool:
        """The original walkability rule: signed attr > 0, out-of-bounds blocked."""
        if not (0 <= x < self.width and 0 <= z < self.height):
            return False
        return self.attr(x, z) > 0


CELL_RECORD_SIZE = 4  # pathfinding cell record incl. padding; all 325 shipped files


def parse_map(path: Path | str) -> MoveGrid:
    data = Path(path).read_bytes()
    if len(data) < 24:
        raise ValueError(f"{path}: too short for a .map header")
    # Two skipped header ints (the original reads them into a throwaway).
    cell_dx, cell_dy = struct.unpack_from("<2i", data, 8)
    if not (0 < cell_dx <= 1024 and 0 < cell_dy <= 1024):
        raise ValueError(f"{path}: implausible cell grid {cell_dx}x{cell_dy}")
    att_off = 16 + cell_dx * cell_dy * CELL_RECORD_SIZE
    if att_off + 8 > len(data):
        raise ValueError(f"{path}: truncated before the attribute grid")
    dx, dy = struct.unpack_from("<2i", data, att_off)
    if (dx, dy) != (cell_dx, cell_dy):
        raise ValueError(
            f"{path}: attribute grid {dx}x{dy} != cell grid {cell_dx}x{cell_dy} "
            "— cell record size assumption broken for this file")
    start = att_off + 8
    if start + dx * dy > len(data):
        raise ValueError(f"{path}: truncated attribute grid")
    return MoveGrid(width=dx, height=dy, attrs=bytes(data[start:start + dx * dy]))
