class_name SfxLibrary
extends RefCounted
## Loads sfx.json (raw .sfd data in ORIGINAL D3D space), converts each
## effect to a runtime config at the boundary (spec §4.4: negate the
## values of dir_z / wind_z / blackhole_z — nothing else), packs the
## effect's textures into one atlas (spec §4.3.6 — 33 non-additive effects
## use several textures and 16 mix sizes, so one MultiMesh over one atlas
## keeps the original's global draw order), and hands out configured,
## UNPARENTED SfxObjects. Textures load RAW from a .gdignore'd folder via
## Image.load_tga_from_buffer (never the importer — the terrain-tile
## precedent), so no color-space conversion happens before the shader.

const CATALOG_PATH := "res://assets/effects/sfx.json"
const TEXTURE_DIR := "res://assets/effects/sfx_textures/"
const GUTTER := 1
const WHITE_SIZE := 4
const Z_GRAPHS := ["dir_z", "wind_z", "blackhole_z"]

var _effects: Dictionary = {}   # lowercase stem -> raw json entry
var _errors: Dictionary = {}
var _configs: Dictionary = {}   # stem -> built config
var _images: Dictionary = {}    # texture name -> Image (null cached for missing)
var _warned: Dictionary = {}


static func normalize(name: String) -> String:
	var n := name.strip_edges().to_lower()
	if n.ends_with(".sfd"):
		n = n.substr(0, n.length() - 4)
	return n


func load() -> bool:
	_effects.clear()
	_errors.clear()
	_configs.clear()
	if not FileAccess.file_exists(CATALOG_PATH):
		push_error("SfxLibrary: missing " + CATALOG_PATH)
		return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(CATALOG_PATH))
	if not (parsed is Dictionary) or not (parsed.get("effects") is Dictionary):
		push_error("SfxLibrary: malformed " + CATALOG_PATH)
		return false
	for k in parsed["effects"]:
		_effects[normalize(String(k))] = parsed["effects"][k]
	var errs: Variant = parsed.get("errors", {})
	if errs is Dictionary:
		for k in errs:
			_errors[normalize(String(k))] = String(errs[k])
	return not _effects.is_empty()


func names() -> PackedStringArray:
	var out := PackedStringArray(_effects.keys())
	out.sort()
	return out


func has(name: String) -> bool:
	return _effects.has(normalize(name))


func error_for(name: String) -> String:
	return String(_errors.get(normalize(name), ""))


func info(name: String) -> Dictionary:
	return _effects.get(normalize(name), {})


func config(name: String) -> Dictionary:
	var key := normalize(name)
	if _configs.has(key):
		return _configs[key]
	var raw: Dictionary = _effects.get(key, {})
	if raw.is_empty():
		return {}
	var graphs := {}
	for k in raw:
		var v: Variant = raw[k]
		if v is Dictionary and v.has("points"):
			var g := SfxGraph.from_points(v["points"])
			graphs[k] = g.negated() if k in Z_GRAPHS else g
	var atlas := atlas_for(key)
	var cfg := {
		"kind": String(raw.get("kind", "billboard")),
		"name_key": key,
		"additive": bool(raw.get("additive", true)),
		"total_time": float(raw.get("total_time", 1.0)),
		"texture_direction": int(raw.get("texture_direction", 0)),
		"alignment": int(raw.get("alignment", 0)),
		"graphs": graphs,
		"atlas": atlas["texture"],
		"rects": atlas["rects"],
		"white_rect": atlas["white_rect"],
		"missing_textures": atlas["missing"],
	}
	_configs[key] = cfg
	return cfg


func instantiate(name: String) -> SfxObject:
	var cfg := config(name)
	if cfg.is_empty():
		return null
	var obj := SfxObject.new()
	obj.name = "Sfx_" + normalize(name)
	obj.setup(cfg)
	return obj


func _load_image(tex_name: String) -> Image:
	if _images.has(tex_name):
		return _images[tex_name]
	var img: Image = null
	var path := TEXTURE_DIR + tex_name.to_lower()
	if FileAccess.file_exists(path):
		var candidate := Image.new()
		if candidate.load_tga_from_buffer(FileAccess.get_file_as_bytes(path)) == OK:
			candidate.convert(Image.FORMAT_RGBA8)
			img = candidate
	if img == null and not _warned.has(tex_name):
		_warned[tex_name] = true
		push_warning("SfxLibrary: texture '%s' missing/unreadable — white fallback" % tex_name)
	_images[tex_name] = img
	return img


func atlas_for(name: String) -> Dictionary:
	## Shelf-pack: [white block][tex0][tex1]... on one row, GUTTER texels
	## apart; rects are UV rects inset by half a texel so linear filtering
	## never bleeds across neighbors (the original sampled each texture on
	## its own with the D3D default WRAP mode — only the border texel differs).
	var raw: Dictionary = _effects.get(normalize(name), {})
	var tex_names: Array = raw.get("textures", [])
	var images: Array = []
	var missing: Array = []
	var width := GUTTER
	var height := WHITE_SIZE
	for t in tex_names:
		var img := _load_image(String(t))
		images.append(img)
		if img == null:
			missing.append(String(t))
		else:
			width += img.get_width() + GUTTER
			height = maxi(height, img.get_height())
	width += WHITE_SIZE + GUTTER
	height += 2 * GUTTER
	var atlas := Image.create(width, height, false, Image.FORMAT_RGBA8)
	atlas.fill(Color(0, 0, 0, 0))
	var x := GUTTER
	# white block first
	atlas.fill_rect(Rect2i(x, GUTTER, WHITE_SIZE, WHITE_SIZE), Color(1, 1, 1, 1))
	var white_rect := _uv_rect(x, GUTTER, WHITE_SIZE, WHITE_SIZE, width, height)
	x += WHITE_SIZE + GUTTER
	var rects: Array = []
	for img in images:
		if img == null:
			rects.append(white_rect)
			continue
		atlas.blit_rect(img, Rect2i(0, 0, img.get_width(), img.get_height()), Vector2i(x, GUTTER))
		rects.append(_uv_rect(x, GUTTER, img.get_width(), img.get_height(), width, height))
		x += img.get_width() + GUTTER
	return {"texture": ImageTexture.create_from_image(atlas), "rects": rects,
			"white_rect": white_rect, "missing": missing, "size": Vector2i(width, height)}


static func _uv_rect(x: int, y: int, w: int, h: int, aw: int, ah: int) -> Rect2:
	return Rect2((x + 0.5) / float(aw), (y + 0.5) / float(ah),
			(w - 1.0) / float(aw), (h - 1.0) / float(ah))
