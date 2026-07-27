"""
TCG Parser — Tile registry binary format.

Binary format (reverse-engineered):
  Header: uint32 tile_set_count
  TileSets: tile_set_count entries:
    uint32 set_id + char[256] set_name +
    15 × TileData (uint32 index + uint32 opt_count +
                    opt_count × (uint16 opt_id + char[256] texture_name))
  Palettes: uint32 palette_count
    palette_count entries:
      uint32 pal_id + char[256] pal_name + uint32 entry_count +
      entry_count × uint32 tile_set_ids
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path

_MAX_FNAME = 256
_TILEREG_TILESETNUM = 15


@dataclass
class TileSet:
    set_id: int
    name: str
    tiles: dict[tuple[int, int], str] = field(default_factory=dict)


@dataclass
class TilePalette:
    pal_id: int
    name: str
    entry_ids: list[int] = field(default_factory=list)


@dataclass
class RegistryData:
    tile_sets: dict[int, TileSet] = field(default_factory=dict)
    palettes: list[TilePalette] = field(default_factory=list)


def _read_cstr(data: bytes, offset: int, length: int) -> str:
    raw = data[offset:offset + length]
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")


class TCGParser:
    def parse(self, path: Path | str) -> RegistryData:
        path = Path(path)
        with open(path, "rb") as f:
            data = f.read()

        offset = 0
        tile_set_count = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        tile_sets: dict[int, TileSet] = {}

        for _ in range(tile_set_count):
            set_id = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            set_name = _read_cstr(data, offset, _MAX_FNAME)
            offset += _MAX_FNAME

            ts = TileSet(set_id=set_id, name=set_name)

            for _ in range(_TILEREG_TILESETNUM):
                tile_index = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                opt_count = struct.unpack_from("<I", data, offset)[0]
                offset += 4

                for _ in range(opt_count):
                    opt_id = struct.unpack_from("<H", data, offset)[0]
                    offset += 2
                    tex_name = _read_cstr(data, offset, _MAX_FNAME)
                    offset += _MAX_FNAME

                    if tile_index > 0:
                        ts.tiles[(tile_index, opt_id)] = tex_name

            tile_sets[set_id] = ts

        # Palettes section
        palettes: list[TilePalette] = []
        if offset < len(data):
            pal_count = struct.unpack_from("<I", data, offset)[0]
            offset += 4

            for _ in range(pal_count):
                pal_id = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                pal_name = _read_cstr(data, offset, _MAX_FNAME)
                offset += _MAX_FNAME
                entry_count = struct.unpack_from("<I", data, offset)[0]
                offset += 4

                entry_ids = []
                for _ in range(entry_count):
                    eid = struct.unpack_from("<I", data, offset)[0]
                    entry_ids.append(eid)
                    offset += 4

                palettes.append(TilePalette(
                    pal_id=pal_id, name=pal_name, entry_ids=entry_ids,
                ))

        return RegistryData(tile_sets=tile_sets, palettes=palettes)
