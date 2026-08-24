"""Tests for skl_parser — skill script (.skl) decoder."""
import collections
import struct
from pathlib import Path

import pytest

from src.parsers.skl_parser import _Archive, _parse_cmd_base, parse_skl

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
SKILL_DIR = YTREF_ROOT / "models" / "raw" / "Skill.IRD" / "Skill"

WARP = {
    "sk100001": ("sfx_ava_spwan1_small.TMD", "etc_warp_outdoor.wav"),
    "sk100002": ("sfx_mon_dead1_small.TMD", "etc_warp_outdoor.wav"),
    "sk100003": ("sfx_mon_dead1_small.TMD", "etc_warp_indoor.wav"),
    "sk100004": ("sfx_ava_spwan1_small.TMD", "etc_warp_indoor.wav"),
}


@pytest.mark.parametrize("code,expect", WARP.items())
def test_warp_skill_decodes(code, expect):
    tmd_name, wav_name = expect
    skill = parse_skl(SKILL_DIR / f"{code}.skl")
    assert skill.skill_id == int(code[2:])
    assert skill.fps == 30.0
    # The skl's own frame budget: 60 in all four warp files (the referenced
    # TMD assets have their own internal frame counts — different files).
    assert skill.total_frames == 60
    # Animation-level end-notify hook, byte-identical across the four.
    assert skill.notify_frame == 29
    kinds = {t.component.kind for t in skill.tracks}
    assert {"tmd", "motion", "sound"} <= kinds
    tmd = next(t for t in skill.tracks if t.component.kind == "tmd")
    assert tmd.component.name == tmd_name
    snd = next(t for t in skill.tracks if t.component.kind == "sound")
    assert snd.component.name == wav_name


def test_motion_track_names_preview_mlib():
    skill = parse_skl(SKILL_DIR / "sk100001.skl")
    mot = next(t for t in skill.tracks if t.component.kind == "motion")
    assert "female" in mot.component.name.lower()


def test_cmd_base_schema3_reads_two_separate_inherit_ints():
    """A schema-3 base command stores TWO separate inherit ints (one for
    position, the next for rotation) before offset_y — 13 bytes after
    base_bone, not 9. inherit_pos=False/inherit_rot=True below
    are deliberately different so a parser that collapses them into one
    shared value, or drops the second int, cannot coincidentally pass.
    """
    payload = (
        b"\x00"  # base_character source byte (schema 3 < 5: char, upgraded)
        b"\x05"  # base_bone
        + struct.pack("<i", 0)  # inherit_pos int -> False
        + struct.pack("<i", 1)  # inherit_rot int -> True (SEPARATE field)
        + struct.pack("<f", 2.5)  # offset_y
        + b"\xab"  # sentinel: must NOT be consumed
    )
    ar = _Archive(payload)
    start = ar.pos
    params = _parse_cmd_base(ar, 3)

    assert params["base_bone"] == 5
    assert params["inherit_pos"] is False
    assert params["inherit_rot"] is True
    assert params["offset"] == (0.0, 2.5, 0.0)
    assert params["rot"] == (0.0, 0.0, 0.0)
    # Exactly 14 bytes consumed (1 base_character + 1 base_bone + 4 + 4 +
    # 4) — the sentinel byte must be left untouched, proving no
    # misalignment leaked into whatever follows this command in a real
    # file.
    assert ar.pos - start == 14


def _fleet():
    return sorted(SKILL_DIR.glob("*.skl"))


