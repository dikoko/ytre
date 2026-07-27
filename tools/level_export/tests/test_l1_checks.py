"""L1 eval checks against real SF001001 data."""
from mapeval.l1_checks import run_l1


def test_l1_runs_on_sf001001():
    result = run_l1("SF001001")
    assert set(result) >= {"cvs_invariants", "det_census", "texture_resolution"}


def test_cvs_invariants_hold_on_sf001001():
    inv = run_l1("SF001001")["cvs_invariants"]
    # Measured 2026-07-12: SF001001 satisfies all tile-layer invariants
    assert inv["layer0_not_full"] == 0
    assert inv["fringe_with_opt"] == 0
    assert inv["duplicate_kind_layers"] == 0
    assert inv["palette_count"] == 318


def test_det_census_sf001001():
    det = run_l1("SF001001")["det_census"]
    assert det["total"] == 901
    assert det["negative"] == 0
    assert det["negative_ids"] == []


def test_texture_resolution_sf001001():
    tex = run_l1("SF001001")["texture_resolution"]
    assert tex["unresolved"] == []


def test_det_census_negative_dets_are_not_violations():
    """Negative-determinant placements are fully supported (mirrorx GLBs,
    30_export_map) — the census stays informational, never a violation.
    SF002004 has one such placement in shipped data."""
    det = run_l1("SF002004")["det_census"]
    assert det["negative"] == 1
    assert det["violations"] == []


def test_texture_resolution_benign_refs_are_not_violations():
    """SF001009 references fringe tiles into full-only sets (e.g. SE00144)
    and kind-0x00 ids with stray index bits — both composite as skipped
    layers in the original client, so they are not violations. Only a
    nonzero kind absent from the registry would be."""
    tex = run_l1("SF001009")["texture_resolution"]
    assert tex["violations"] == []
    assert tex["skipped_missing_art"] > 0


def test_heightmap_check_sf001001_8bpp_clean():
    hm = run_l1("SF001001")["heightmap"]
    assert hm["bpp"] == 8
    assert hm["png_matches_bmp"] is True
    assert hm["navmesh_cells"] >= 50
    assert hm["median_navmesh_err"] < 3.0
    assert hm["violations"] == []


def test_heightmap_check_sf002001_16bpp_clean():
    """SF002001 ships a 16bpp height BMP (first byte HIGH). The 2026-07-26
    bug: PIL converted it as RGB555 color, distorting every height ~10 m
    median vs the navmesh. The RG16 pipeline must decode it bit-exact and
    agree with the navmesh again."""
    hm = run_l1("SF002001")["heightmap"]
    assert hm["bpp"] == 16
    assert hm["png_matches_bmp"] is True
    assert hm["navmesh_cells"] >= 50
    assert hm["median_navmesh_err"] < 3.0
    assert hm["violations"] == []
