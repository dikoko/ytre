class_name HeightService
extends RefCounted
## Gameplay terrain height from the exported heightmap PNG ({code}_h.bmp
## converted by 30/35_export scripts, RG16 encoding: 16-bit height value
## split as R=high byte, G=low byte — 22 maps ship 16bpp height BMPs whose
## values exceed a byte). Formula h = value*0.1 - 10.0. Original sampling:
## per-cell triangle lerp, diagonal (0,0)->(1,1), pick by dx<=dz — matching
## retail client behavior (which also decodes the 16bpp BMPs big-endian).
## World z is negated vs grid row.
##
## The renderer draws terrain at the RAW decoded height, matching the
## original (the retail height lookup returns the stored value verbatim,
## with no offset). The viewer used to sink the mesh 0.15 "so the
## ground sits under prop bases", but that levitated every ground-plate/
## stair prop 0.15 above the visible terrain, opening see-through slit
## lines at prop edges at grazing run-camera angles (SF002001 terrace).
## surface_height() is kept as the "height of the rendered surface" API;
## it now equals sample().

var _img: Image = null
var _w := 0
var _h := 0


func load_map(code: String) -> bool:
	_img = Image.new()
	var abs_path := ProjectSettings.globalize_path(
		"res://assets/maps/%s/%s.png" % [code, code])
	if _img.load(abs_path) != OK:   # raw load: bypass import compression
		push_warning("height_service: cannot load heightmap for %s" % code)
		_img = null
		return false
	_w = _img.get_width()
	_h = _img.get_height()
	return true


func in_bounds(x: float, z: float) -> bool:
	if _img == null:
		return false
	var gz := -z
	return x >= 0.0 and x <= float(_w - 1) and gz >= 0.0 and gz <= float(_h - 1)


func _vert(gx: int, gz: int) -> float:
	# RG16: R carries the high byte, G the low byte. roundf() rescues the
	# byte values from get_pixel's /255.0 float division before the <<8.
	var c := _img.get_pixel(gx, gz)
	return (roundf(c.r * 255.0) * 256.0 + roundf(c.g * 255.0)) * 0.1 - 10.0


func sample(x: float, z: float) -> float:
	if not in_bounds(x, z):
		return -100.0
	var gz := -z
	var cx := clampi(int(floor(x)), 0, _w - 2)
	var cz := clampi(int(floor(gz)), 0, _h - 2)
	var dx := x - float(cx)
	var dz := gz - float(cz)
	var h00 := _vert(cx, cz)
	var h10 := _vert(cx + 1, cz)
	var h01 := _vert(cx, cz + 1)
	var h11 := _vert(cx + 1, cz + 1)
	# Diagonal (0,0)->(1,1): dx<=dz picks the (00,01,11) triangle, else (00,10,11).
	if dx <= dz:
		return h00 + (h01 - h00) * (dz - dx) + (h11 - h01) * dx
	return h00 + (h10 - h00) * (dx - dz) + (h11 - h10) * dz


func surface_height(x: float, z: float) -> float:
	if not in_bounds(x, z):
		return -100.0
	return sample(x, z)


func get_bounds() -> AABB:
	if _img == null:
		return AABB()
	var hmin := 1e9
	var hmax := -1e9
	for gz in _h:
		for gx in _w:
			var v := _vert(gx, gz)
			hmin = minf(hmin, v)
			hmax = maxf(hmax, v)
	return AABB(Vector3(0, hmin, -float(_h - 1)),
			Vector3(float(_w - 1), maxf(hmax - hmin, 0.1), float(_h - 1)))
