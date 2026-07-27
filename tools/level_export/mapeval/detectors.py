"""Image-space detectors scored over Godot captures."""
import numpy as np

DARK_LUMA = 40  # 0-255 luma below this counts as "dark" (lighting inversion)


def _luma(img: np.ndarray) -> np.ndarray:
    return (0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2])


def dark_ratio(img: np.ndarray, bg: tuple[int, int, int], bg_tol: int = 12) -> float:
    """Fraction of non-background pixels that are dark.

    High values on a prop capture mean it is lit from below/inside —
    the winding/normal inversion failure mode. Background is matched with
    a per-channel tolerance: Godot's tonemapping/sRGB pipeline shifts the
    clear color a few units, so exact equality never matches.
    """
    diff = np.abs(img.astype(np.int16) - np.asarray(bg, np.int16))
    fg = np.any(diff > bg_tol, axis=-1)
    if not fg.any():
        return 0.0
    return float((_luma(img)[fg] < DARK_LUMA).mean())


def magenta_ratio(img: np.ndarray) -> float:
    """Fraction of pixels that are colorkey/fallback magenta."""
    m = (img[..., 0] > 240) & (img[..., 1] < 20) & (img[..., 2] > 240)
    return float(m.mean())


def seam_score(img: np.ndarray, px_per_cell: int) -> float:
    """Ratio of luma gradient at cell boundaries vs interior, regularized.

    Captures are top-down orthographic, aligned so cell boundaries land on
    pixel rows/cols at multiples of px_per_cell. The boundary bucket takes
    both sides of each boundary (diff indices == 0 and == px_per_cell-1,
    mod px_per_cell) so 1px seam lines contribute fully. The +1.0 luma
    regularizer pins flat images at exactly 1.0.
    ~1.0 = no seams; higher = boundary discontinuities (tile bleeding).
    """
    y = _luma(img.astype(np.float64))
    gx = np.abs(np.diff(y, axis=1))  # gradient across column boundaries
    gy = np.abs(np.diff(y, axis=0))
    mod_x = np.arange(gx.shape[1]) % px_per_cell
    mod_y = np.arange(gy.shape[0]) % px_per_cell
    col_b = (mod_x == px_per_cell - 1) | (mod_x == 0)
    row_b = (mod_y == px_per_cell - 1) | (mod_y == 0)
    boundary = np.concatenate([gx[:, col_b].ravel(), gy[row_b, :].ravel()])
    interior = np.concatenate([gx[:, ~col_b].ravel(), gy[~row_b, :].ravel()])
    return float((boundary.mean() + 1.0) / (interior.mean() + 1.0))
