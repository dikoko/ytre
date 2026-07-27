extends SceneTree
## Run: GODOT_BIN --headless --path client --script scripts/tests/test_nav_service.gd

var _fails := 0


func _init() -> void:
	var nav := NavService.new()
	_check(nav.load_map("SF001001"), "SF001001 blobs load")
	_check(nav.has_navmesh(), "has navmesh")
	_check(nav.has_walls(), "has walls")

	var hs := HeightService.new()
	_check(hs.load_map("SF001001"), "heightmap loads")

	# Platform cluster from the survey: original X 121-125, Z 75-78
	# (Godot z = -75..-78) sits ~1.2-2.0 above the terrain.
	var hits := 0
	var raised := 0
	for gx in range(121, 126):
		for gz in range(75, 79):
			var y := nav.sample(float(gx) + 0.5, -(float(gz) + 0.5))
			if is_nan(y):
				continue
			hits += 1
			if y - hs.surface_height(float(gx) + 0.5, -(float(gz) + 0.5)) > 0.5:
				raised += 1
	_check(hits > 0, "navmesh hits in the platform cluster (%d)" % hits)
	_check(raised > 0, "cluster cells sit >0.5 above terrain (%d/%d)" % [raised, hits])

	# Off-navmesh must MISS so the caller can fall back to terrain.
	_check(is_nan(nav.sample(2.5, -2.5)), "off-navmesh returns NAN")

	# A map with no navmesh: every sample misses, nothing crashes.
	var empty := NavService.new()
	empty.load_map("FD000100")
	_check(not empty.has_navmesh(), "FD000100 has no navmesh")
	_check(is_nan(empty.sample(20.0, -20.0)), "empty navmesh returns NAN")

	# Walls: find a real wall cell, then assert the DDA sees it and is symmetric.
	var wall := Vector2i(-1, -1)
	for cz in range(0, 149):
		for cx in range(0, 149):
			if nav.is_wall(float(cx) + 0.5, -(float(cz) + 0.5)):
				wall = Vector2i(cx, cz)
				break
		if wall.x >= 0:
			break
	_check(wall.x >= 0, "found a wall cell (%s)" % wall)
	if wall.x >= 0:
		var wx := float(wall.x) + 0.5
		var wz := -(float(wall.y) + 0.5)
		var a := nav.crosses_wall(wx - 6.0, wz, wx + 6.0, wz)
		var b := nav.crosses_wall(wx + 6.0, wz, wx - 6.0, wz)
		_check(a == b, "wall DDA symmetric (%s == %s)" % [a, b])
		_check(a or nav.crosses_wall(wx, wz - 6.0, wx, wz + 6.0),
				"a segment through the wall cell is blocked")

	# Escape-hatch regression (nm-task-5 final review): SF002013's default
	# spawn (portals[0].pos = (64.0, 0.0, -68.0)) lands inside a wall cell —
	# this is the exact fixture the reviewer used to prove that an
	# unconditional hatch lets the avatar tunnel 26.7 m through 27 distinct
	# wall cells. The hatch must be OUTBOUND-only: free movement within the
	# trapped cell and out to open ground, but never into a NEW wall cell.
	var nav2013 := NavService.new()
	_check(nav2013.load_map("SF002013"), "SF002013 blobs load")
	_check(nav2013.has_walls(), "SF002013 has walls")
	var hs2013 := HeightService.new()
	_check(hs2013.load_map("SF002013"), "SF002013 heightmap loads")
	var spawn_x := 64.0
	var spawn_z := -68.0
	_check(nav2013.is_wall(spawn_x, spawn_z), "SF002013 default spawn is inside a wall cell")
	# (65,68) and (64,67) confirmed against the shipped walls.bin: the east
	# neighbor is a DIFFERENT wall cell, the north neighbor is open ground.
	var new_wall_x := 65.5
	var new_wall_z := -68.5
	var open_x := 64.5
	var open_z := -67.5
	_check(nav2013.is_wall(new_wall_x, new_wall_z), "SF002013 (65,68) is a wall cell (fixture check)")
	_check(not nav2013.is_wall(open_x, open_z), "SF002013 (64,67) is open ground (fixture check)")
	var runner := AvatarRunner.new()
	runner.setup(hs2013, null, {}, nav2013)
	runner.avatar_position = Vector3(spawn_x + 0.5, 0.0, spawn_z - 0.5)
	_check(runner.step_blocked(new_wall_x, new_wall_z),
			"SF002013 trapped avatar cannot tunnel into a NEW wall cell")
	_check(not runner.step_blocked(open_x, open_z),
			"SF002013 trapped avatar can still escape to open ground")
	runner.free()   # Node3D — never added to a tree, must free explicitly

	print("FAILED: %d" % _fails if _fails else "ALL OK")
	quit(1 if _fails else 0)


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok: " + label)
	else:
		printerr("FAIL: " + label)
		_fails += 1
