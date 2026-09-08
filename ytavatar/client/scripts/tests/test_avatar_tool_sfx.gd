extends SceneTree
## Run: "$GODOT_BIN" --path client --headless --script scripts/tests/test_avatar_tool_sfx.gd
## Headless wiring checks for the Skills dock's SFX tab (C2, spec §4.6).

var _fails := 0


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok - ", label)
	else:
		_fails += 1
		printerr("FAIL - ", label)


func _wait_ms(ms: int) -> void:
	var deadline := Time.get_ticks_msec() + ms
	while Time.get_ticks_msec() < deadline:
		await process_frame


func _init() -> void:
	var scene := load("res://scenes/avatar_tool.tscn") as PackedScene
	var tool_node = scene.instantiate()
	get_root().add_child(tool_node)
	for i in 5:
		await process_frame

	_check(tool_node.sfx_list != null and tool_node.sfx_list.item_count == 154, "SFX tab lists all 154 effects")
	_check(tool_node.skill_tabs.get_tab_title(2) == "SFX", "third tab is SFX")

	_check(tool_node._play_sfx("sfx_common_particledot1_red", true), "browser plays an emitter")
	await _wait_ms(300)
	var obj: SfxObject = tool_node._sfx_active
	_check(obj != null and is_instance_valid(obj) and obj.particle_count() > 0, "browser effect ticks and emits")
	_check(tool_node.sfx_status_label.text.contains("emitter"), "status line names the kind")

	# playing a skill stops the browser effect
	tool_node._play_skill("sk100001")
	_check(tool_node._sfx_active == null, "playing a skill stops the browser effect")
	tool_node.skill_player.stop()

	# loop: the object restarts every total_time
	_check(tool_node._play_sfx("sfx_common_condition_aging_billboard", false), "browser plays a billboard")
	tool_node.sfx_loop_check.button_pressed = true
	var bb: SfxObject = tool_node._sfx_active
	await _wait_ms(1300)   # total_time 1.0 -> at least one loop restart
	_check(is_instance_valid(bb) and bb.relative_time < 0.9, "loop restarts the clock after total_time")
	tool_node._stop_sfx()
	_check(tool_node._sfx_active == null, "stop clears the active effect")

	# filter (substring of the NAME — "billboard" is a naming convention here, not the kind)
	tool_node._on_sfx_filter_changed("billboard")
	_check(tool_node.sfx_list.item_count > 0 and tool_node.sfx_list.item_count < 154, "filter narrows the list (%d)" % tool_node.sfx_list.item_count)

	# --- "Hide character" (2026-09-07 browse-pass request): the raw .sfd has
	# no actor/target binding, so on the SFX tab the caster and the target
	# dummy are hidden by default and the effect plays alone at the anchor.
	tool_node.skill_tabs.current_tab = 1
	await process_frame
	_check(tool_node._current_character().visible, "character visible on the All tab")
	tool_node.skill_tabs.current_tab = 2
	await process_frame
	_check(tool_node.sfx_hide_check != null and tool_node.sfx_hide_check.button_pressed, "SFX tab hides the character by default")
	_check(not tool_node._current_character().visible, "character hidden on the SFX tab")
	_check(not tool_node._ground_plane.visible and tool_node._sfx_gizmo.visible, "SFX tab swaps the ground plane for the axes gizmo")
	_check(tool_node._sfx_gizmo.global_transform.is_equal_approx(tool_node._current_character().global_transform), "gizmo sits on the effect anchor (character frame)")
	tool_node._on_target_mode_selected(1)
	await process_frame
	_check(tool_node.target_dummy != null and not tool_node.target_dummy.visible, "target dummy set on the SFX tab is hidden too")
	tool_node._switch_gender()
	await process_frame
	_check(not tool_node._current_character().visible, "rebuilt avatar (gender switch) stays hidden on the SFX tab")
	tool_node.sfx_hide_check.button_pressed = false
	await process_frame
	_check(tool_node._current_character().visible and tool_node.target_dummy.visible, "unticking Hide shows caster and dummy")
	tool_node.sfx_hide_check.button_pressed = true
	tool_node.skill_tabs.current_tab = 1
	await process_frame
	_check(tool_node._current_character().visible and tool_node.target_dummy.visible, "leaving the SFX tab shows caster and dummy")
	_check(tool_node._ground_plane.visible and not tool_node._sfx_gizmo.visible, "leaving the SFX tab restores the ground plane and hides the gizmo")
	tool_node._on_target_mode_selected(0)
	tool_node.skill_tabs.current_tab = 2
	await process_frame

	# --- Trackpad gestures over the dock must not reach the camera
	# (2026-09-07 report: two-finger scrolling the SFX list pitched the
	# camera). Wheel/button events over a Control are marked handled by the
	# viewport; pan/magnify gestures are not, so the tool hit-tests the dock.
	var list_pos: Vector2 = tool_node.sfx_list.get_global_rect().get_center()
	_check(tool_node._dock_covers(list_pos), "the SFX list lies inside a dock panel")
	var pitch0: float = tool_node.camera_angle_y
	var dist0: float = tool_node.camera_distance
	var pan := InputEventPanGesture.new()
	pan.position = list_pos
	pan.delta = Vector2(0, 5)
	Input.parse_input_event(pan)
	var mag := InputEventMagnifyGesture.new()
	mag.position = list_pos
	mag.factor = 1.2
	Input.parse_input_event(mag)
	await process_frame
	_check(tool_node.camera_angle_y == pitch0, "pan gesture over the SFX list leaves the camera pitch alone")
	_check(tool_node.camera_distance == dist0, "magnify gesture over the SFX list leaves the camera distance alone")
	# midway between the left panel and the skills dock (window width varies headless vs windowed)
	var view_x: float = (tool_node.left_panel.get_global_rect().end.x + tool_node._dock_panels[2].get_global_rect().position.x) * 0.5
	var view_pos := Vector2(view_x, list_pos.y)
	_check(not tool_node._dock_covers(view_pos), "the 3D view lies outside every dock panel")
	var pan2 := InputEventPanGesture.new()
	pan2.position = view_pos
	pan2.delta = Vector2(0, 5)
	Input.parse_input_event(pan2)
	await process_frame
	_check(tool_node.camera_angle_y != pitch0, "pan gesture over the 3D view still orbits the camera")

	print("FAILED: %d" % _fails if _fails else "ALL OK")
	quit(1 if _fails else 0)
