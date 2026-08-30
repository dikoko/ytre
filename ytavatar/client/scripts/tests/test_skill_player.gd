extends SceneTree
## Run: "$GODOT_BIN" --headless --path client --script scripts/tests/test_skill_player.gd
##
## Polling uses real wall-clock deadlines (Time.get_ticks_msec()), not an
## iteration-count proxy for elapsed time: this headless engine's idle loop
## runs well north of 60fps with no throttle, so "N awaits ~= N/60 seconds"
## under-counts real elapsed time badly here and would make the finding-1
## timing regression (below) unreliable.

var _fails := 0
## Shared player instance for the Task 6 tests below (_test_motion_by_id,
## _test_play_reason, _test_glow_loop, _test_bone_anchor) — set from
## _init() right after the SkillPlayer is created/cataloged, mirroring the
## rest of this file's single-instance-per-run convention (the existing
## checks all run against the local `sp` in _init(); `player` is that same
## instance, just reachable from the standalone test funcs too).
var player: SkillPlayer


## Duck-typed stand-in for AvatarCharacter: `play_motion_id` records what
## it was asked to play instead of touching a real AnimationPlayer, and
## reports the same "false on unknown id" contract the real character does
## (avatar_character.gd's play_motion_id, id 99999 standing in for "not in
## motion_ids.json").
class StubCharacter:
	extends Node3D
	var played_ids: Array = []

	func play_motion_id(id: int, _loop := false) -> bool:
		played_ids.append(id)
		return id != 99999


## Adds a duck-typed get_bone_attachment on top of StubCharacter: always
## returns the one pre-made BoneAttachment3D under a real Skeleton3D
## regardless of the requested bone name (the brief's "simpler and more
## honest" option — a real AvatarCharacter is only exercised windowed, in
## skill_eval.gd).
class StubSkeletonCharacter:
	extends Node3D
	var played_ids: Array = []
	var _att: BoneAttachment3D

	func play_motion_id(id: int, _loop := false) -> bool:
		played_ids.append(id)
		return id != 99999

	func set_attachment(att: BoneAttachment3D) -> void:
		_att = att

	func get_bone_attachment(_bone_name: String) -> BoneAttachment3D:
		return _att


## Duck-typed TargetDummy stand-in: records hits; bone attachment optional.
class StubDummy:
	extends Node3D
	var hits: Array = []
	var _att: BoneAttachment3D = null
	var kind := "avatar"

	func play_hit(mid: int) -> void:
		hits.append(mid)

	func root() -> Node3D:
		return self

	func set_attachment(att: BoneAttachment3D) -> void:
		_att = att

	func get_bone_attachment(_bone_name: String) -> BoneAttachment3D:
		return _att


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


func _wait_finished_or(seconds: float) -> void:
	## Waits for the shared `player`'s one-shot session to go idle
	## (current_frame() back to -1, i.e. stop()/_finish() already ran) or
	## for `seconds` to elapse, whichever comes first — the Task 6 tests'
	## equivalent of this file's existing `finished`-signal wait loops,
	## expressed via the new current_frame() API instead of a fresh signal
	## connection per call site.
	var deadline := Time.get_ticks_msec() + int(seconds * 1000.0)
	while player.current_frame() >= 0 and Time.get_ticks_msec() < deadline:
		await process_frame


func _make_stub_character() -> StubCharacter:
	var stub := StubCharacter.new()
	root.add_child(stub)
	return stub


func _make_skeleton_stub(bone_names: Array) -> StubSkeletonCharacter:
	var stub := StubSkeletonCharacter.new()
	root.add_child(stub)
	var skel := Skeleton3D.new()
	stub.add_child(skel)
	for n in bone_names:
		var idx := skel.add_bone(String(n))
		skel.set_bone_rest(idx, Transform3D.IDENTITY)
	var att := BoneAttachment3D.new()
	att.bone_name = String(bone_names[0])
	skel.add_child(att)
	stub.set_attachment(att)
	return stub


