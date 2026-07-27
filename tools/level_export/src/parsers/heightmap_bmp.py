"""Height BMP ({code}_h.bmp) decoder + viewer-PNG encoder.

The original client's heightmap loader supports two shipped layouts:

- 8bpp palettized (303 maps): the height value is the raw palette INDEX
  byte — the palette itself is never consulted.
- 16bpp (22 maps, e.g. SF002001): two raw bytes per pixel, and the FIRST
  byte in the file is the HIGH byte: value = (byte0 << 8) | byte1. A plain
  little-endian uint16 read gives garbage in the thousands (verified
  empirically: correct order matches navmesh cell heights to ~0.5 m
  median; swapped order is off by ~2600 m).

Both then apply h = value * 0.1 - 10.0. The original loader stores rows top-down
(flipping the BMP's bottom-up file order), so row 0 here is grid row 0 —
the same orientation PIL produced for the 8bpp maps that shipped first.

The viewer PNG packs the 16-bit value into RGB8: R = value >> 8,
G = value & 0xFF, B = 0 (8bpp maps simply have R = 0). Decoded by
height_service.gd / terrain_loader.gd as (R*256 + G) * 0.1 - 10.0.
Godot's PNG loader reduces 16-bit-per-channel PNGs to 8-bit, so a
grayscale 16-bit PNG cannot carry these heights — hence the RG split.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

HEIGHT_SCALE = 0.1
HEIGHT_OFFSET = -10.0


def decode_height_bmp(path: Path | str) -> np.ndarray:
    """Decode {code}_h.bmp to a (rows, cols) uint16 array, top-down rows."""
    data = Path(path).read_bytes()
    if data[:2] != b"BM":
        raise ValueError(f"{path}: not a BMP file")
    data_off = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    bpp = struct.unpack_from("<H", data, 28)[0]
    if width <= 0 or height <= 0:
        raise ValueError(f"{path}: unsupported dimensions {width}x{height}")
    if bpp == 8:
        pixbytes = 1
    elif bpp == 16:
        pixbytes = 2
    else:
        # The original loader only decodes 8/16bpp height maps.
        raise ValueError(f"{path}: unsupported height BMP depth {bpp}bpp")
    stride = (width * pixbytes + 3) // 4 * 4
    rows = np.frombuffer(
        data, dtype=np.uint8, count=height * stride, offset=data_off
    ).reshape(height, stride)[:, : width * pixbytes]
    rows = rows[::-1]  # BMP files are bottom-up; the original loader flips to top-down
    if bpp == 8:
        return rows.astype(np.uint16)
    pairs = rows.reshape(height, width, 2).astype(np.uint16)
    return (pairs[:, :, 0] << 8) | pairs[:, :, 1]  # first byte is the HIGH byte


def write_height_png(values: np.ndarray, path: Path | str) -> None:
    """Write the viewer heightmap PNG: R = high byte, G = low byte, B = 0."""
    from PIL import Image

    v = np.ascontiguousarray(values, dtype=np.uint16)
    rgb = np.zeros((*v.shape, 3), dtype=np.uint8)
    rgb[:, :, 0] = v >> 8
    rgb[:, :, 1] = v & 0xFF
    Image.fromarray(rgb, "RGB").save(str(path))


def heights_from_values(values: np.ndarray) -> np.ndarray:
    """Apply the original height formula h = v * 0.1 - 10.0."""
    return values.astype(np.float64) * HEIGHT_SCALE + HEIGHT_OFFSET