def test_fleet_parses_clean():
    assert len(_fleet()) == 742
    census = collections.Counter()
    for f in _fleet():
        skill = parse_skl(f)                      # no exception = clean
        for t in skill.tracks:
            census[t.component.kind] += 1
            assert "raw" not in t.component.params, f"{f.name} undecoded"
            for c in t.commands:
                assert 0 <= c.frame <= skill.total_frames, \
                    f"{f.name}: command frame {c.frame} outside 0..{skill.total_frames}"
    # Occurrence counts pinned from a fleet byte-scan census.
    # NOTE: the byte-scan counted FILES CONTAINING each class; a file can
    # carry several tracks of one kind, so per-track counts may be >=.
    # "path" is NOT here: the byte-level decode shows paths are
    # animation-level data (no component type exists for them), counted
    # separately below.
    for kind, minimum in [("tmd", 707), ("motion", 614), ("sfx", 373),
                          ("sound", 339), ("color", 285), ("camera", 117),
                          ("sword_trace", 34)]:
        assert census[kind] >= minimum, f"{kind}: {census[kind]} < {minimum}"
    files_with_paths = sum(1 for f in _fleet() if parse_skl(f).paths)
    assert files_with_paths >= 50


def test_unknown_class_is_loud(tmp_path):
    bad = tmp_path / "bad.skl"
    bad.write_bytes(bytes.fromhex("ffff0100" + "0700") + b"LsCFake" + b"\x00" * 16)
    with pytest.raises(ValueError, match="LsCFake"):
        parse_skl(bad)


def test_unknown_component_class_mid_archive_is_loud(tmp_path):
    """Component-level unknown-class check (_parse_track), hit from
    *inside* the track list on a real fixture — not just the root-level
    check test_unknown_class_is_loud already covers. Swaps the literal
    ASCII class name bytes of sk100001.skl's first ("new class") component
    tag for a same-length, unrecognized name, so every length-prefixed
    field (namelen, and everything after it) stays correctly aligned and
    only the name lookup fails.

    Offsets pinned by a one-off byte scan of sk100001.skl: offset 34 is
    where this component's 0xFFFF "new class" tag begins (the `start`
    _parse_track reports in its ValueError); the literal name "LsCMotion"
    (9 ASCII bytes, CLASS_KINDS-recognized) sits at 40..49.
    """
    data = bytearray((SKILL_DIR / "sk100001.skl").read_bytes())
    assert data[40:49] == b"LsCMotion"
    data[40:49] = b"LsCBogus9"  # same length (9), not in CLASS_KINDS
    bad = tmp_path / "bad_component.skl"
    bad.write_bytes(bytes(data))
    with pytest.raises(ValueError) as exc_info:
        parse_skl(bad)
    msg = str(exc_info.value)
    assert "LsCBogus9" in msg
    assert "34" in msg  # offset of the mutated tag's 0xFFFF marker


def test_unknown_command_class_is_loud(tmp_path):
    """Command-level unknown-class check (_parse_command) — same
    same-length-swap technique as the component-level test above, applied
    to sk100001.skl's first command tag instead.

    Offsets pinned the same way: offset 85 is the command's 0xFFFF tag
    start; the literal name "LsCCmdPlay" (10 ASCII bytes, COMMAND_KINDS-
    recognized) sits at 91..101.
    """
    data = bytearray((SKILL_DIR / "sk100001.skl").read_bytes())
    assert data[91:101] == b"LsCCmdPlay"
    data[91:101] = b"LsCCmdFake"  # same length (10), not in COMMAND_KINDS
    bad = tmp_path / "bad_command.skl"
    bad.write_bytes(bytes(data))
    with pytest.raises(ValueError) as exc_info:
        parse_skl(bad)
    msg = str(exc_info.value)
    assert "LsCCmdFake" in msg
    assert "85" in msg  # offset of the mutated tag's 0xFFFF marker


def test_trailing_bytes_is_loud(tmp_path):
    """The parser's ValueError contract covers unknown class tags OR
    trailing bytes — this covers the trailing-bytes half by taking a
    real, fully-valid warp fixture and appending one stray byte after
    its last legitimately-consumed byte."""
    original = (SKILL_DIR / "sk100001.skl").read_bytes()
    bad = tmp_path / "trailing.skl"
    bad.write_bytes(original + b"\x00")
    with pytest.raises(ValueError) as exc_info:
        parse_skl(bad)
    msg = str(exc_info.value)
    assert bad.name in msg
    assert str(len(original)) in msg  # offset where the stray byte sits
    assert "trailing" in msg.lower()
