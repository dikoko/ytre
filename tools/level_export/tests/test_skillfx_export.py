"""Skill-effect (warp puff) export.

The two warp TMDs export through the ordinary animated-prop path but live
in an opt-in `skillfx` category: discover_props() must never see them, or
every terrain census and the static byte-identity gate shifts.
"""
import struct
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._prop_config import discover_props, discover_skill_effects
from src.exporters.prop_animation import build_animation_plan
from src.parsers.tmd_parser import TMDParser


def test_skill_effects_are_opt_in():
    cats = {c for c, _p, _t in discover_props()}
    assert "skillfx" not in cats
    fx = discover_skill_effects()
    assert [(c, p) for c, p, _t in fx] == [
        ("skillfx", "sfx_ava_spwan1_small"),
        ("skillfx", "sfx_mon_dead1_small"),
    ]


def test_warp_effect_plans_match_the_spec_table():
    """The warp effects' data expectations, asserted."""
    expected = {
        "sfx_ava_spwan1_small": {"objects": 8, "animated": 3, "fades": 3,
                                 "frames": 30.0},
        "sfx_mon_dead1_small": {"objects": 3, "animated": 2, "fades": 2,
                                "frames": 60.0},
    }
    for _cat, prop_id, tmd_path in discover_skill_effects():
        model = TMDParser().parse(tmd_path)
        plan = build_animation_plan(model, prop_id)
        want = expected[prop_id]
        assert len(model.objects) == want["objects"]
        assert len(plan.animated) == want["animated"]
        assert len(plan.visibility) == want["fades"]
        assert plan.total_frames == want["frames"]
        assert plan.fps == 30.0
        assert not plan.clips, "warp effects carry no anim ranges"
        for mat in model.materials:
            assert mat.self_illumination > 0.0, "every surface is additive"


def test_warp_effect_export_roundtrip(tmp_path):
    from scripts._export_common import embed_textures
    from scripts._prop_config import TEXTURE_SEARCH_DIRS
    from src.exporters.prop_anim_sidecar import write_sidecar
    from src.exporters.prop_exporter import export_prop

    for _cat, prop_id, tmd_path in discover_skill_effects():
        model = TMDParser().parse(tmd_path)
        glb = tmp_path / f"{prop_id}.glb"
        export_prop(model, glb, prop_id=prop_id)
        embed_textures(glb, tmd_path.parent, model,
                       texture_dirs=TEXTURE_SEARCH_DIRS)
        plan = build_animation_plan(model, prop_id)
        sidecar = write_sidecar(plan, glb)
        assert sidecar is not None

        data = glb.read_bytes()
        n = struct.unpack("<I", data[12:16])[0]
        gltf = json.loads(data[20:20 + n])
        assert len(gltf.get("animations", [])) == 1
        assert gltf["animations"][0]["name"] == "default"
        # Every material must both be emissive (additive at runtime) and
        # have its texture embedded — a missing skill texture would fall
        # back to flat white and flash as a white card in-game.
        for mat in gltf["materials"]:
            assert mat.get("emissiveFactor") == [1.0, 1.0, 1.0]
            assert "baseColorTexture" in mat["pbrMetallicRoughness"]

        side = json.loads(sidecar.read_text())
        assert set(side["clips"]) == {"default"}
        assert side["clips"]["default"]["loop"] is True  # rangeless default
        assert side["visibility"], "fade curves are the effect's core"


def test_discover_effects_full_set():
    from scripts._prop_config import discover_effects, discover_props
    effects = discover_effects()
    assert len(effects) == 352
    # opt-in: the terrain census must never see them
    assert not (set(effects) & set(discover_props()))


def test_catalog_skip_reason_covers_any_out_dir_not_just_effects():
    """Review finding (2026-08-17): the catalog skip must not be narrowly
    gated on --effects — --out-dir is unrestricted on the CLI (nothing
    stops e.g. --all --out-dir /tmp/x), and writing props.yaml against the
    default OUTPUT_MODELS while GLBs actually landed under a custom
    --out-dir would silently claim models exist in this repo's shipped
    tree that don't.
    """
    import importlib
    export_props = importlib.import_module("scripts.22_export_props")
    skip = export_props.catalog_skip_reason

    # Normal full/partial exports (no --out-dir): catalog is written.
    assert skip(effects=False, out_dir=None) is None

    # --effects always skips, --out-dir or not.
    assert skip(effects=True, out_dir=None) is not None
    assert skip(effects=True, out_dir=Path("/tmp/x")) is not None

    # The landmine this fixes: --all/--category/--ids combined with
    # --out-dir must ALSO skip, not just --effects.
    assert skip(effects=False, out_dir=Path("/tmp/x")) is not None

