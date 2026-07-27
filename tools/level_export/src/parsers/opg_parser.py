"""OPG parser — object-property (wall) cell grid.

The original client loads this grid alongside the terrain heightmap; cell
values are 0 = open, 1 = wall (a 0xF000 "user disable" value exists in the
format but never shipped). 16 bpp BI_RGB BMP, 40-byte info header, bottom-up
scanlines with the stride padded to 4 bytes; dimensions are the CELL grid
(nMapRow-1) x (nMapCol-1), one row/col smaller than the heightmap. The
original client's image loader flips scanlines on load so buffer row
0 == world Z 0, the same orientation as {code}_h.bmp.

Only the exact value 1 counts as a wall — two shipped files (SF001009,
SF002015) contain MSVC heap fill, which the original client's exact-equality
wall test likewise treats as open ground.
"""
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WallGrid:
    width: int
    height: int
    cells: bytearray


def wall_count(grid: WallGrid) -> int:
    return sum(1 for c in grid.cells if c)


def parse_opg(path: Path | str) -> WallGrid:
    data = Path(path).read_bytes()
    if data[:2] != b"BM":
        raise ValueError(f"{path}: not a BMP")
    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    info_header_size = struct.unpack_from("<I", data, 14)[0]
    if info_header_size != 40:
        raise ValueError(
            f"{path}: expected a 40-byte BITMAPINFOHEADER, got {info_header_size}")
    width, height = struct.unpack_from("<2i", data, 18)
    if height < 0:
        raise ValueError(
            f"{path}: negative biHeight ({height}) — top-down BMP, but the "
            "shipped bottom-up scanline flip (module docstring) assumes "
            "positive biHeight; refusing to silently misread it")
    bpp = struct.unpack_from("<H", data, 28)[0]
    if bpp != 16:
        raise ValueError(f"{path}: expected 16 bpp, got {bpp}")
    compression = struct.unpack_from("<I", data, 30)[0]
    if compression != 0:
        raise ValueError(f"{path}: expected BI_RGB (0) compression, got {compression}")
    stride = ((width * 2 + 3) // 4) * 4
    cells = bytearray(width * height)
    for row in range(height):
        # Bottom-up source row -> top-down buffer row (== world Z).
        src = pixel_offset + (height - 1 - row) * stride
        for col in range(width):
            value = struct.unpack_from("<H", data, src + col * 2)[0]
            cells[row * width + col] = 1 if value == 1 else 0
    return WallGrid(width=width, height=height, cells=cells)
