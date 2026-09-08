# client/scripts/tests/test_sfx_random.gd
extends SceneTree
## Run: "$GODOT_BIN" --headless --path client --script scripts/tests/test_sfx_random.gd
## Replays the Python-generated parity fixture (tools/avatar_export/src/
## sfx_random_ref.py via 48_export_sfx.py) so both sides of the port draw
## the same numbers in the same order.

const PARITY := "res://scripts/tests/fixtures/sfx_random_parity.json"
var _fails := 0


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok: " + label)
	else:
		printerr("FAIL: " + label)
		_fails += 1


func _near(a: float, b: float, eps := 1e-5) -> bool:
	return absf(a - b) <= eps


func _init() -> void:
	_check(SfxRandom.load_tables(), "tables load")
	var p: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(PARITY))
	_check(int(p["version"]) == 1, "parity fixture v1")

	SfxRandom.reset()
	var ok := true
	for v in p["irand"]:
		ok = ok and SfxRandom.irand() == int(v)
	_check(ok, "irand sequence")
	SfxRandom.reset()
	ok = true
	for v in p["frand"]:
		ok = ok and _near(SfxRandom.frand(), float(v))
	_check(ok, "frand sequence")

	SfxRandom.reset()
	for i in 10000:
		SfxRandom.irand()
	_check(SfxRandom.irand() == int(p["irand"][0]), "int cursor wraps at 10000")
	_check(SfxRandom.cursors() == Vector2i(1, 0), "cursors() reports (int, float)")

	_check(SfxRandom.deg_units(90.0) == 16380, "deg_units 90")
	_check(SfxRandom.deg_units(-90.0) == 49156, "deg_units -90 wraps (fast-spin quirk)")
	_check(_near(SfxRandom.sin_units(16384), 1.0) and _near(SfxRandom.cos_units(32768), -1.0), "sin/cos units")

	SfxRandom.reset()
	ok = true
	for v in p["random_float"]:
		ok = ok and _near(SfxRandom.random_float(0.5, 2.0), float(v))
	_check(ok, "random_float parity")
	SfxRandom.reset()
	ok = true
	for v in p["random_life"]:
		ok = ok and _near(SfxRandom.random_life(2.0, 1.0), float(v))
	_check(ok, "random_life parity")
	SfxRandom.reset()
	ok = true
	for v in p["random_direction"]:
		var d := SfxRandom.random_direction(Vector3(1.0, 2.0, 3.0), 35.065)
		ok = ok and _near(d.x, float(v[0])) and _near(d.y, float(v[1])) and _near(d.z, float(v[2]))
	_check(ok, "random_direction parity")
	SfxRandom.reset()
	ok = true
	for s in p["spawn"]:
		# the emitter's exact per-particle draw order (spec §3.3)
		var d := SfxRandom.random_direction(Vector3(0.0, 5.07, 0.0), 35.065)
		var av := SfxRandom.deg_units(SfxRandom.random_float(0.0, 90.0))
		var ideg := SfxRandom.deg_units(SfxRandom.random_float(0.0, 180.0))
		var life := SfxRandom.random_life(2.0, 1.0)
		ok = ok and _near(d.x, float(s["dir"][0])) and _near(d.y, float(s["dir"][1])) and _near(d.z, float(s["dir"][2]))
		ok = ok and av == int(s["ang_vel"]) and ideg == int(s["init_deg"]) and _near(life, float(s["life"]))
	_check(ok, "spawn draw-order parity")

	print("FAILED: %d" % _fails if _fails else "ALL OK")
	quit(1 if _fails else 0)