func _test_motion_by_id() -> void:
	# sk010101 track: {kind:"motion", name:"female.mlib",
	#   params:{character_type:257, motion_id:10101}} — actor role (0x100)
	# plus two ct000x tracks with character_type 534/1046 — target roles,
	# skipped until a target dummy exists (C1 out of scope).
	var stub := _make_stub_character()
	_check(player.play("sk010101", stub), "sk010101 plays")
	await _wait_finished_or(3.0)
	_check(stub.played_ids == [10101], "actor motion by id; target motions skipped")
	stub.free()


func _test_play_reason() -> void:
	var stub := _make_stub_character()
	_check(player.play_ex("nope", stub) == SkillPlayer.PlayResult.UNKNOWN, "unknown code")
	_check(player.play_ex("sk010101", null) == SkillPlayer.PlayResult.NO_CHARACTER, "null character")
	stub.free()


func _test_glow_loop() -> void:
	var stub := _make_stub_character()
	_check(player.play_loop("sk610015", stub), "glow loop starts")
	_check(player.is_looping(), "is_looping")
	# a one-shot on top must not kill the loop
	_check(player.play("sk010101", stub), "one-shot over loop")
	await _wait_finished_or(3.0)
	_check(player.is_looping(), "loop survives one-shot finish")
	player.stop_loop()
	_check(not player.is_looping(), "stop_loop")
	stub.free()


func _test_bone_anchor() -> void:
	# stub with a real Skeleton3D + a bone named "@Sword"; sk610015 (like
	# sk610011) is a single-tmd-track glow whose base command is
	# {base_bone:7, base_character:256, inherit_rot:true} — sk610015 is
	# used here instead of the brief's sk610011 because sk610011's shipped
	# GLB (sfx_weapon_blade_A0011.glb) fails to import in this checkout
	# ("Index material = 0 is out of bounds (p_state->materials.size() = 0)",
	# a pre-existing exporter/asset bug outside skill_player.gd's scope —
	# confirmed via a direct load() repro, not a SkillPlayer defect);
	# sk610015's GLB loads cleanly and the catalog shape is identical.
	# Fetched via player._wrappers (this file already pokes at `sp._catalog`
	# above, so reaching into a tracked-wrapper array for the same reason —
	# the wrapper reparents onto the bone attachment, so it stops being a
	# child of `player` at all; get_child()-on-player can't find it anymore).
	var stub := _make_skeleton_stub(["@Sword"])
	_check(player.play("sk610015", stub), "glow plays on skeleton stub")
	var wrapper: Node3D = player._wrappers[player._wrappers.size() - 1] as Node3D
	_check(wrapper != null and wrapper.get_parent() != player, "wrapper parented under bone attachment")
	player.stop()
	stub.free()


