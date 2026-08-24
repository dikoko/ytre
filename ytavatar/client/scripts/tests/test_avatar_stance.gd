extends SceneTree
## Headless checks for AvatarCharacter motion-id playback + stance.
## Run: "$GODOT_BIN" --path client --headless --script scripts/tests/test_avatar_stance.gd

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
	var av := AvatarCharacter.new()
	av.gender = "female"
	get_root().add_child(av)
	await process_frame            # _ready builds the avatar
	await process_frame

	_check(av.has_motion_id(10101), "has_motion_id 10101")
	_check(not av.has_motion_id(99999), "no motion 99999")
	_check(av.play_motion_id(10101), "play_motion_id returns true")
	_check(not av.play_motion_id(99999), "missing id returns false, no crash")
	_check(av.is_animation_playing(), "one-shot playing")

	# dedupe suffix resolution: 40030 must resolve to the '...ho2' clip
	_check(av.play_motion_id(40030), "collision id 40030 resolves")

	# stance: set -> stand clip loops; one-shot returns to stance when done
	av.set_stance(30111, 30112)    # glorb boxing
	await process_frame
	_check(av.is_animation_playing(), "stance playing")
	_check(av.current_animation() == "feglorb_boxing_stand", "stance stand clip active")

	var finished := [false]
	var finished_name := [""]
	av.animation_finished.connect(func(n): finished[0] = true; finished_name[0] = n)
	av.play_motion_id(30101)       # boxing attack1, one-shot
	_check(av.current_animation() == "feglorb_boxing_attack1", "one-shot attack clip active")

	var deadline := Time.get_ticks_msec() + 3000
	while not finished[0] and Time.get_ticks_msec() < deadline:
		await process_frame
	_check(finished[0], "one-shot finished signal fired")
	_check(finished_name[0] == "feglorb_boxing_attack1", "finished signal reports the one-shot clip name")
	# after the one-shot ends the stand clip must be playing again
	await process_frame
	_check(av.is_animation_playing(), "still playing after one-shot")
	_check(av.current_animation() == "feglorb_boxing_stand", "returned to stance after one-shot")

	av.clear_stance()
	await process_frame
	_check(av.current_animation() == "febasic_stand", "clear_stance returns to basic stand")

	# bone attachments
	var sw := av.get_bone_attachment("@Sword")
	_check(sw != null and sw.get_parent() != null, "sword bone attachment")
	_check(av.get_bone_attachment("@Sword") == sw, "attachment cached")
	_check(av.get_bone_attachment("@NoSuchBone") == null, "missing bone -> null")

	av.free()

	if _fails == 0:
		print("ALL OK")
	quit(0 if _fails == 0 else 1)
