"""
QQQ Parser — Quadtree object placement file.

Stores 3D object positions, rotations, and model references for game maps.

Binary format (from QuadTree.h):
  Header: 56 bytes (ident, version, 6 × lump offsets)
  LUMP_MODEL (0): 80-byte entries (shadow flags + 4x4 matrix + IDs)
  LUMP_SURFACE (1): skipped
  LUMP_PORTAL (2): 68-byte entries (4x4 matrix + IDs, no shadow flags)
  LUMP_TREEINFO (3): 20 bytes (quadtree metadata)
  LUMP_NODEINFO (4): skipped
  LUMP_TRIGGEROBJ (5): 108-byte entries (interactive objects)
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MapObject:
    unique_id: int
    model_id: int
    transform: list[float]
    shadow_self: bool = False
    shadow_receive: bool = False
    trans_type: int = 0


@dataclass
class MapPortal:
    unique_id: int
    model_id: int
    transform: list[float]


@dataclass
class TreeInfo:
    max_level: int
    center: tuple[float, float]
    extents: tuple[float, float]


@dataclass
class MapData:
    objects: list[MapObject] = field(default_factory=list)
    portals: list[MapPortal] = field(default_factory=list)
    triggers: list[MapObject] = field(default_factory=list)
    tree_info: TreeInfo | None = None


class QQQParser:
    LUMP_MODEL = 0
    LUMP_PORTAL = 2
    LUMP_TREEINFO = 3
    LUMP_TRIGGEROBJ = 5

    MODEL_SIZE = 80
    PORTAL_SIZE = 68
    TREEINFO_SIZE = 20
    TRIGGER_SIZE = 108

    def parse(self, path: Path | str) -> MapData:
        path = Path(path)
        with open(path, "rb") as f:
            data = f.read()

        lumps = []
        for i in range(6):
            offset_pos = 8 + i * 8
            ofs, size = struct.unpack_from("<II", data, offset_pos)
            lumps.append((ofs, size))

        result = MapData()

        ofs, size = lumps[self.LUMP_MODEL]
        count = size // self.MODEL_SIZE
        for i in range(count):
            result.objects.append(self._parse_model(data, ofs + i * self.MODEL_SIZE))

        ofs, size = lumps[self.LUMP_PORTAL]
        count = size // self.PORTAL_SIZE
        for i in range(count):
            result.portals.append(self._parse_portal(data, ofs + i * self.PORTAL_SIZE))

        ofs, size = lumps[self.LUMP_TREEINFO]
        if size >= self.TREEINFO_SIZE:
            result.tree_info = self._parse_tree_info(data, ofs)

        ofs, size = lumps[self.LUMP_TRIGGEROBJ]
        count = size // self.TRIGGER_SIZE
        for i in range(count):
            result.triggers.append(self._parse_trigger(data, ofs + i * self.TRIGGER_SIZE))

        return result

    def _parse_model(self, data: bytes, offset: int) -> MapObject:
        selfshadow, receiveshadow, transtype = struct.unpack_from("<III", data, offset)
        mat = list(struct.unpack_from("<16f", data, offset + 12))
        unique_id, model_id = struct.unpack_from("<HH", data, offset + 76)
        return MapObject(
            unique_id=unique_id, model_id=model_id, transform=mat,
            shadow_self=bool(selfshadow), shadow_receive=bool(receiveshadow),
            trans_type=transtype,
        )

    def _parse_portal(self, data: bytes, offset: int) -> MapPortal:
        mat = list(struct.unpack_from("<16f", data, offset))
        unique_id, model_id = struct.unpack_from("<HH", data, offset + 64)
        return MapPortal(unique_id=unique_id, model_id=model_id, transform=mat)

    def _parse_tree_info(self, data: bytes, offset: int) -> TreeInfo:
        max_level = struct.unpack_from("<I", data, offset)[0]
        cx, cz = struct.unpack_from("<ff", data, offset + 4)
        ex, ez = struct.unpack_from("<ff", data, offset + 12)
        return TreeInfo(max_level=max_level, center=(cx, cz), extents=(ex, ez))

    def _parse_trigger(self, data: bytes, offset: int) -> MapObject:
        return self._parse_model(data, offset)
