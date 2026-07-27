extends SceneTree
## Tool probe: loads maps through the real level_tool scene, asserts
## height/camera/portal invariants, saves screenshots.
## Run (WINDOWED — viewport capture needs a real window):
##   "$GODOT_BIN" --path client --script scripts/tests/tool_probe.gd --position 4000,4000

const MAPS := ["SF001001", "SF002001", "FD000100"]
const SHOTS_DIR := "res://../reports/tool_probe"

var _failures := 0


func _init() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOTS_DIR))
	var tool_scene := (load("res://scenes/level_tool.tscn") as PackedScene).instantiate()
	root.add_child(tool_scene)
	await process_frame
	for code in MAPS:
		await _probe_map(tool_scene, code)
	print("PROBE FAILED: %d" % _failures if _failures else "PROBE ALL OK")
	quit(1 if _failures else 0)


func _probe_map(tool: Node, code: String) -> void:
	tool.load_level(code)
	for i in 30: await process_frame   # let loaders finish
	_check(tool.map_host.current_code == code, "%s loaded" % code)
	_check(tool.map_host.get_terrain() != null, "%s terrain present" % code)
	# Height service vs terrain: 5 fixed sample points inside bounds.
	var hs: HeightService = tool.height_service
	var b := hs.get_bounds()
	for f: float in [0.2, 0.35, 0.5, 0.65, 0.8]:
		var x := b.position.x + b.size.x * f
		var z := b.position.z + b.size.z * f
		var h := hs.sample(x, z)
		_check(h > -10.5 and h < 30.0, "%s height sane at %.1f,%.1f (%.2f)" % [code, x, z, h])
	# Portal count matches catalog.
	var want: int = tool.catalog.get_level(code).get("portals", []).size()
	_check(tool.portal_markers.get_child_count() == want,
			"%s portal markers %d == %d" % [code, tool.portal_markers.get_child_count(), want])
	# Camera clamp: force the explore camera underground; it must recover.
	var cam: ExploreCamera = tool._camera
	var center := b.get_center()
	cam.position = Vector3(center.x, -50.0, center.z)
	cam.clamp_now()
	var cam_ground := hs.sample(cam.position.x, cam.position.z)
	_check(cam_ground > -50.0, "%s recovery check sampled real ground" % code)
	_check(cam.position.y >= cam_ground,
			"%s camera clamped above ground (%.2f >= %.2f)" % [code, cam.position.y, cam_ground])
	cam.reset_view()
	# Run mode: avatar Y == sampled height at spawn.
	var pre_run_fov := cam.fov
	var pre_run_projection := cam.projection
	tool._toggle_run()
	for i in 20: await process_frame
	var runner: AvatarRunner = tool.runner
	_check(runner.active, "%s run mode active" % code)
	# Feet plant on the composite ground (navmesh-first, terrain fallback —
	# same resolution AvatarRunner.enter() used for the spawn), not just the
	# terrain surface — tolerance is tight enough to catch the composite
	# regressing back to a terrain-only lookup.
	var want_y := runner.ground_height(runner.avatar_position.x, runner.avatar_position.z)
	_check(absf(runner.avatar_position.y - want_y) < 0.02,
			"%s avatar on composite ground (%.3f vs %.3f)" % [code, runner.avatar_position.y, want_y])
	var sx := runner.avatar_position.x
	var sz := runner.avatar_position.z
	if is_nan(tool.nav_service.sample(sx, sz)):
		# Terrain-resolved spawn: pin the RAW decoded height explicitly —
		# comparing against ground_height alone is tautological. The renderer
		# draws terrain at the raw height (original GetH has no offset); the
		# old 0.15 render sink opened see-through slits under prop edges and
		# must not come back.
		var want_raw := hs.sample(sx, sz)
		_check(absf(runner.avatar_position.y - want_raw) < 0.02,
				"%s terrain spawn at raw decoded height (%.3f vs %.3f)"
				% [code, runner.avatar_position.y, want_raw])
	await _shot("%s_run" % code)
	if code == "SF001001":
		# Porch/platform cluster (original X 121-125 / Z 75-78): the navmesh
		# must win over the terrain fallback and the avatar must resolve
		# onto it, not sink through to the ground below.
		# (Moved AFTER the screenshot above so it doesn't ruin the shot with
		# a teleported avatar — captured separately, not visually checked.)
		var px := 123.5
		var pz := -76.5
		var gh := runner.ground_height(px, pz)
		var terrain_h := hs.surface_height(px, pz)
		_check(not is_nan(gh) and gh - terrain_h > 0.5,
				"%s navmesh wins on porch cluster (%.2f vs terrain %.2f)" % [code, gh, terrain_h])
		runner.avatar_position = Vector3(px, gh, pz)
		var nav: NavService = tool.nav_service
		# A step onto an adjacent porch cell must stay resolved via the
		# navmesh (not drop to the terrain fallback) — proves movement across
		# the cluster stays on-mesh, not just that a single point sampled
		# correctly (which the assignment above trivially satisfies).
		var npx := px
		var npz := pz
		var found_neighbor := false
		for off: Vector2 in [Vector2(1, 0), Vector2(-1, 0), Vector2(0, 1), Vector2(0, -1)]:
			var cx: float = px + off.x
			var cz: float = pz + off.y
			if not is_nan(nav.sample(cx, cz)):
				npx = cx
				npz = cz
				found_neighbor = true
				break
		_check(found_neighbor, "%s found an adjacent porch cell on navmesh" % code)
		if found_neighbor:
			var n_next := nav.sample(npx, npz)
			_check(not runner.step_blocked(npx, npz),
					"%s step across porch cluster is not blocked" % code)
			var next_gh := runner.ground_height(npx, npz)
			_check(is_equal_approx(next_gh, n_next),
					"%s step onto adjacent porch cell stays on navmesh (%.2f == %.2f)" % [code, next_gh, n_next])
		# Wall blocking (Critical finding, nm-task-5): a per-frame step that
		# lands INSIDE a wall cell must be blocked even though it never
		# CROSSES one (the line-cross test is endpoint-exclusive). Find a real wall
		# cell + an adjacent open cell so the check runs against real data,
		# not a hardcoded guess.
		var wall := Vector2i(-1, -1)
		for cz in range(0, 149):
			for cx in range(0, 149):
				if nav.is_wall(float(cx) + 0.5, -(float(cz) + 0.5)):
					wall = Vector2i(cx, cz)
					break
			if wall.x >= 0:
				break
		_check(wall.x >= 0, "%s found a wall cell (%s)" % [code, wall])
		if wall.x >= 0:
			var open_cx := wall.x - 1
			if open_cx < 0 or nav.is_wall(float(open_cx) + 0.5, -(float(wall.y) + 0.5)):
				open_cx = wall.x + 1   # west neighbor is also wall (or off-grid): try east
			var wx := float(wall.x) + 0.5
			var wz := -(float(wall.y) + 0.5)
			var ox := float(open_cx) + 0.5
			runner.avatar_position = Vector3(ox, runner.ground_height(ox, wz), wz)
			_check(runner.step_blocked(wx, wz),
					"%s step into wall cell is blocked" % code)
			_check(not runner.step_blocked(ox, wz),
					"%s step to open ground is not blocked" % code)
	tool._toggle_run()
	# Camera handoff (F1): explore camera fov/projection must be restored
	# after a full Explore->Run->Explore round-trip, not left at the
	# runner's follow-cam fov (or stuck in ortho if we'd entered top-down).
	_check(is_equal_approx(cam.fov, pre_run_fov),
			"%s explore camera fov restored (%.2f == %.2f)" % [code, cam.fov, pre_run_fov])
	_check(cam.projection == pre_run_projection,
			"%s explore camera projection restored" % code)
	await _shot("%s_overview" % code)


func _shot(name: String) -> void:
	await process_frame
	await process_frame
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("%s/%s.png" % [SHOTS_DIR, name]))


func _check(cond: bool, label: String) -> void:
	if not cond:
		printerr("FAIL: " + label)
		_failures += 1
	else:
		print("ok: " + label)
