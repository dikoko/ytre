"""Tests for MLIB parser."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
MLIB_PATH = AVATAR_IRD / "motion" / "male" / "male.mlib"


def test_parse_male_mlib():
    from src.parsers.mlib_parser import MLIBParser
    parser = MLIBParser()
    mlib = parser.parse(MLIB_PATH)
    assert mlib is not None


def test_male_mlib_has_55_bones():
    # MLIB has 55 bones, TMD has 54 (MLIB includes extra root)
    from src.parsers.mlib_parser import MLIBParser
    parser = MLIBParser()
    mlib = parser.parse(MLIB_PATH)
    assert len(mlib.bones) == 55


def test_male_mlib_has_223_motions():
    from src.parsers.mlib_parser import MLIBParser
    parser = MLIBParser()
    mlib = parser.parse(MLIB_PATH)
    assert len(mlib.motions) == 223


def test_basic_pick_exists():
    from src.parsers.mlib_parser import MLIBParser
    parser = MLIBParser()
    mlib = parser.parse(MLIB_PATH)
    motion = mlib.get_motion_by_name("male_basic_pick")
    assert motion is not None
    assert motion.frame_count > 0
