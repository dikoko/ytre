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

	# Movement grid (.map port, 2026-08-16 plaza report): the original's
	# walkability authority. Fixture values verified against the parsed
	# source data (test_map_parser.py pins the same cells).
	_check(nav.has_move_grid(), "SF001001 move grid loads")
	# School porch/stairs: movable (the LOS wall grid falsely blocked here).
	_check(nav.movable(123.5, -76.5), "porch cluster movable")
	# Stray plaza island (the 2026-08-16 "blocked in open space" spot):
	# blocked in the original's own data — a balustrade-post-class obstacle.
	_check(not nav.movable(66.5, -102.5), "stray plaza cell blocked")
	_check(nav.movable(66.5, -101.5), "cell south of the stray open")
	# Out of bounds is blocked (the original client's walkability rule).
	_check(not nav.movable(-1.0, -0.5), "out-of-bounds blocked")

	# Runner against the move grid: diagonal corner rule + wall slide.
	var runner001 := AvatarRunner.new()
	runner001.setup(hs, null, {}, nav)
	# Corner rule: (71,88)->(72,89) are both movable but diagonal, and the
	# shared orthogonal neighbor (72,88) is blocked -> no corner squeeze.
	runner001.avatar_position = Vector3(71.5, 0.0, -88.5)
	_check(runner001.step_blocked(72.5, -89.5),
			"diagonal corner squeeze blocked")
	_check(not runner001.step_blocked(71.5, -89.5),
			"straight step beside the corner open")
	# Slide: heading NE into the stray (66,102) — the straight step is
	# blocked, the X-axis slide candidate advances along the boundary.
	runner001.avatar_position = Vector3(65.7, 0.0, -101.7)
	runner001.avatar_position.y = runner001.ground_height(65.7, -101.7)
	_check(not runner001._try_step(Vector3(66.3, 0.0, -102.3)),
			"straight step into stray blocked")
	_check(runner001._try_step(Vector3(66.3, 0.0, -101.7)),
			"axis slide along the stray advances")
	_check(not runner001._try_step(runner001.avatar_position),
			"no-op step does not count as movement")
	# Corner rounding: marching straight north into the 1-cell stray at
	# (66,102) must WALK AROUND it (the original's pathfinder never dead-
	# stopped on a 1-cell island), while the solid planter band at rows
	# 89-90 must still stop cleanly with no lateral drift.
	runner001.avatar_position = Vector3(66.5, 0.0, -103.6)
	runner001.avatar_position.y = runner001.ground_height(66.5, -103.6)
	var north := Vector3(0.0, 0.0, 1.0)
	for i in 120:
		runner001._move_step(north, 1.0 / 60.0)
	_check(runner001.avatar_position.z > -102.0,
			"corner rounding passes the plaza stray (z=%.2f)" % runner001.avatar_position.z)
	# Lane x=57 has a clean band front (rows 89-90 blocked across all
	# adjacent lanes, no islands in front) — head-on stop, zero drift.
	runner001.avatar_position = Vector3(57.5, 0.0, -94.5)
	runner001.avatar_position.y = runner001.ground_height(57.5, -94.5)
	for i in 120:
		runner001._move_step(north, 1.0 / 60.0)
	_check(runner001.avatar_position.z < -90.5,
			"solid band still stops (z=%.2f)" % runner001.avatar_position.z)
	_check(absf(runner001.avatar_position.x - 57.5) < 0.01,
			"no lateral drift along the band (x=%.2f)" % runner001.avatar_position.x)
	runner001.free()

	# Escape-hatch regression (nm-task-5 final review): SF002013's default
	# spawn (portals[0].pos = (64.0, 0.0, -68.0)) lands inside a wall cell —
	# this is the exact fixture the reviewer used to prove that an
	# unconditional hatch lets the avatar tunnel 26.7 m through 27 distinct
	# wall cells. The hatch must be OUTBOUND-only: free movement within the
	# trapped cell and out to open ground, but never into a NEW wall cell.
	var nav2013 := NavService.new()
	_check(nav2013.load_map("SF002013"), "SF002013 blobs load")
	_check(nav2013.has_walls(), "SF002013 has walls")
	# The spawn cell is blocked in the movement grid too (att 0), so the
	# hatch exercises the move-grid path since the .map port (2026-08-16).
	_check(nav2013.has_move_grid(), "SF002013 has move grid")
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
