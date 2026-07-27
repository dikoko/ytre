"""Tests for the {code}_h.bmp height decoder + RG16 PNG encoder."""
import struct
from pathlib import Path

import numpy as np
import pytest

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"


def _bmp_header(width: int, height: int, bpp: int, data_size: int,
                palette: bytes = b"") -> bytes:
    data_off = 14 + 40 + len(palette)
    file_hdr = struct.pack("<2sIHHI", b"BM", data_off + data_size, 0, 0, data_off)
    info_hdr = struct.pack("<IiiHHIIiiII", 40, width, height, 1, bpp,
                           0, data_size, 0, 0, 0, 0)
    return file_hdr + info_hdr + palette


def _make_8bpp(tmp_path: Path, values: np.ndarray) -> Path:
    """Bottom-up 8bpp palettized BMP whose pixel bytes are `values` (top-down)."""
    h, w = values.shape
    stride = (w + 3) // 4 * 4
    palette = b"".join(struct.pack("<4B", i, i, i, 0) for i in range(256))
    rows = []
    for r in range(h - 1, -1, -1):          # file stores bottom row first
        rows.append(values[r].astype(np.uint8).tobytes().ljust(stride, b"\0"))
    data = b"".join(rows)
    p = tmp_path / "test8.bmp"
    p.write_bytes(_bmp_header(w, h, 8, len(data), palette) + data)
    return p


def _make_16bpp(tmp_path: Path, values: np.ndarray) -> Path:
    """Bottom-up 16bpp BMP; per pixel the FILE stores (value>>8, value&0xFF) —
    the original client reads byte0 as the HIGH byte."""
    h, w = values.shape
    stride = (w * 2 + 3) // 4 * 4
    rows = []
    for r in range(h - 1, -1, -1):
        row = b"".join(struct.pack("<2B", int(v) >> 8, int(v) & 0xFF)
                       for v in values[r])
        rows.append(row.ljust(stride, b"\0"))
    data = b"".join(rows)
    p = tmp_path / "test16.bmp"
    p.write_bytes(_bmp_header(w, h, 16, len(data)) + data)
    return p


def test_decode_8bpp_uses_index_bytes(tmp_path):
    from src.parsers.heightmap_bmp import decode_height_bmp
    vals = np.arange(15, dtype=np.uint16).reshape(3, 5) * 7 % 256
    got = decode_height_bmp(_make_8bpp(tmp_path, vals))
    assert got.dtype == np.uint16
    assert np.array_equal(got, vals)


def test_decode_16bpp_first_byte_is_high(tmp_path):
    from src.parsers.heightmap_bmp import decode_height_bmp
    # Values crafted so a little-endian misread would differ wildly.
    vals = np.array([[0, 100, 255], [256, 300, 512]], dtype=np.uint16)
    got = decode_height_bmp(_make_16bpp(tmp_path, vals))
    assert got.dtype == np.uint16
    assert np.array_equal(got, vals)


def test_decode_16bpp_row_padding(tmp_path):
    # Width 3 -> 6 pixel bytes/row, padded to 8: the pad must be skipped.
    from src.parsers.heightmap_bmp import decode_height_bmp
    vals = (np.arange(9, dtype=np.uint16) * 41).reshape(3, 3)
    got = decode_height_bmp(_make_16bpp(tmp_path, vals))
    assert np.array_equal(got, vals)


def test_decode_rejects_other_depths(tmp_path):
    from src.parsers.heightmap_bmp import decode_height_bmp
    data = b"\0" * 12
    p = tmp_path / "test24.bmp"
    p.write_bytes(_bmp_header(2, 2, 24, len(data)) + data)
    with pytest.raises(ValueError):
        decode_height_bmp(p)


def test_png_roundtrip_rg_encoding(tmp_path):
    from PIL import Image
    from src.parsers.heightmap_bmp import decode_height_bmp, write_height_png
    vals = np.array([[0, 155, 292], [1000, 65535, 42]], dtype=np.uint16)
    png = tmp_path / "out.png"
    write_height_png(vals, png)
    arr = np.asarray(Image.open(png).convert("RGB")).astype(np.uint16)
    decoded = (arr[:, :, 0] << 8) | arr[:, :, 1]   # R=high, G=low (viewer decode)
    assert np.array_equal(decoded, vals)


def test_sf001001_matches_shipped_8bpp_range():
    # Real 8bpp map: decode must stay in byte range and produce the known
    # sane height window once h = v*0.1 - 10 is applied.
    from src.parsers.heightmap_bmp import decode_height_bmp
    vals = decode_height_bmp(MAP_DIR / "SF001001" / "SF001001_h.bmp")
    assert vals.shape == (150, 150)
    assert vals.max() <= 255
    h = vals.astype(np.float64) * 0.1 - 10.0
    assert -10.0 <= h.min() and h.max() < 30.0


def test_sf002001_16bpp_heights_sane():
    # Real 16bpp map (the bug this module fixes): correct byte order gives
    # heights in a plausible window; a little-endian misread lands ~6500.
    from src.parsers.heightmap_bmp import decode_height_bmp
    vals = decode_height_bmp(MAP_DIR / "SF002001" / "SF002001_h.bmp")
    assert vals.shape == (250, 250)
    h = vals.astype(np.float64) * 0.1 - 10.0
    assert -10.0 <= h.min() and h.max() < 30.0
