extends SceneTree
## Headless checks for TargetDummy — the C1.5 adapter that wraps an
## AvatarCharacter or MonsterCharacter behind one hit-reaction surface.
## Run: "$GODOT_BIN" --headless --path client --script scripts/tests/test_target_dummy.gd

var _fails := 0


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok: " + label)
	else:
		printerr("FAIL: " + label)
		_fails += 1


func _wait_ms(ms: int) -> void:
	var deadline := Time.get_ticks_msec() + ms
	while Time.get_ticks_msec() < deadline:
		await process_frame


func _init() -> void:
	# --- avatar kind ---
	var d := TargetDummy.new()
	get_root().add_child(d)
	_check(d.kind == "", "fresh dummy has no kind")
	_check(d.root() == null, "fresh dummy has no root")
	_check(d.setup_avatar("female"), "setup_avatar(female)")
	await process_frame
	await process_frame
	_check(d.kind == "avatar", "kind avatar")
	var av := d.root() as AvatarCharacter
	_check(av != null, "root is AvatarCharacter")
	_check(av.current_animation() != "", "avatar dummy idles (basic stand)")
	var idle_clip := av.current_animation()

	d.play_hit(19)
	await process_frame
	_check(av.current_animation() != idle_clip, "hit motion 19 plays")
	# hit is a one-shot with NO stance — TargetDummy must re-idle on finish
	var deadline := Time.get_ticks_msec() + 4000
	while av.current_animation() != idle_clip and Time.get_ticks_msec() < deadline:
		await process_frame
	_check(av.current_animation() == idle_clip, "dummy returns to idle after hit")

	var att := d.get_bone_attachment("@Spine3")
	_check(att != null, "avatar dummy exposes bone attachments")

	# --- monster kind (rebuild in place) ---
	_check(d.setup_monster("ct0001"), "setup_monster(ct0001)")
	await process_frame
	await process_frame
	_check(d.kind == "monster", "kind monster")
	var mc := d.root() as MonsterCharacter
	_check(mc != null, "root is MonsterCharacter")
	_check(mc.get_current_animation() == "ct0001_stand", "monster dummy idles on stand")
	_check(d.get_bone_attachment("@Spine3") == null, "monster dummy has no avatar-rig bones")

	d.play_hit(19)
	await process_frame
	_check(mc.get_current_animation() == "ct0001_hit1", "hit maps to {id}_hit1")
	deadline = Time.get_ticks_msec() + 6000
	while mc.get_current_animation() != "ct0001_stand" and Time.get_ticks_msec() < deadline:
		await process_frame
	_check(mc.get_current_animation() == "ct0001_stand", "monster returns to stand after hit")

	# --- teardown ---
	d.clear()
	_check(d.kind == "" and d.root() == null, "clear() empties the dummy")

	if _fails == 0:
		print("ALL OK")
	else:
		printerr("%d FAILURES" % _fails)
	quit(1 if _fails else 0)
