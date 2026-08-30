extends SceneTree
## Headless checks for the avatar tool's Target row (C1.5): dummy
## lifecycle, placement, SkillPlayer wiring, mode/gender interactions.
## Run: "$GODOT_BIN" --headless --path client --script scripts/tests/test_avatar_tool_target.gd

var _fails := 0


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok: " + label)
	else:
		printerr("FAIL: " + label)
		_fails += 1


func _init() -> void:
	var scene := load("res://scenes/avatar_tool.tscn") as PackedScene
	var tool_node = scene.instantiate()
	get_root().add_child(tool_node)
	for i in 5:
		await process_frame

	_check(tool_node.target_dummy == null or tool_node.target_dummy.kind == "",
			"starts with no target")

	# Avatar target
	tool_node._on_target_mode_selected(1)
	for i in 3:
		await process_frame
	_check(tool_node.target_dummy != null and tool_node.target_dummy.kind == "avatar",
			"avatar dummy spawns")
	_check(tool_node.target_dummy.root().gender != tool_node._avatar.gender,
			"dummy is the opposite gender")
	var dp: Vector3 = tool_node.target_dummy.position
	_check(dp.distance_to(Vector3(0, 0, 2.5)) < 0.01, "dummy at 2.5m (got %s)" % dp)
	_check(tool_node.camera_pivot.position.is_equal_approx(Vector3(0, 1.0, 1.25)),
			"camera pivot moves to caster/dummy midpoint (got %s)" % tool_node.camera_pivot.position)
	_check(tool_node.camera_distance >= 4.5,
			"camera zooms out to fit both (got %.2f)" % tool_node.camera_distance)
	_check(tool_node.skill_player._target == tool_node.target_dummy,
			"skill_player wired to the dummy")

	# Gender switch rebuilds the dummy opposite
	tool_node._switch_gender()
	for i in 5:
		await process_frame
	_check(tool_node.target_dummy != null \
			and tool_node.target_dummy.root().gender != tool_node._avatar.gender,
			"gender switch keeps dummy opposite")

	# Monster target
	tool_node._on_target_mode_selected(2)
	for i in 5:
		await process_frame
	_check(tool_node.target_dummy.kind == "monster", "monster dummy spawns")

	# None removes + unwires
	tool_node._on_target_mode_selected(0)
	for i in 3:
		await process_frame
	_check(tool_node.target_dummy == null or tool_node.target_dummy.kind == "",
			"None clears the dummy")
	_check(tool_node.skill_player._target == null, "skill_player unwired")
	_check(tool_node.camera_pivot.position.is_equal_approx(Vector3(0, 1.0, 0)),
			"camera pivot restored on None (got %s)" % tool_node.camera_pivot.position)
	_check(absf(tool_node.camera_distance - 3.0) < 0.01,
			"camera distance restored on None (got %.2f)" % tool_node.camera_distance)

	# Removing the dummy mid-skill stops the skill immediately (finding 2):
	# without skill_player.stop() in _clear_target_dummy, the wrapper dies
	# with the dummy and animation_finished never fires, stalling teardown
	# until the 4s failsafe.
	tool_node._on_target_mode_selected(1)
	for i in 3:
		await process_frame
	tool_node.skill_player.play("sk010101", tool_node._avatar)
	tool_node._on_target_mode_selected(0)
	_check(tool_node.skill_player.current_frame() == -1,
			"clearing the dummy mid-skill stops the session immediately")

	# Monster picker visibility on revert to None (finding 3). Forcing a
	# real setup_monster() failure isn't reachable through this UI path in
	# a test, so this pins the simpler regression: from monster state, the
	# picker must not stay visible after reverting to None (previously a
	# deferred cosmetic — a failed-setup revert left it shown).
	tool_node._on_target_mode_selected(2)
	for i in 3:
		await process_frame
	tool_node._on_target_mode_selected(0)
	for i in 3:
		await process_frame
	_check(not tool_node.target_monster_option.visible,
			"monster picker hides after reverting to None")

	# Monster mode hides the row (dummy is avatar-mode only)
	tool_node._on_target_mode_selected(1)
	for i in 3:
		await process_frame
	tool_node._on_character_selected(2)   # CharacterMode.MONSTER
	for i in 5:
		await process_frame
	_check(tool_node.target_dummy == null or tool_node.target_dummy.kind == "",
			"entering monster mode clears the dummy")
	_check(not tool_node.target_row.visible, "target row hidden in monster mode")

	if _fails == 0:
		print("ALL OK")
	else:
		printerr("%d FAILURES" % _fails)
	quit(1 if _fails else 0)
