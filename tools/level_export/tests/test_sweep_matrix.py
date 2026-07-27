"""Tests for the sweep matrix renderer (scripts/40_sweep_maps.py)."""
import importlib

sweep = importlib.import_module("scripts.40_sweep_maps")


RESULTS = {
    "SF001001": {
        "status": "ok",
        "blockers": [],
        "models_resolved": 76,
        "models_total": 77,
        "l1_violations": 0,
        "seam_topdown": 0.987,
        "seam_closeup": 1.341,
        "worst_prop_dark_ratio": 0.31,
        "export_seconds": 42.0,
    },
    "SF001002": {
        "status": "blocked",
        "blockers": ["point_lights"],
    },
    "FD000501": {
        "status": "export_failed",
        "blockers": [],
        "error": "31_export_terrain: KeyError: 'combo_999'",
    },
}


def test_matrix_has_summary_counts():
    md = sweep.render_matrix(RESULTS)
    assert "3 maps" in md
    assert "ok: 1" in md
    assert "blocked: 1" in md
    assert "export_failed: 1" in md


def test_matrix_has_per_map_rows():
    md = sweep.render_matrix(RESULTS)
    assert "| SF001001 | ok |" in md
    assert "point_lights" in md
    assert "KeyError" in md


def test_matrix_blocker_histogram():
    md = sweep.render_matrix(RESULTS)
    assert "point_lights: 1" in md


def test_summarize_scores_extracts_l2():
    scores = {
        "l1": {"cvs_invariants": {"violations": []},
               "texture_resolution": {"violations": []}},
        "l2": {
            "terrain_seam_score": 0.987,
            "terrain_closeup_seam_score": 1.341,
            "props": [
                {"name": "a", "dark_ratio": 0.1, "magenta_ratio": 0.0},
                {"name": "b", "dark_ratio": 0.4, "magenta_ratio": 0.0},
            ],
        },
        "l2_skipped": False,
    }
    s = sweep.summarize_scores(scores)
    assert s["seam_topdown"] == 0.987
    assert s["seam_closeup"] == 1.341
    assert s["worst_prop_dark_ratio"] == 0.4
    assert s["l1_violations"] == 0
