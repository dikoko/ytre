extends SceneTree
## Run: GODOT_BIN --headless --path client --script scripts/tests/test_height_service.gd


func _init() -> void:
	var failures := 0
	var hs := HeightService.new()
	failures += _check(hs.load_map("SF001001"), "loads SF001001")
	# Vertex-exact: sample at integer coords == pure pixel decode.
	var img := Image.new()
	img.load(ProjectSettings.globalize_path("res://assets/maps/SF001001/SF001001.png"))
	for probe in [[10, 10], [75, 106], [140, 20]]:
		# RG16 heightmap PNG: R=high byte, G=low byte of the 16-bit value.
		var c := img.get_pixel(probe[0], probe[1])
		var want := (roundf(c.r * 255.0) * 256.0 + roundf(c.g * 255.0)) * 0.1 - 10.0
		var got := hs.sample(float(probe[0]), -float(probe[1]))
		failures += _check(absf(got - want) < 0.001, "vertex %s: %f vs %f" % [probe, got, want])
	# Interpolated samples stay within the cell's corner min/max.
	var corners := [hs.sample(50, -50), hs.sample(51, -50), hs.sample(50, -51), hs.sample(51, -51)]
	var mid := hs.sample(50.5, -50.5)
	failures += _check(mid >= corners.min() - 0.001 and mid <= corners.max() + 0.001, "midpoint bounded")
	failures += _check(hs.sample(-5.0, 10.0) == -100.0, "out of bounds sentinel")
	failures += _check(hs.in_bounds(75.0, -106.0), "in_bounds true")
	failures += _check(not hs.in_bounds(500.0, -500.0), "in_bounds false")
	var b := hs.get_bounds()
	failures += _check(b.size.x > 100.0 and b.position.y >= -10.0, "bounds sane")
	# 16bpp map (SF002001 ships a 16-bit height BMP): oracle values hardcoded
	# from the ORIGINAL BMP via the big-endian 16bpp decode — catches any RG16
	# encode/decode or orientation regression against independent ground truth.
	failures += _check(hs.load_map("SF002001"), "loads SF002001")
	for probe in [[125, 125, -2.0], [60, 180, 2.1], [200, 40, -1.8]]:
		var got16 := hs.sample(float(probe[0]), -float(probe[1]))
		failures += _check(absf(got16 - probe[2]) < 0.001,
				"SF002001 16bpp vertex (%d,%d): %f vs %f" % [probe[0], probe[1], got16, probe[2]])
	print("FAILED: %d" % failures if failures else "ALL OK")
	quit(1 if failures else 0)


func _check(cond: bool, label: String) -> int:
	if not cond:
		printerr("FAIL: " + label)
		return 1
	return 0