func _test_target_routing() -> void:
	# sk010101: actor motion 10101 + TWO non-actor motion tracks — target
	# (character_type 534 = 0x216) and other (1046 = 0x416) — both request
	# motion id 19 at frame 15 (verified via skills.json; see the existing
	# _test_motion_by_id comment above, which already notes "two ct000x
	# tracks"). Both route to the single dummy (spec §4's single-dummy
	# simplification), so the dummy sees TWO hits, not one.
	var stub := StubCharacter.new()
	root.add_child(stub)
	var dummy := StubDummy.new()
	root.add_child(dummy)

	# 1) null-target regression: exact current behavior
	player.set_target(null)
	_check(player.play("sk010101", stub), "routing: plays with null target")
	await _wait_finished_or(4.0)
	_check(stub.played_ids == [10101], "routing: null target — target motion still skipped")

	# 2) with target: hit routed to dummy, caster motion untouched
	stub.played_ids.clear()
	player.set_target(dummy)
	_check(player.play("sk010101", stub), "routing: plays with target set")
	await _wait_finished_or(4.0)
	_check(stub.played_ids == [10101], "routing: caster still plays only its own motion")
	_check(dummy.hits == [19, 19], "routing: both non-actor tracks' motion 19 reached the dummy")

	# 3) target-anchored effect: sk040009's frame-0 tmd track anchors
	#    base_character=512 (0x200, non-actor) at base_bone=1 (a real bone,
	#    not 11/Local) — verified via a python read of skills.json (the
	#    brief's suggested sk020014 does NOT fit: its only frame-0 tmd base
	#    command is base_character=256, i.e. ACTOR role, and its one 0x200
	#    base command uses bone 11/Local, which anchors at the dummy ROOT
	#    rather than a bone attachment; sk040009 has a genuine early 0x200 +
	#    real-bone base command, so it exercises the bone-attachment path
	#    the brief describes). Give the dummy a real skeleton attachment;
	#    the wrapper must land under it (not under the player, not under
	#    the caster).
	var skel := Skeleton3D.new()
	dummy.add_child(skel)
	var att := BoneAttachment3D.new()
	skel.add_child(att)
	dummy.set_attachment(att)
	_check(player.play("sk040009", stub), "routing: sk040009 plays")
	await _wait_ms(300)
	var found_under_dummy := false
	for w in att.get_children():
		if String(w.name).begins_with("SkillFx_"):
			found_under_dummy = true
	_check(found_under_dummy, "routing: target-anchored wrapper parented under dummy bone")
	player.stop()

	# 4) freed-dummy safety: set, free, play — must not crash, must skip
	var dummy2 := StubDummy.new()
	root.add_child(dummy2)
	player.set_target(dummy2)
	dummy2.free()
	stub.played_ids.clear()
	_check(player.play("sk010101", stub), "routing: plays after target freed")
	await _wait_finished_or(4.0)
	_check(stub.played_ids == [10101], "routing: freed target degrades to skip")

	# 5) precedence: an explicit target_character (glow-loop path) always
	#    wins over a set dummy, even for a non-actor-role base command —
	#    direct _bind_wrapper unit check (fix round 1 code review finding:
	#    the dummy override must never silently discard an explicitly
	#    passed loop character). No shipped catalog entry currently pairs
	#    a loop/glow skill with a non-actor base command, so this exercises
	#    _bind_wrapper directly rather than through play_loop() — the same
	#    style this file already uses to poke at player._wrappers/_catalog.
	player.set_target(dummy)
	dummy.global_position = Vector3(0, 0, 0)
	var loop_char := StubCharacter.new()
	root.add_child(loop_char)
	loop_char.global_position = Vector3(5, 0, 0)  # distinct from dummy's
	# position, so a discarded target_character (bug) resolves the
	# wrapper at the dummy's origin instead and this assertion catches it
	var precedence_wrapper := Node3D.new()
	player.add_child(precedence_wrapper)
	player._bind_wrapper(precedence_wrapper, {"role": 512, "bone": 11}, loop_char)
	_check(precedence_wrapper.get_parent() == player,
			"routing: explicit target_character keeps the wrapper off the dummy's tree")
	_check(precedence_wrapper.global_position.is_equal_approx(loop_char.global_position),
			"routing: explicit target_character wins precedence over a set dummy")
	precedence_wrapper.queue_free()
	loop_char.queue_free()

	player.set_target(null)
	stub.queue_free()
	dummy.queue_free()


