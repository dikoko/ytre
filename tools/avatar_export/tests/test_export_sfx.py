"""Tests for 48_export_sfx — sfx.json + textures + random tables exporter."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def _run(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "48_export_sfx.py"), *args],
        capture_output=True, text=True, cwd=ROOT)


def test_export_writes_catalog_textures_and_tables(tmp_path):
    parity = tmp_path / "parity.json"
    r = _run("--out-dir", str(tmp_path), "--parity-out", str(parity))
    assert r.returncode == 0, r.stderr
    cat = json.loads((tmp_path / "effects" / "sfx.json").read_text())
    assert cat["version"] == 1
    assert cat["errors"] == {}
    effects = cat["effects"]
    assert len(effects) == 154
    red = effects["sfx_common_particledot1_red"]
    assert red["kind"] == "emitter_polygon"
    assert red["additive"] is True
    assert red["total_time"] == 1.0
    assert red["textures"] == ["sfx_common_particledot1_red.tga"]
    assert red["missing_textures"] == []
    assert red["gravity"]["points"][0] == pytest.approx([0.0, 10.0, 0.0, 10.0], abs=1e-4)
    assert len(red["dynamic_state"]) == 8
    assert "width" not in red
    bb = effects["sfx_common_condition_aging_billboard"]
    assert bb["kind"] == "billboard" and bb["alignment"] == 0
    assert bb["textures"] == ["sfx_common_condition_aging3.tga",
                              "sfx_common_condition_aging1.tga"]
    assert "gravity" not in bb
    # every referenced texture resolved and was copied lowercase
    tex_dir = tmp_path / "effects" / "sfx_textures"
    for e in effects.values():
        assert e["missing_textures"] == []
        for t in e["textures"]:
            assert t == t.lower()
            assert (tex_dir / t).exists()
    assert (tex_dir / ".gdignore").exists()
    assert len(list(tex_dir.glob("*.tga"))) == 143   # all shipped, orphans included
    # random tables
    rnd = json.loads((tmp_path / "effects" / "sfx_random.json").read_text())
    assert rnd["version"] == 1
    assert len(rnd["ints"]) == 10000 and len(rnd["floats"]) == 10000
    assert rnd["ints"][0] == 26513
    # parity fixture
    p = json.loads(parity.read_text())
    assert p["version"] == 1 and len(p["spawn"]) == 20
    assert "154 effects" in r.stdout and "errors: 0" in r.stdout


def test_dry_run_writes_nothing(tmp_path):
    r = _run("--out-dir", str(tmp_path), "--parity-out", str(tmp_path / "p.json"),
             "--dry-run")
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "effects").exists()
    assert not (tmp_path / "p.json").exists()


# The scripts directory is not a package — import the module by path.
def _load_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "export_sfx", ROOT / "scripts" / "48_export_sfx.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_texture_lookup_is_case_insensitive():
    mod = _load_module()
    index = mod.texture_index()
    # 9 shipped textures carry an uppercase .TGA extension; a .sfd may
    # reference them in any case — resolution ignores case, copies lowercase.
    uppercase = [k for k, v in index.items() if v.name != v.name.lower()]
    assert len(uppercase) == 9
    assert mod.resolve_texture("SFX_COMMON_PARTICLEDOT1_RED.TGA", index) is not None
    assert mod.resolve_texture("nope.tga", index) is None
