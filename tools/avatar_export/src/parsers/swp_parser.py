"""
SWP File Parser

Parses Yogurting .swp (swap) files that drive the avatar part-swap system.

The original client swaps WHOLE MESHES by slot ID:
- Every base-body mesh gets a sequential swap-slot ID in mesh-list
  order — slot ID == base TMD material index (8 slots per gender;
  NOTE male and female orders differ, always derive from the base TMD).
- The header DefData table maps each slot to its naked default part
  ({gender}PartN.PRT) restored when nothing covers the slot.
- Each part's SwpData lists, per part mesh, the slot IDs that mesh
  REPLACES. Equipping deletes the base meshes occupying those slots
  outright — vertices are never individually hidden.
- The clone index/normal arrays are a seam weld: indices into the
  PART's own mesh whose normals are overwritten with authored
  replacement normals at equip time, matching base-body shading at
  the boundary.

File format:
- Header: DefNum (int), DefData[DefNum]
- Body: PartsNum (int), SwpData[PartsNum]
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
    swp_num: list[int]  # [MAX_MESH] - slot count per part mesh
    swp_id: list[list[int]]  # [MAX_MESH][MAX_SWP_NUM] - slots each part mesh replaces
    clone_num: list[int]  # [MAX_MESH] - weld-normal counts per part mesh
    clone_idx: list[list[int]]  # [MAX_MESH][MAX_CLONE_NUM] - PART vertex indices to re-normal
    clone_nor: list[list[tuple[float, float, float]]]  # [MAX_MESH][MAX_CLONE_NUM] - authored weld normals
    chain_num: list[int]  # [MAX_MESH]
    chain_idx: list[list[int]]  # [MAX_MESH][MAX_CLONE_NUM]
    tmd_name: str
    obj_name: str

    def get_slot_ids(self) -> list[int]:
        """All base swap-slot IDs this part replaces (union across its meshes)."""
        slots = set()
        for m in range(self.mesh_num):
            for j in range(self.swp_num[m]):
                slots.add(self.swp_id[m][j])
        return sorted(slots)

    def get_weld_normals(self, mesh_idx: int) -> list[tuple[int, tuple[float, float, float]]]:
        """(part vertex index, authored normal) pairs for one part mesh.

        Shipped data contains clone counts above the fixed per-mesh array
        size (50); the original engine indexes the contiguous 2D struct
        arrays past the row end, spilling into the next row. Replicate that
        with flat row-major indexing.
        """
        if mesh_idx >= self.mesh_num:
            return []
        n = self.clone_num[mesh_idx]
        flat_idx = [x for row in self.clone_idx for x in row]
        flat_nor = [x for row in self.clone_nor for x in row]
        base = mesh_idx * MAX_CLONE_NUM
        return [(flat_idx[base + i], flat_nor[base + i])
                for i in range(min(n, len(flat_idx) - base))]


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

        # per-mesh slot counts [MAX_MESH]
        swp_num = list(struct.unpack_from(f"<{MAX_MESH}i", data, offset))
        offset += MAX_MESH * 4

        # replaced slot IDs [MAX_MESH][MAX_SWP_NUM]
        swp_id = []
        for _ in range(MAX_MESH):
            ids = list(struct.unpack_from(f"<{MAX_SWP_NUM}i", data, offset))
            swp_id.append(ids)
            offset += MAX_SWP_NUM * 4

        # weld counts [MAX_MESH]
        clone_num = list(struct.unpack_from(f"<{MAX_MESH}i", data, offset))
        offset += MAX_MESH * 4

        # weld vertex indices [MAX_MESH][MAX_CLONE_NUM]
        clone_idx = []
        for _ in range(MAX_MESH):
            indices = list(struct.unpack_from(f"<{MAX_CLONE_NUM}i", data, offset))
            clone_idx.append(indices)
            offset += MAX_CLONE_NUM * 4

        # weld normals [MAX_MESH][MAX_CLONE_NUM] - 3 floats each:
        # authored replacement normals for the part's clone_idx vertices
        clone_nor = []
        for _ in range(MAX_MESH):
            nors = []
            for _ in range(MAX_CLONE_NUM):
                nors.append(struct.unpack_from("<3f", data, offset))
                offset += 12
            clone_nor.append(nors)

        # chain counts [MAX_MESH]
        chain_num = list(struct.unpack_from(f"<{MAX_MESH}i", data, offset))
        offset += MAX_MESH * 4

        # chain indices [MAX_MESH][MAX_CLONE_NUM]
        chain_idx = []
        for _ in range(MAX_MESH):
            indices = list(struct.unpack_from(f"<{MAX_CLONE_NUM}i", data, offset))
            chain_idx.append(indices)
            offset += MAX_CLONE_NUM * 4

        # TMD file name [MAX_NAME]
        tmd_name = self._read_string(data, offset, MAX_NAME)
        offset += MAX_NAME

        # object name [MAX_NAME]
        obj_name = self._read_string(data, offset, MAX_NAME)
        offset += MAX_NAME

        return SwpData(
            int_id=int_id,
            mesh_num=mesh_num,
            swp_num=swp_num,
            swp_id=swp_id,
            clone_num=clone_num,
            clone_idx=clone_idx,
            clone_nor=clone_nor,
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
