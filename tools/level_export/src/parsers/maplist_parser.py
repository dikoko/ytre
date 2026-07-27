"""Maplist parser — maplist.lst, the map-code → display-name table.

403 × 108-byte fixed records, no header:
  int32  mapid
  char   mapname[34]    ASCII map code ("SF001001"), NUL-padded
  WCHAR  levelname[34]  UTF-16LE Korean display name, NUL-padded
  2 bytes tail padding (0xCC in the shipped file)
"""
import struct
from dataclasses import dataclass
from pathlib import Path

RECORD_SIZE = 108


@dataclass
class MapEntry:
    map_id: int
    code: str
    name_ko: str


def parse_maplist(path: Path | str) -> list[MapEntry]:
    data = Path(path).read_bytes()
    if len(data) % RECORD_SIZE:
        raise ValueError(f"maplist size {len(data)} not a multiple of {RECORD_SIZE}")
    entries: list[MapEntry] = []
    for off in range(0, len(data), RECORD_SIZE):
        map_id = struct.unpack_from("<i", data, off)[0]
        code = data[off + 4 : off + 38].split(b"\x00")[0].decode("ascii")
        name = data[off + 38 : off + 106].decode("utf-16-le").split("\x00")[0]
        entries.append(MapEntry(map_id=map_id, code=code, name_ko=name))
    return entries