func _test_path_playback() -> void:
	# Hand-built catalog entry: one effect with a path command at frame 0,
	# flying 0 -> 4 units (authored +z, mirrored to -z) over 0.5 s.
	# Reuses a real effect model ref so the wrapper actually spawns.
	var params10: Array = []
	for i in 10:
		params10.append(float(i) / 9.0)
	player._catalog["zzpath"] = {
		"fps": 30.0, "frames": 30, "missing": [],
		"paths": [{
			"input_points": [[0.0, 0.0, 0.0], [0.0, 0.0, 4.0]],
			"parameters": params10,
			"base_character": 256, "base_bone": 11,
			"target_character": 512, "target_bone": 11,
		}],
		"tracks": [{
			"kind": "tmd", "name": "sfx_a_SWAball01.TMD",
			"commands": [
				{"frame": 0, "kind": "play", "params": {}},
				{"frame": 0, "kind": "path",
					"params": {"path_id": 0, "play_time": 0.5}},
			],
		}],
	}
	var stub := StubCharacter.new()
	get_root().add_child(stub)
	var dummy := StubDummy.new()
	get_root().add_child(dummy)
	dummy.position = Vector3(0, 0, 3)
	player.set_target(dummy)

	_check(player.play("zzpath", stub), "path: zzpath plays")
	var wrapper: Node3D = null
	for w in player._wrappers:
		wrapper = w
	_check(wrapper != null, "path: wrapper spawned")
	var start_pos: Vector3 = wrapper.global_position
	await _wait_ms(250)
	var mid_pos: Vector3 = wrapper.global_position
	_check(mid_pos.distance_to(start_pos) > 0.3,
			"path: wrapper moved mid-flight (%.2f)" % mid_pos.distance_to(start_pos))
	await _wait_ms(400)
	var end_pos: Vector3 = wrapper.global_position
	_check(end_pos.distance_to(dummy.position) < 1.2,
			"path: wrapper holds near the target after play_time (got %s)" % end_pos)
	player.stop()

	# No-dummy variant: base-only frame — flies from the caster along its
	# own forward, must still MOVE (the original client flies base-only paths).
	player.set_target(null)
	_check(player.play("zzpath", stub), "path: plays without dummy")
	var wrapper2: Node3D = null
	for w in player._wrappers:
		wrapper2 = w
	var start2: Vector3 = wrapper2.global_position
	await _wait_ms(300)
	_check(wrapper2.global_position.distance_to(start2) > 0.3,
			"path: base-only flight still animates")
	player.stop()
	player._catalog.erase("zzpath")
	stub.queue_free()
	dummy.queue_free()


func _test_catalog() -> void:
	var cat := SkillCatalog.new()
	_check(cat.load(), "catalog loads")
	_check(cat.skill_ids().size() == 742, "742 skills")
	_check(cat.family("sk040016") == "weapon_skill", "family weapon_skill")
	_check(cat.family("sk610011") == "glow", "family glow")
	var s := cat.skill_set_for_weapon("mura_A0011")
	_check(s.get("class", "") == "mura", "clarinets class")
	_check(int(s["stance"]["stand"]) == 50111, "clarinets stance")
	_check(int(s["base_attacks"][0]) == 50101, "clarinets attack1")
	_check(int(s["skills"][0]) == 60013, "clarinets named skill")
	_check(cat.skill_set_for_weapon("nope").is_empty(), "unknown weapon -> {}")
	_check(cat.bone_name(7) == "@Sword", "bone 7 sword")
	_check(cat.bone_name(11) == "", "bone 11 self")
	_check(SkillCatalog.code_for_id(60013) == "sk060013", "code_for_id")


