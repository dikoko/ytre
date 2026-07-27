"""
CVS Parser — Terrain tile canvas data.

Binary format (reverse-engineered):
  Header: uint32 version + uint16 palette_count
  Palette: palette_count × 8 bytes (4 × uint16 tile IDs)
  Grid: uint16 grid_rows + uint16 grid_cols
  Cells: grid_rows × grid_cols × 8 bytes (uint16 palette_id + 2 padding + uint32 visible)
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CanvasData:
    version: int
    grid_rows: int
    grid_cols: int
    palette: list[tuple[int, int, int, int]] = field(default_factory=list)
    cells: list[list[int]] = field(default_factory=list)
    visibility: list[list[bool]] = field(default_factory=list)


class CVSParser:
    PALETTE_ENTRY_SIZE = 8   # 4 × uint16
    CELL_SIZE = 8            # uint16 + 2 pad + uint32

    def parse(self, path: Path | str) -> CanvasData:
        path = Path(path)
        with open(path, "rb") as f:
            data = f.read()

        version = struct.unpack_from("<I", data, 0)[0]
        palette_count = struct.unpack_from("<H", data, 4)[0]

        offset = 6
        palette = []
        for _ in range(palette_count):
            tiles = struct.unpack_from("<4H", data, offset)
            palette.append(tiles)
            offset += self.PALETTE_ENTRY_SIZE

        grid_rows = struct.unpack_from("<H", data, offset)[0]
        grid_cols = struct.unpack_from("<H", data, offset + 2)[0]
        offset += 4

        cells = []
        visibility = []
        for r in range(grid_rows):
            row_cells = []
            row_vis = []
            for c in range(grid_cols):
                pal_id = struct.unpack_from("<H", data, offset)[0]
                vis = struct.unpack_from("<I", data, offset + 4)[0]
                row_cells.append(pal_id)
                row_vis.append(bool(vis))
                offset += self.CELL_SIZE
            cells.append(row_cells)
            visibility.append(row_vis)

        return CanvasData(
            version=version,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            palette=palette,
            cells=cells,
            visibility=visibility,
        )
