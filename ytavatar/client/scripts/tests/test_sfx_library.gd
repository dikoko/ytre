extends SceneTree
## Run: "$GODOT_BIN" --headless --path client --script scripts/tests/test_sfx_library.gd

var _fails := 0


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok: " + label)
	else:
		printerr("FAIL: " + label)
		_fails += 1


func _init() -> void:
	await process_frame
	var lib := SfxLibrary.new()
	_check(lib.load(), "sfx.json loads")
	_check(lib.names().size() == 154, "154 effects")
	_check(lib.has("sfx_common_particledot1_red") and lib.has("SFX_Common_ParticleDot1_Red.sfd"),
			"name lookup ignores case and the .sfd suffix")
	_check(not lib.has("nope"), "unknown name")
	_check(lib.instantiate("nope") == null, "instantiate unknown -> null")

	var cfg := lib.config("sfx_common_particledot1_red")
	_check(cfg["kind"] == "emitter_polygon" and cfg["additive"] == true, "config basics")
	_check(cfg["graphs"]["gravity"] is SfxGraph and absf(cfg["graphs"]["gravity"].value(0.0) - 10.0) < 1e-5, "graphs built")
	_check(cfg["atlas"] is Texture2D and cfg["rects"].size() == 1, "atlas + one rect")
	var r: Rect2 = cfg["rects"][0]
	_check(r.position.x > 0.0 and r.size.x < 1.0 and r.size.x > 0.0, "rect is half-texel inset inside the atlas")
	var wr: Rect2 = cfg["white_rect"]
	_check(wr.size.x > 0.0 and wr != r, "white rect reserved separately")

	# Z conversion: find any effect with a nonzero dir_z and compare to the raw entry
	var converted := false
	for n in lib.names():
		var raw: Dictionary = lib.info(n)
		if raw["kind"] != "emitter_polygon":
			continue
		var pts: Array = raw["dir_z"]["points"]
		if pts.is_empty() or absf(float(pts[0][1])) < 1e-6:
			continue
		var g: SfxGraph = lib.config(n)["graphs"]["dir_z"]
		converted = absf(float(g.points[0][1]) + float(pts[0][1])) < 1e-6 \
				and absf(float(g.points[0][3]) + float(pts[0][3])) < 1e-6
		var gy: SfxGraph = lib.config(n)["graphs"]["dir_y"]
		converted = converted and absf(float(gy.points[0][1]) - float(raw["dir_y"]["points"][0][1])) < 1e-6
		break
	_check(converted, "dir_z negated at load (v and c2), dir_y untouched")

	# multi-texture effect with mixed sizes: atlas packs both, rects differ
	var aging := lib.config("sfx_common_condition_aging1")
	_check(aging["rects"].size() == 2 and aging["rects"][0].size != aging["rects"][1].size, "mixed-size textures packed into one atlas (different uv sizes)")
	var asz: Vector2i = lib.atlas_for("sfx_common_condition_aging1")["size"]
	_check(asz.x >= 64 + 32 + 4 + 4 and asz.y >= 64 + 2, "atlas sized for 64 + 32 + white block + gutters (got %s)" % asz)

	var obj := lib.instantiate("sfx_common_condition_aging_billboard")
	_check(obj != null and obj.kind == "billboard" and obj.get_parent() == null, "instantiate returns an unparented SfxObject")
	obj.free()

	# missing texture -> white rect, still instantiable
	lib._effects["zz_missing"] = {"kind": "billboard", "textures": ["not_there.tga"], "missing_textures": ["not_there.tga"],
			"additive": true, "total_time": 1.0, "texture_direction": 1, "alignment": 0,
			"opacity": {"points": [[0, 1, 0, 1]]}, "color_r": {"points": [[0, 1, 0, 1]]}, "color_g": {"points": [[0, 1, 0, 1]]},
			"color_b": {"points": [[0, 1, 0, 1]]}, "texture_frame": {"points": [[0, 1, 0, 1]]},
			"width": {"points": [[0, 1, 0, 1]]}, "height": {"points": [[0, 1, 0, 1]]}}
	var mcfg := lib.config("zz_missing")
	_check(mcfg["rects"].size() == 1 and mcfg["rects"][0] == mcfg["white_rect"], "missing texture resolves to the white rect")
	var mobj := lib.instantiate("zz_missing")
	_check(mobj != null, "effect with a missing texture still plays")
	mobj.free()

	print("FAILED: %d" % _fails if _fails else "ALL OK")
	quit(1 if _fails else 0)