func _init() -> void:
	await process_frame
	var sp := SkillPlayer.new()
	root.add_child(sp)
	sp.load_catalog()
	player = sp
	_check(sp.skill_ids().size() == 742, "catalog loads 742 skills")
	var info: Dictionary = sp.skill_info("sk100001")
	_check(info["fps"] == 30.0, "warp arrive fps")
	_check(info["missing"].is_empty(), "warp arrive fully resolvable")

	_test_catalog()

	var character := Node3D.new()
	root.add_child(character)

	# --- Natural playback + finding-1 regression -----------------------
	# A skill whose last authored event is a color flash or a sound (~50%
	# of the fleet) must hold that terminal effect on screen at least until
	# the catalog's declared frame count elapses — the pre-fix code gated
	# natural finish on the last COMMAND frame only, which for sk100001 is
	# frame 0, so it applied-then-instantly-reverted every frame-0 effect
	# in the same tick and fired `finished` almost immediately. Assert the
	# finish takes close to the full 60-frame/30fps = 2.0s budget.
	var done := [false]
	var finish_ms := [0]
	var play_start_ms := Time.get_ticks_msec()
	sp.finished.connect(func(_c): done[0] = true; finish_ms[0] = Time.get_ticks_msec())
	_check(sp.play("sk100001", character), "warp arrive playable")
	_check(sp.get_child_count() > 0, "effect wrapper spawned")
	var deadline := Time.get_ticks_msec() + 6000
	while not done[0] and Time.get_ticks_msec() < deadline:
		await process_frame
	_check(done[0], "finished signal fired")
	_check(sp.get_child_count() == 0, "teardown complete")
	var elapsed_s := float(finish_ms[0] - play_start_ms) / 1000.0
	# 1.5s, not 1.9s: the player's `_time += delta` engine clock runs
	# slightly ahead of this test's wall clock (Time.get_ticks_msec()) in
	# headless, so the 2.0s nominal budget reproducibly finishes at ~1.90-
	# 1.91s — under 100ms slack against a 1.9s floor, a latent CI/loaded-
	# machine flake (final-review finding, reproduced 2026-08-17). The
	# assertion only needs to tell "held the ~2.0s frame budget" apart from
	# the pre-fix regression signature (~0.03-0.5s, an instant apply-then-
	# revert in the same tick) — 1.5s keeps full discriminating power for
	# that while absorbing the drift.
	_check(elapsed_s >= 1.5,
			"natural finish held for the full catalog frame budget (%.2fs)" % elapsed_s)

	# --- Finding-3 regression --------------------------------------------
	# Unknown skill: play() returns false, never crashes.
	var broken_played := sp.play("sk999999", character)
	_check(not broken_played, "unknown skill refuses to play")

	# A resolvable-looking skill with a non-empty `missing` list must also
	# refuse to play outright (0/742 shipped entries hit this today, so
	# inject a synthetic one — mutating the loaded catalog dict directly).
	var synthetic: Dictionary = (sp.skill_info("sk100001") as Dictionary).duplicate(true)
	synthetic["missing"] = ["tmd:not_a_real_file.TMD"]
	sp._catalog["sk_broken_synthetic"] = synthetic
	var missing_played := sp.play("sk_broken_synthetic", character)
	_check(not missing_played, "skill with non-empty missing[] refuses to play")

	# --- Finding-2 regression --------------------------------------------
	# A stale failsafe timer from an earlier session must not kill a later
	# one. Play session 1, let it run well past its own natural finish
	# (its 4s-from-ITS-OWN-play() failsafe keeps ticking in the background
	# regardless), then start session 2 timed so the stale failsafe lands
	# squarely inside session 2's still-active window — exactly the case
	# the pre-fix code got wrong (global `_playing` alone can't tell a
	# stale timer from a legitimately still-running later session).
	_check(sp.play("sk100001", character), "session 1 (chain test) playable")
	await _wait_ms(3500)  # session 1 has long since finished naturally
	_check(sp.get_child_count() == 0, "session 1 torn down before session 2 starts")

	var done2 := [false]
	var code2 := [""]
	var finish2_ms := [0]
	sp.finished.connect(func(c): done2[0] = true; code2[0] = c; finish2_ms[0] = Time.get_ticks_msec())
	var session2_start_ms := Time.get_ticks_msec()
	_check(sp.play("sk100004", character), "session 2 playable")
	# Session 1's failsafe fires ~4.0s after ITS play() call — ~0.5s into
	# session 2's run here. `_code` is shared, single-instance state, so a
	# premature fire from the stale timer would still (mis)report the
	# CORRECT code ("sk100004") — the only thing that actually distinguishes
	# a stale-timer kill from session 2's own natural finish is TIMING: a
	# stale-timer kill lands at ~0.5s in, well short of the full ~2.0s
	# catalog-frame budget finding 1 pins.
	var deadline2 := Time.get_ticks_msec() + 8000
	while not done2[0] and Time.get_ticks_msec() < deadline2:
		await process_frame
	_check(done2[0], "session 2 finished on its own clock")
	_check(code2[0] == "sk100004", "finished signal reports session 2's code")
	var elapsed2_s := float(finish2_ms[0] - session2_start_ms) / 1000.0
	# See the finding-1 boundary above for why 1.5s, not 1.9s: same
	# engine-vs-wall-clock drift, same discriminating power (a stale-timer
	# kill would land at ~0.5s, far under either boundary).
	_check(elapsed2_s >= 1.5,
			"session 2 ran its own full budget, not cut short by session 1's stale failsafe (%.2fs)" % elapsed2_s)

	# --- Color-lerp regression (final-review finding 2) -------------------
	# The original client's color track is a temporal LERP from
	# the command's `self` (start) to `target` (end) material over
	# `total_frame/fps` seconds — NOT an instant snap to target, and the
	# dominant authored use (401/910 color commands across 267 skills) is
	# a DIFFUSE-ALPHA fade (target diffuse rgb is white fleet-wide), which
	# the pre-fix code never rendered at all (it read only `target.ambient`
	# and applied it instantly). sk200012 (real catalog entry, resolvable
	# refs) carries exactly this: frame 20 fades Diffuse.alpha 1.0->0.0
	# over 16 frames (16/30fps ~= 0.533s), so the fade completes ~1.20s
	# into playback and holds at 0 until the 60-frame/2.0s catalog budget
	# elapses. A bare Node3D has no MeshInstance3D for the color stash to
	# find (skill_eval.gd's own docstring notes this), so build a minimal
	# mesh character with a ShaderMaterial matching the avatar shader's
	# shape (shader_type spatial; a fragment() that assigns ALBEDO, closed
	# by a trailing "}") so the derived flash-shader variant's
	# `flash_color` uniform is directly inspectable.
	var mesh_char := Node3D.new()
	root.add_child(mesh_char)
	var mi := MeshInstance3D.new()
	mi.mesh = BoxMesh.new()
	var base_shader := Shader.new()
	base_shader.code = "shader_type spatial;\nrender_mode unshaded;\nvoid fragment() {\n\tALBEDO = vec3(1.0);\n}\n"
	var base_mat := ShaderMaterial.new()
	base_mat.shader = base_shader
	mi.material_override = base_mat
	mesh_char.add_child(mi)

	var color_done := [false]
	sp.finished.connect(func(_c): color_done[0] = true)
	_check(sp.play("sk200012", mesh_char), "color-fade skill (sk200012) playable")

	# Mid-fade (~0.95s: ~0.28s into the 0.533s fade that started at ~0.667s)
	# — must read a STRICTLY INTERIOR alpha, proving a progressing lerp,
	# not an instant snap to either endpoint. The pre-fix code would read
	# 1.0 here (it never touched diffuse alpha at all).
	await _wait_ms(950)
	var mid_mat := mi.material_override as ShaderMaterial
	var mid_ok := mid_mat != null and mid_mat.shader != base_shader \
			and mid_mat.get_shader_parameter("flash_color") != null
	_check(mid_ok, "color fade derived a flash-shader variant with flash_color set")
	var mid_alpha: float = mid_mat.get_shader_parameter("flash_color").a if mid_ok else -1.0
	_check(mid_alpha > 0.1 and mid_alpha < 0.9,
			"color fade mid-lerp alpha is strictly interior (%.3f), not snapped (pre-fix would read 1.0)" % mid_alpha)

	# Past the fade's own completion (~1.20s) but still mid-skill (catalog
	# holds to 2.0s) — must have reached the target (alpha ~0.0).
	await _wait_ms(400)  # now ~1.35s into playback
	var end_mat := mi.material_override as ShaderMaterial
	var end_alpha: float = end_mat.get_shader_parameter("flash_color").a if end_mat != null else -1.0
	_check(end_alpha < 0.05,
			"color fade reached its target alpha (%.3f), held past fade completion" % end_alpha)

	# Wait out the rest of the catalog's 2.0s budget for natural finish,
	# then assert EXACT restore: same material Object back, no leftover
	# flash-shader variant.
	var color_deadline := Time.get_ticks_msec() + 6000
	while not color_done[0] and Time.get_ticks_msec() < color_deadline:
		await process_frame
	_check(color_done[0], "color-fade session finished naturally")
	_check(mi.material_override == base_mat,
			"color-fade session restores the exact original material after finish")

	mesh_char.free()

	# --- Task 6: motion by id, play reasons, glow loop, bone anchoring -----
	await _test_motion_by_id()
	await _test_play_reason()
	await _test_glow_loop()
	await _test_bone_anchor()
	await _test_target_routing()
	await _test_path_playback()

	sp.free()
	character.free()
	print("FAILED: %d" % _fails if _fails else "ALL OK")
	quit(1 if _fails else 0)
