"""
Tile Compositor — blends tile textures into composited images.

Replicates the original client's D3D9 tile-compositing behavior:
layer 0 is drawn as base, layers 1-3 are alpha-blended on top.
"""

from pathlib import Path
from PIL import Image
import numpy as np

# Target size for all composited output tiles
COMPOSITE_SIZE = 128


class TileResolutionError(RuntimeError):
    """Raised when a tile texture cannot be resolved."""
    pass


def blend_d3d(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Exact replica of the original client's per-channel tile blend.

    Per channel: out = trunc(src*fsa) + trunc(dst*(1-fsa)), fsa = srcA/255.0,
    each product truncated independently (C float->int cast). Output alpha 255.
    """
    fsa = src[..., 3:4].astype(np.float32) / 255.0
    s = (src[..., :3].astype(np.float32) * fsa).astype(np.uint16)      # trunc
    d = (dst[..., :3].astype(np.float32) * (1.0 - fsa)).astype(np.uint16)
    out = np.empty_like(src)
    out[..., :3] = (s + d).astype(np.uint8)   # max 255, no overflow possible
    out[..., 3] = 255
    return out


def resolve_tile_dir(set_name: str, tile_ird: Path) -> Path | None:
    """Find tile set directory (case-insensitive)."""
    target = set_name.lower()
    for d in tile_ird.iterdir():
        if d.is_dir() and d.name.lower() == target:
            return d
    return None


def load_tile_texture(tile_dir: Path, filename: str) -> Image.Image | None:
    """Load a TGA tile texture. Returns RGBA image or None."""
    tex_path = tile_dir / filename
    if not tex_path.exists():
        # Try case-insensitive lookup
        target = filename.lower()
        for f in tile_dir.iterdir():
            if f.name.lower() == target:
                tex_path = f
                break
        else:
            return None
    img = Image.open(tex_path).convert("RGBA")
    return img


def _resolve_tile_texture(
    tile_id: int, registry, tile_ird: Path, strict: bool = False,
) -> Image.Image | None:
    """Resolve a tile ID to a loaded texture image.

    Returning None means "layer contributes nothing" — legal per the
    original client:
    - Kind 0x00 is an EMPTY layer regardless of index/opt bits: the
      original client tests the kind byte, not the whole tile id.
      Shipped data carries ids like 0x0010 with stray index bits.
    - A referenced tile with no art (e.g. fringe indices into full-only
      sets like ROCK1044) is silently skipped: the original client's
      tile-texture lookup yields nothing for unloaded ids and its
      compositor skips absent sources.

    strict=True raises TileResolutionError only for a nonzero kind absent
    from the registry — data we cannot interpret (no shipped map has one).
    """
    if tile_id == 0:
        return None

    kind_id = (tile_id >> 8) & 0xFF
    index = (tile_id >> 4) & 0xF
    opt = tile_id & 0xF

    if kind_id == 0:
        return None

    ts = registry.tile_sets.get(kind_id)
    if ts is None:
        if strict:
            raise TileResolutionError(
                f"tile 0x{tile_id:04X}: kind 0x{kind_id:02X} not in registry")
        return None

    tex_name = ts.tiles.get((index, opt))
    if tex_name is None:
        # Fall back to opt=0 if specific opt not found
        tex_name = ts.tiles.get((index, 0))
    if tex_name is None:
        return None

    tile_dir = resolve_tile_dir(ts.name, tile_ird)
    if tile_dir is None:
        return None

    return load_tile_texture(tile_dir, tex_name)


def composite_layers(
    tile_ids: list[int],
    registry,
    tile_ird: Path,
    lenient: bool = False,
) -> Image.Image | None:
    """Composite up to 4 tile layers into a single image.

    Layer 0 is the base (drawn opaque). Layers 1-3 are alpha-blended on top.
    Returns an RGB image of COMPOSITE_SIZE × COMPOSITE_SIZE, or None if no
    textures could be loaded.

    Empty layers (kind 0x00) and referenced tiles with no art are silently
    skipped, matching the original compositor (see _resolve_tile_texture).
    If lenient=False, a nonzero kind absent from the registry raises
    TileResolutionError; lenient=True skips those too.
    """
    result = None

    for tile_id in tile_ids:
        tex = _resolve_tile_texture(tile_id, registry, tile_ird,
                                    strict=not lenient)
        if tex is None:
            continue

        # Resize to target composite size
        if tex.size != (COMPOSITE_SIZE, COMPOSITE_SIZE):
            tex = tex.resize((COMPOSITE_SIZE, COMPOSITE_SIZE), Image.LANCZOS)

        if result is None:
            # First layer: use as base (ignore alpha, treat as opaque)
            result = tex.convert("RGBA")
        else:
            # Subsequent layers: alpha-composite on top using exact D3D BlendColor
            result = Image.fromarray(blend_d3d(np.asarray(tex), np.asarray(result)))

    if result is None:
        return None

    return result.convert("RGB")
