"""Tests for OCG parser — model ID to filename index."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
SF001001_OCG = MAP_DIR / "SF001001" / "SF001001.ocg"


def test_ocg_parser_reads_file():
    from src.parsers.ocg_parser import OCGParser
    entries = OCGParser().parse(SF001001_OCG)
    assert len(entries) == 84, f"Expected 84 entries, got {len(entries)}"


def test_ocg_first_entry_is_structure():
    from src.parsers.ocg_parser import OCGParser
    entries = OCGParser().parse(SF001001_OCG)
    assert entries[0].filename == "Structure\\s_SEhall"
    assert entries[0].category == "structure"
    assert entries[0].model_name == "s_SEhall"


def test_ocg_entries_have_valid_categories():
    from src.parsers.ocg_parser import OCGParser
    entries = OCGParser().parse(SF001001_OCG)
    for entry in entries:
        assert entry.category, f"Entry {entry.index} has empty category"
        assert entry.model_name, f"Entry {entry.index} has empty model_name"


def test_ocg_version():
    from src.parsers.ocg_parser import OCGParser
    entries = OCGParser().parse(SF001001_OCG)
    assert len(entries) > 0


def test_ocg_entry_billboard_is_bool():
    """Billboard field should be bool, not int."""
    from src.parsers.ocg_parser import OCGParser
    entries = OCGParser().parse(SF001001_OCG)
    assert isinstance(entries[0].billboard, bool)


def test_ocg_billboard_flags_exist():
    """SF001001 has 4 billboard entries (trees)."""
    from src.parsers.ocg_parser import OCGParser
    entries = OCGParser().parse(SF001001_OCG)
    billboard_count = sum(1 for e in entries if e.billboard)
    # Measured: 4 entries have billboard=True in SF001001
    assert billboard_count == 4, f"Expected 4 billboard entries, got {billboard_count}"
