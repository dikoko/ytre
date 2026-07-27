"""
OCG Parser — Object Category file.

Maps numeric model IDs to prop filenames.
Binary format:
  Header: int32 version (20040114) + uint16 count (no padding)
  Entries: count × (int32 m_bBillboard + char[256] filename)

  Note: m_bBillboard is a 4-byte BOOL (int); each record is that flag
  followed by a fixed 256-char filename buffer.
"""

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OCGEntry:
    index: int
    billboard: bool  # m_bBillboard from C++ OCG struct, converted from int BOOL
    filename: str
    category: str
    model_name: str


class OCGParser:
    EXPECTED_VERSION = 20040114
    ENTRY_SIZE = 260

    def parse(self, path: Path | str) -> list[OCGEntry]:
        path = Path(path)
        with open(path, "rb") as f:
            data = f.read()

        version, count = struct.unpack_from("<IH", data, 0)
        if version != self.EXPECTED_VERSION:
            raise ValueError(f"Unexpected OCG version: {version} (expected {self.EXPECTED_VERSION})")

        entries = []
        offset = 6

        for i in range(count):
            billboard_raw = struct.unpack_from("<I", data, offset)[0]
            billboard = bool(billboard_raw)
            raw_name = data[offset + 4:offset + 260]
            filename = raw_name.split(b"\x00", 1)[0].decode("ascii", errors="replace")

            parts = filename.replace("/", "\\").split("\\")
            if len(parts) >= 2:
                category = parts[-2].lower()
                model_name = parts[-1]
            else:
                category = ""
                model_name = filename

            entries.append(OCGEntry(
                index=i, billboard=billboard, filename=filename,
                category=category, model_name=model_name,
            ))
            offset += self.ENTRY_SIZE

        return entries
