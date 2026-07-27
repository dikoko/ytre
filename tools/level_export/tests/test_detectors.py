import numpy as np
from mapeval.detectors import dark_ratio, magenta_ratio, seam_score

BG = (30, 30, 200)  # capture background color


def _canvas(w=64, h=64, color=(120, 120, 120)):
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = color
    return img


def test_dark_ratio_ignores_background():
    img = _canvas(color=BG)          # all background
    img[10:20, 10:20] = (5, 5, 5)    # dark prop pixels
    img[30:40, 30:40] = (200, 200, 200)  # lit prop pixels
    assert dark_ratio(img, BG) == 0.5   # 100 dark / 200 prop pixels


def test_dark_ratio_zero_when_no_prop():
    assert dark_ratio(_canvas(color=BG), BG) == 0.0


def test_dark_ratio_tolerates_near_background():
    # rendered background drifts a few units from the requested clear color
    img = _canvas(color=(33, 27, 205))          # near-BG, within tolerance of BG
    img[10:20, 10:20] = (5, 5, 5)               # dark prop pixels
    img[30:40, 30:40] = (200, 200, 200)         # lit prop pixels
    assert dark_ratio(img, BG) == 0.5           # near-BG excluded from foreground


def test_magenta_ratio():
    img = _canvas()
    img[:8, :8] = (255, 0, 255)
    assert magenta_ratio(img) > 0.0
    assert magenta_ratio(_canvas()) == 0.0


def test_seam_score_flags_grid_lines():
    smooth = _canvas(w=80, h=80)
    seamy = _canvas(w=80, h=80)
    seamy[::8, :] = (0, 0, 0)   # dark line at every cell boundary (8 px/cell)
    seamy[:, ::8] = (0, 0, 0)
    assert seam_score(seamy, 8) > seam_score(smooth, 8) + 1.0


def test_seam_score_flat_image_is_one():
    assert seam_score(_canvas(w=80, h=80), 8) == 1.0


def test_seam_score_captures_both_sides_of_seam_line():
    seamy = _canvas(w=80, h=80)
    seamy[::8, :] = (0, 0, 0)
    seamy[:, ::8] = (0, 0, 0)
    # both enter and exit gradients land in the boundary bucket -> strong ratio
    assert seam_score(seamy, 8) > 20.0
