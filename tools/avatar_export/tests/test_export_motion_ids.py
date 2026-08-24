"""motion_ids.json: motion id -> imported GLB clip name, per gender.
Clip naming rule (the animation exporter): motion.name.replace("male_","")
— which also turns 'female_' into 'fe' (matches the shipped GLBs; keep it).
Godot's GLB importer dedupes duplicate animation names by appending
2,3,...; exactly one duplicate exists per gender (motions 40002/40030
truncate identically in the MLIB) — verified against the imported GLBs."""
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLIENT = ROOT.parent.parent / "ytavatar" / "client"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "47_export_motion_ids.py"), *args],
        capture_output=True, text=True, cwd=ROOT)


def _glb_anim_names(path: Path) -> list[str]:
    b = path.read_bytes()
    ln = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + ln])
    return [a["name"] for a in doc.get("animations", [])]


def test_motion_ids(tmp_path):
    r = _run("--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    m = json.loads((tmp_path / "motion_ids.json").read_text())
    assert m["version"] == 1
    for gender in ("female", "male"):
        assert len(m[gender]) == 223
    assert m["female"]["10101"] == "feblade_stick_attack1"
    assert m["male"]["10101"] == "blade_stick_attack1"
    assert m["female"]["50111"] == "femura_classic_stand"
    # the one collision: second occurrence gets Godot's dedupe suffix "2"
    assert m["female"]["40002"] == "feglorb_matial_hoyunjigiknukcle_ho"
    assert m["female"]["40030"] == "feglorb_matial_hoyunjigiknukcle_ho2"
    assert m["male"]["40030"] == "glorb_matial_hoyunjigiknukcle_hoyu2"
    # same id sets in both genders (that is how one .skl serves both)
    assert set(m["female"]) == set(m["male"])


ROLE_ACTOR = 0x100  # actor-role bit in character_type — skill_player.gd's ROLE_ACTOR


def test_skill_motion_ids_exist_in_both_genders():
    """Catalog invariant: every
    avatar motion_id referenced by an ACTOR-role skills.json motion track
    (character_type & 0x100, track name is an avatar mlib — female.mlib/
    female.MLIB/male.mlib, never a monster ct*/cn*.mlib, which this test
    exempts by name) must resolve in BOTH genders' motion_ids.json — that
    is how one .skl serves both genders at runtime (skill_player.gd's
    play_motion_id is gender-aware and looks up the SAME id in whichever
    gender is currently equipped). Reads the committed catalog files
    directly (not the exporter script) since this pins the SHIPPED data,
    not a regeneration. Expected to pass today: only monster motion ids
    are ever absent from motion_ids.json, and those tracks always name a
    ct*/cn*.mlib, which never reaches the assertion below."""
    skills = json.loads((CLIENT / "assets" / "effects" / "skills.json").read_text())["skills"]
    motion_ids = json.loads((CLIENT / "assets" / "avatars" / "base" / "motion_ids.json").read_text())
    checked = 0
    for code, entry in skills.items():
        for track in entry.get("tracks", []):
            if track.get("kind") != "motion":
                continue
            name = str(track.get("name", ""))
            if not (name.lower().startswith("female") or name.lower().startswith("male")):
                continue  # monster ct*/cn*.mlib track — exempt
            params = track.get("params", {})
            if int(params.get("character_type", 0)) & ROLE_ACTOR == 0:
                continue  # target/other role — not played by an ACTOR
            mid = str(params.get("motion_id", -1))
            assert mid in motion_ids["female"], (code, name, mid, "missing in female")
            assert mid in motion_ids["male"], (code, name, mid, "missing in male")
            checked += 1
    # Sanity: the name/role filters above didn't accidentally skip every
    # track — the shipped catalog has 163 matching actor-role avatar-mlib
    # motion tracks as of 2026-08-22.
    assert checked > 0


def test_motion_ids_match_shipped_glbs(tmp_path):
    r = _run("--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    m = json.loads((tmp_path / "motion_ids.json").read_text())
    # Every mapped name must exist in the raw GLB animation list, modulo the
    # dedupe suffix (raw GLB carries the duplicate verbatim; Godot renames
    # only on import).
    for gender, glb in [("female", "female_base_materials.glb"),
                        ("male", "male_base_materials.glb")]:
        names = _glb_anim_names(CLIENT / "assets" / "avatars" / "base" / glb)
        for mid, clip in m[gender].items():
            base = clip[:-1] if clip.endswith("2") and clip[:-1] in names else clip
            assert base in names, (gender, mid, clip)
