import json
from mapeval.report import write_report


def test_write_report(tmp_path):
    scores = {
        "map": "SF001001", "timestamp": "20260712-120000",
        "l1": {"cvs_invariants": {"violations": []},
               "det_census": {"total": 901, "negative": 0, "violations": []},
               "texture_resolution": {"unresolved": [], "violations": []}},
        "l2": {"terrain_seam_score": 1.4,
               "props": [{"name": "a_SEtrack01", "dark_ratio": 0.9, "magenta_ratio": 0.0},
                          {"name": "a_bookcase01", "dark_ratio": 0.01, "magenta_ratio": 0.0}]},
        "l2_skipped": False,
    }
    out = tmp_path / "run"
    out.mkdir()
    write_report(scores, out, previous=None)
    assert (out / "scores.json").exists()
    html = (out / "report.html").read_text()
    assert "a_SEtrack01" in html           # worst prop listed
    assert json.loads((out / "scores.json").read_text())["map"] == "SF001001"


def test_write_report_shows_delta_vs_previous(tmp_path):
    prev = {"l2": {"terrain_seam_score": 2.0, "props": []}}
    scores = {"map": "M", "timestamp": "t", "l1": {}, "l2": {"terrain_seam_score": 1.0, "props": []}, "l2_skipped": False}
    out = tmp_path / "run"; out.mkdir()
    write_report(scores, out, previous=prev)
    assert "2.0" in (out / "report.html").read_text()  # previous value shown


def test_write_report_shows_closeup_seam_score_when_present(tmp_path):
    scores = {"map": "M", "timestamp": "t", "l1": {},
              "l2": {"terrain_seam_score": 1.2, "terrain_closeup_seam_score": 1.05, "props": []},
              "l2_skipped": False}
    out = tmp_path / "run"; out.mkdir()
    write_report(scores, out, previous=None)
    html = (out / "report.html").read_text()
    assert "1.05" in html
    assert "closeup" in html.lower()


def test_write_report_embeds_scene_topdown_when_present(tmp_path):
    scores = {"map": "M", "timestamp": "t", "l1": {},
              "l2": {"terrain_seam_score": 1.0, "scene_topdown": True, "props": []},
              "l2_skipped": False}
    out = tmp_path / "run"; out.mkdir()
    write_report(scores, out, previous=None)
    html = (out / "report.html").read_text()
    assert "captures/scene_topdown.png" in html
    assert "orientation" in html.lower()


def test_write_report_omits_scene_topdown_when_absent(tmp_path):
    scores = {"map": "M", "timestamp": "t", "l1": {},
              "l2": {"terrain_seam_score": 1.0, "props": []},
              "l2_skipped": False}
    out = tmp_path / "run"; out.mkdir()
    write_report(scores, out, previous=None)
    html = (out / "report.html").read_text()
    assert "captures/scene_topdown.png" not in html
