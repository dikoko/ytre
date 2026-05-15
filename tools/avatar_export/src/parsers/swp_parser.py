"""
SWP File Parser

Parses Yogurting .swp (swap) files that define which base mesh vertices
are replaced by each avatar part.

File format (from GtCSwpReader):
- Header: DefNum (int), DefData[DefNum]
- Body: PartsNum (int), SwpData[PartsNum]

Each SwpData contains pCloneIdx - vertex indices in base mesh to hide when part equipped.
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path


MAX_NAME = 256
MAX_MESH = 10
MAX_SWP_NUM = 10
MAX_CLONE_NUM = 50


@dataclass
class DefData:
    """Default object data."""
    swp_id: int
    obj_name: str
    def_name: str


@dataclass
class SwpData:
    """Swap data for a single part."""
    int_id: int  # Interface/Part ID
    mesh_num: int
    swp_num: list[int]  # [MAX_MESH]
    swp_id: list[list[int]]  # [MAX_MESH][MAX_SWP_NUM]
    clone_num: list[int]  # [MAX_MESH] - vertex counts per mesh
    clone_idx: list[list[int]]  # [MAX_MESH][MAX_CLONE_NUM] - vertex indices to hide
    # clone_nor: list[list[tuple]] - normals, not needed for region mapping
    chain_num: list[int]  # [MAX_MESH]
    chain_idx: list[list[int]]  # [MAX_MESH][MAX_CLONE_NUM]
    tmd_name: str
    obj_name: str

    def get_all_clone_indices(self) -> set[int]:
        """Get all vertex indices that this part replaces (across all meshes)."""
        indices = set()
        for mesh_idx in range(min(self.mesh_num, len(self.clone_idx))):
            count = self.clone_num[mesh_idx] if mesh_idx < len(self.clone_num) else 0
            mesh_clone_idx = self.clone_idx[mesh_idx] if mesh_idx < len(self.clone_idx) else []
            for i in range(min(count, len(mesh_clone_idx))):
                idx = mesh_clone_idx[i]
                if idx >= 0:  # Valid index
                    indices.add(idx)
        return indices


@dataclass
class SWPFile:
    """Parsed SWP file."""
    def_data: list[DefData] = field(default_factory=list)
    swp_data: list[SwpData] = field(default_factory=list)

    def get_part_by_id(self, int_id: int) -> SwpData | None:
        """Get swap data by interface ID."""
        for swp in self.swp_data:
            if swp.int_id == int_id:
                return swp
        return None

    def get_parts_by_name_prefix(self, prefix: str) -> list[SwpData]:
        """Get all parts whose TMD name starts with prefix (e.g., 'male_hair')."""
        return [swp for swp in self.swp_data if swp.tmd_name.startswith(prefix)]


class SWPParser:
    """Parser for SWP files."""

    def parse(self, path: Path) -> SWPFile:
        """Parse an SWP file."""
        with open(path, "rb") as f:
            data = f.read()
        return self._parse_data(data)

    def _parse_data(self, data: bytes) -> SWPFile:
        """Parse SWP data from bytes."""
        offset = 0
        swp_file = SWPFile()

        # Read default data count
        def_num = struct.unpack_from("<i", data, offset)[0]
        offset += 4

        # Read default data entries
        for _ in range(def_num):
            def_data, offset = self._read_def_data(data, offset)
            swp_file.def_data.append(def_data)

        # Read parts count
        parts_num = struct.unpack_from("<i", data, offset)[0]
        offset += 4

        # Read swap data entries
        for _ in range(parts_num):
            swp_data, offset = self._read_swp_data(data, offset)
            swp_file.swp_data.append(swp_data)

        return swp_file

    def _read_def_data(self, data: bytes, offset: int) -> tuple[DefData, int]:
        """Read a DefData structure."""
        swp_id = struct.unpack_from("<i", data, offset)[0]
        offset += 4

        obj_name = self._read_string(data, offset, MAX_NAME)
        offset += MAX_NAME

        def_name = self._read_string(data, offset, MAX_NAME)
        offset += MAX_NAME

        return DefData(swp_id, obj_name, def_name), offset

    def _read_swp_data(self, data: bytes, offset: int) -> tuple[SwpData, int]:
        """Read a SwpData structure."""
        int_id = struct.unpack_from("<i", data, offset)[0]
        offset += 4

        mesh_num = struct.unpack_from("<i", data, offset)[0]
        offset += 4

        # pSwpNum[MAX_MESH]
        swp_num = list(struct.unpack_from(f"<{MAX_MESH}i", data, offset))
        offset += MAX_MESH * 4

        # pSwpID[MAX_MESH][MAX_SWP_NUM]
        swp_id = []
        for _ in range(MAX_MESH):
            ids = list(struct.unpack_from(f"<{MAX_SWP_NUM}i", data, offset))
            swp_id.append(ids)
            offset += MAX_SWP_NUM * 4

        # nCloneNum[MAX_MESH]
        clone_num = list(struct.unpack_from(f"<{MAX_MESH}i", data, offset))
        offset += MAX_MESH * 4

        # pCloneIdx[MAX_MESH][MAX_CLONE_NUM]
        clone_idx = []
        for _ in range(MAX_MESH):
            indices = list(struct.unpack_from(f"<{MAX_CLONE_NUM}i", data, offset))
            clone_idx.append(indices)
            offset += MAX_CLONE_NUM * 4

        # pCloneNor[MAX_MESH][MAX_CLONE_NUM] - GtVector3 (3 floats each)
        # Skip normals, we don't need them
        offset += MAX_MESH * MAX_CLONE_NUM * 12

        # pChainNum[MAX_MESH]
        chain_num = list(struct.unpack_from(f"<{MAX_MESH}i", data, offset))
        offset += MAX_MESH * 4

        # pChainIdx[MAX_MESH][MAX_CLONE_NUM]
        chain_idx = []
        for _ in range(MAX_MESH):
            indices = list(struct.unpack_from(f"<{MAX_CLONE_NUM}i", data, offset))
            chain_idx.append(indices)
            offset += MAX_CLONE_NUM * 4

        # szTMDName[MAX_NAME]
        tmd_name = self._read_string(data, offset, MAX_NAME)
        offset += MAX_NAME

        # szObjName[MAX_NAME]
        obj_name = self._read_string(data, offset, MAX_NAME)
        offset += MAX_NAME

        return SwpData(
            int_id=int_id,
            mesh_num=mesh_num,
            swp_num=swp_num,
            swp_id=swp_id,
            clone_num=clone_num,
            clone_idx=clone_idx,
            chain_num=chain_num,
            chain_idx=chain_idx,
            tmd_name=tmd_name,
            obj_name=obj_name,
        ), offset

    def _read_string(self, data: bytes, offset: int, max_len: int) -> str:
        """Read a null-terminated string from fixed-size buffer."""
        raw = data[offset:offset + max_len]
        # Find null terminator
        null_pos = raw.find(b'\x00')
        if null_pos >= 0:
            raw = raw[:null_pos]
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            # Try cp949 (Korean encoding)
            try:
                return raw.decode('cp949')
            except UnicodeDecodeError:
                return raw.decode('latin-1')
