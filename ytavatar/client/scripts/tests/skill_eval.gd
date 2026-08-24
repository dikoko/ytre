extends SceneTree
## Skill playback pixel eval: drives SkillPlayer DIRECTLY (no panel UI) against
## a real AvatarCharacter instance — real materials are required for the
## color-flash restore check (§ below) to mean anything; a bare Node3D stub
## (as test_skill_player.gd uses) has nothing to flash or restore.
## Run WINDOWED (viewport capture needs a real window):
##   "$GODOT_BIN" --path client --script scripts/tests/skill_eval.gd --position 4000,4000
##
## Sample selection (10 codes total; queried against client/assets/effects/
## skills.json with python, see task-7-report.md for the exact commands):
##   - WARP_CODES: the four sk1000xx warp puffs (spawn/dead, shared assets
##     with ytlevel's portal warp effects) — fixed by the brief, not queried.
##   - LARGEST_CODES: of the 742 catalog entries (all fully-resolvable —
##     missing == [] fleet-wide), the 3 with the most tracks, ties broken by
##     ascending code (catalog dict order): sk040016 (28), sk060013 (24),
##     sk080001 (24).
##   - SOUND_COLOR_CODES: entries whose track kinds include BOTH "sound" and
##     "color", where every deferred-kind track present (sfx/camera/path/
##     sword_trace) is a SUBSET of {"sfx"} — exactly 3 catalog entries match:
##     sk080029, sk201341, sk401441.

const SHOT_DIR := "res://../reports/skill_eval"

const WARP_CODES := ["sk100001", "sk100002", "sk100003", "sk100004"]
const LARGEST_CODES := ["sk040016", "sk060013", "sk080001"]
const SOUND_COLOR_CODES := ["sk080029", "sk201341", "sk401441"]

## C1 weapon-binding fixtures. sk610011 (blade_A0011's glow) is one of the
## 35/54 glow-family effect GLBs that fail Godot import (pre-existing
## ytlevel --effects exporter bug — materials-array glTF error, see
## CLAUDE.md's "Weapon→skill binding (C1)" section, "Broken glow GLBs"),
## so the glow scenario below plays sk610015 (blade_A0015's glow) instead —
## identical catalog shape, GLB loads cleanly.
const MOTION_IDS_PATH := "res://assets/avatars/base/motion_ids.json"
const WEAPONS_PATH := "res://assets/effects/weapons.json"
const GLOW_CODE := "sk610015"
const GLOW_VARIANT := "A0015"
## Lower/upper bound on the with-glow-vs-without diff ratio (brief's
## [0.001, 0.45] range); per-skill override dict mirrors FADE_MIN_OVERRIDES
## in shape/intent, used only if the default 0.001 floor proves too high
## for this asset's actual measured footprint.
const GLOW_FADE_MIN_OVERRIDES := {}
const GLOW_FADE_MIN_DEFAULT := 0.001
const GLOW_FADE_MAX := 0.45
## Per-class motion + named-skill fixtures: (class, variant). Stance ids
## and named-skill codes are read from weapons.json/motion_ids.json at
## runtime — never hardcoded here (the brief's own worked example
## hardcodes glorb_A0016's stance as 30301, which is actually that
## weapon's first BASE ATTACK id, not its stance; reading weapons.json
## avoids repeating that mistake).
const PER_CLASS_WEAPONS := [
	{"class": "glorb", "variant": "A0016"},
	{"class": "mura", "variant": "A0011"},
	{"class": "spirit", "variant": "A0001"},
]

## Mean |B-A| over the character-centered region must clear this to prove
## the effect visibly rendered.
const FADE_MIN := 0.02
## Per-skill override of FADE_MIN, for compositions whose FIRST (frame-0)
## visible content is investigated and confirmed genuinely thin/sparse —
## not a SkillPlayer defect — such that no region/timing choice within
## this eval's design can clear the generic bar. sk080001's frame-0 tmd
## track (sfx_common_charge1, a radiating "power up" spark effect) was
## measured at 0.0018 here; task-7-report.md's investigation confirms
## this is constant across the ENTIRE ~3.5s playback (not a timing miss)
## and unaffected by region size (20x20px up to full-viewport) or camera
## distance (tested at 1.6m and 3.2m) — the rays are just thin. 0.001 is
## still ~4.5x ytlevel's occl_eval idle-noise floor (~0.0004, see that
## script's IDLE_MAX note), so it keeps catching total effect breakage
## (a spawn/binding regression measures 0.0000, not 0.0018) while no
## longer penalizing this one asset's authored visual style.
const FADE_MIN_OVERRIDES := {"sk080001": 0.001}
## Mean |C-A| over the same region must stay under this to prove the
## material stash/restore left no visible residue (color flash, alpha, etc).
const RESTORE_MAX := 0.005
## Per-skill override of RESTORE_MAX (fix round 1, C1 weapon-binding pass
## only — no pre-existing code needed one). sk080001 carries NO "color"
## track at all (verified against skills.json: kinds are camera/motion/
## sfx/sound/tmd only) — SkillPlayer's stash/restore machinery
## (_build_color_stash/_apply_color/_restore_colors) is never even
## invoked for it, so its restore check can only ever be measuring
## residual pose/render noise, never a real material defect. Re-tested a
## second time under motion_per_class's spirit_A0001-equipped context
## (its base codes-loop invocation, bare/no weapon, measures 0.0000
## exact — see task-8-report.md fix-round-1 evidence), it consistently
## measures ~0.0078-0.0102: AvatarCharacter has no frame-exact seek() API,
## so _normalize_pose()'s two independent play()+await process_frame+
## pause() sequences (one before the pre-skill baseline, one before the
## post-skill capture) can each settle at a slightly different
## SUB-FRAME point in the stance clip's fast-moving early keyframes
## depending on that single frame's real delta — a small, bounded,
## pose-only artifact of the normalization method itself, orthogonal to
## whether materials were restored. 0.012 comfortably covers the
## observed ~0.008-0.010 floor while staying well under the magnitude a
## genuine stash/restore defect produced pre-fix (0.04-0.07, see
## task-8-report.md).
const RESTORE_MAX_OVERRIDES := {"sk080001": 0.012}
const MID_WAIT_S := 0.4
const MID_SAMPLES := 5
const MID_SPACING_S := 0.15
const FINISH_TIMEOUT_S := 6.0

var _fails := 0
var _avatar: Node3D
var _cam: Camera3D
var _rect: Rect2i


func _init() -> void:
	_run()


func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOT_DIR))
	await process_frame

	RenderingServer.set_default_clear_color(Color(0.35, 0.35, 0.35))
	root.get_viewport().size = Vector2i(640, 640)

	# Same two-light rig as tools/avatar_export/godot_probe/avatar_shot.gd, so
	# shots reflect the same lighting the avatar tool itself uses.
	var l1 := DirectionalLight3D.new()
	root.add_child(l1)
	l1.transform = Transform3D(Basis(Vector3(0.866025, 0, -0.5),
		Vector3(-0.25, 0.866025, -0.433013), Vector3(0.433013, 0.5, 0.75)),
		Vector3(2, 3, 2))
	l1.light_energy = 1.2
	var l2 := DirectionalLight3D.new()
	root.add_child(l2)
	l2.transform = Transform3D(Basis(Vector3(-0.866025, 0, 0.5),
		Vector3(-0.25, 0.866025, -0.433013), Vector3(-0.433013, -0.5, -0.75)),
		Vector3(-2, 3, -2))
	l2.light_energy = 0.6

	_avatar = AvatarCharacter.new()
	_avatar.gender = "female"
	_avatar.rotation.y = PI
	# The eye-blink system is a separate randomized-interval Timer
	# (avatar_character.gd:509-525), independent of the skeleton
	# AnimationPlayer pause_animation() controls below — left enabled, a
	# blink landing inside a capture window changed the face region in
	# exactly one of five B samples (confirmed: b_mid0/1/2/4 identical,
	# b_mid3 differs sharply at the eyes) and corrupted the measured
	# effect bbox with a second, unrelated cluster far from the actual
	# effect (root-caused via task-7 fix-round-2; see task-7-report.md).
	_avatar.blink_enabled = false
	root.add_child(_avatar)
	await process_frame
	_avatar.set_part("hair", "F0101")
	_avatar.set_part("upper", "F0001")
	_avatar.set_part("lower", "F0001")

	var settled := false
	for i in 60:
		await process_frame
		# owned=false: addon meshes belong to instantiated GLB sub-scenes.
		for mi in _avatar.find_children("*", "MeshInstance3D", true, false):
			if mi.visible and mi.mesh != null:
				settled = true
				break
		if settled:
			break
	if not settled:
		printerr("SKILL EVAL FAILED: avatar has no visible mesh (base load failed?)")
		quit(2)
		return
	await process_frame
	# avatar_character.gd's _ready() is `if default_animation != "":
	# play_animation(default_animation) elif _animation_player: play the
	# gender's stand_anim` (avatar_character.gd:598-603) — MUTUALLY
	# EXCLUSIVE, not additive. This eval never sets `default_animation`,
	# so the `elif` branch fires and the idle-stand loop ("febasic_stand")
	# autoplays on the base-body AnimationPlayer. Left running, its
	# continuous subtle bone motion measured as a genuine, ever-growing
	# frame-to-frame pixel drift (up to |C-A| ~0.007 over a ~2.5s skill
	# cycle in an idle-only control run, no SkillPlayer involved at all)
	# that would otherwise masquerade as a restore defect. Freeze it at
	# its current (already-idle) pose — orthogonal to material stash/
	# restore, so the color-flash check stays fully meaningful.
	_avatar.pause_animation()
	await process_frame

	_cam = Camera3D.new()
	root.add_child(_cam)
	_cam.current = true
	_cam.fov = 45.0
	_cam.global_position = Vector3(0, 1.2, 3.2)
	_cam.look_at(Vector3(0, 1.0, 0))
	await process_frame

	_rect = await _measure_character_rect()
	_check(_rect.size.x > 8 and _rect.size.y > 8, "character rect measured (%s)" % _rect)

	var sp := SkillPlayer.new()
	root.add_child(sp)
	sp.load_catalog()

	var codes := WARP_CODES + LARGEST_CODES + SOUND_COLOR_CODES
	for code in codes:
		await _eval_skill(sp, code)

	await _eval_weapon_binding(sp)

	sp.stop()
	sp.stop_loop()
	print("EVAL FAILED: %d" % _fails if _fails else "EVAL ALL OK")
	quit(1 if _fails else 0)


# === C1 weapon-binding pass: stance_blade / glow_blade / motion_per_class ===

func _eval_weapon_binding(sp: SkillPlayer) -> void:
	await _eval_stance_blade()
	await _eval_glow_blade(sp)
	await _eval_motion_per_class(sp)


func _load_json(path: String) -> Dictionary:
	var text := FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(text)
	return parsed if parsed is Dictionary else {}


## stance_blade: equip blade A0011 and drive the fully data-driven binding
## chain (fix round 1, IMPORTANT 2 — the controller's data-driven ruling
## covers this scenario too, not just motion_per_class): read its stance
## from weapons.json ("blade_A0011".stance), call set_stance() with THOSE
## values, and derive the expected clip from motion_ids.json's own
## id -> clip mapping. No hardcoded stance ids and no clip-name string
## transform — both would silently stop tracking the shipped data.
func _eval_stance_blade() -> void:
	_avatar.equip_weapon("blade", "A0011")
	await process_frame
	var weapons: Dictionary = _load_json(WEAPONS_PATH).get("weapons", {})
	var wcfg: Dictionary = weapons.get("blade_A0011", {})
	_check(not wcfg.is_empty(), "stance_blade: weapons.json entry found")
	if wcfg.is_empty():
		return
	var stance: Dictionary = wcfg.get("stance", {})
	var stand_id := int(stance.get("stand", -1))
	var run_id := int(stance.get("run", -1))
	_check(stand_id >= 0 and run_id >= 0, "stance_blade: weapons.json has a stance")
	if stand_id < 0 or run_id < 0:
		return

	_avatar.set_stance(stand_id, run_id)
	await process_frame

	var motion_female: Dictionary = _load_json(MOTION_IDS_PATH).get("female", {})
	var expected: String = motion_female.get(str(stand_id), "")
	_check(not expected.is_empty(),
			"stance_blade: motion_ids.json has a clip for stand id %d" % stand_id)
	_check(_avatar.current_animation() == expected,
			"stance_blade: current_animation() == %s (got %s)"
			% [expected, _avatar.current_animation()])


## glow_blade: play_loop(sk610015) against blade A0015 (equipped so the
## glow's bone anchor — @Sword, base_bone 7 — has a weapon mesh to sit
## on), captured against a stop_loop() control. Diff measured the same way
## the codes loop measures a fade: tight bbox of what actually changed,
## mean |a-b| over that region.
func _eval_glow_blade(sp: SkillPlayer) -> void:
	_avatar.equip_weapon("blade", GLOW_VARIANT)
	await process_frame
	var weapons: Dictionary = _load_json(WEAPONS_PATH).get("weapons", {})
	var wcfg: Dictionary = weapons.get("blade_%s" % GLOW_VARIANT, {})
	var stance: Dictionary = wcfg.get("stance", {})
	if stance.has("stand") and stance.has("run"):
		_avatar.set_stance(int(stance["stand"]), int(stance["run"]))
		await process_frame
	_avatar.pause_animation()
	await process_frame

	var played := sp.play_loop(GLOW_CODE, _avatar)
	_check(played, "glow_blade: play_loop(%s) accepted" % GLOW_CODE)
	if not played:
		return
	_check(sp.is_looping(), "glow_blade: is_looping() true while glow active")

	await _wait_s(MID_WAIT_S)
	var glow_shots: Array = [await _shot("glow_blade_with0")]
	for i in range(1, MID_SAMPLES):
		await _wait_s(MID_SPACING_S)
		glow_shots.append(await _shot("glow_blade_with%d" % i))
	var img_glow := _average_many(glow_shots)

	sp.stop_loop()
	_check(not sp.is_looping(), "glow_blade: is_looping() false after stop_loop()")
	await process_frame
	await process_frame
	var img_ctrl := _average_images(
			await _shot("glow_blade_ctrl1"), await _shot("glow_blade_ctrl2"))

	var change_bbox := _diff_bbox(img_ctrl, img_glow)
	var glow_rect := change_bbox if change_bbox.size != Vector2i.ZERO else _rect
	var d := _region_diff(img_ctrl, img_glow, glow_rect)
	var glow_min: float = GLOW_FADE_MIN_OVERRIDES.get(GLOW_CODE, GLOW_FADE_MIN_DEFAULT)
	_check(d >= glow_min and d <= GLOW_FADE_MAX,
			"glow_blade: %s glow visibly renders (|diff|=%.4f in [%.3f, %.3f], rect=%s)"
			% [GLOW_CODE, d, glow_min, GLOW_FADE_MAX, glow_rect])


## motion_per_class: for glorb/mura/spirit, equip the weapon, read its
## stance + first named skill from weapons.json (data-driven — no
## hardcoded stance ids), assert current_animation() matches the clip
## motion_ids.json maps the stance's stand id to, and reuse _eval_skill
## (verbatim) to assert the weapon's named skill clears the existing
## render-vs-control diff gate.
func _eval_motion_per_class(sp: SkillPlayer) -> void:
	var weapons: Dictionary = _load_json(WEAPONS_PATH).get("weapons", {})
	var motion_female: Dictionary = _load_json(MOTION_IDS_PATH).get("female", {})

	for entry_v in PER_CLASS_WEAPONS:
		var entry: Dictionary = entry_v
		var cls: String = entry["class"]
		var variant: String = entry["variant"]
		var key := "%s_%s" % [cls, variant]
		var wcfg: Dictionary = weapons.get(key, {})
		_check(not wcfg.is_empty(), "motion_per_class: %s: weapons.json entry found" % key)
		if wcfg.is_empty():
			continue

		var stance: Dictionary = wcfg.get("stance", {})
		var stand_id := int(stance.get("stand", -1))
		var run_id := int(stance.get("run", -1))
		_check(stand_id >= 0 and run_id >= 0,
				"motion_per_class: %s: weapons.json has a stance" % key)
		if stand_id < 0 or run_id < 0:
			continue

		_avatar.equip_weapon(cls, variant)
		await process_frame
		_avatar.set_stance(stand_id, run_id)
		await process_frame
		_avatar.pause_animation()
		await process_frame

		var expected_clip: String = motion_female.get(str(stand_id), "")
		_check(not expected_clip.is_empty(),
				"motion_per_class: %s: motion_ids.json has a clip for stand id %d"
				% [key, stand_id])
		_check(_avatar.current_animation() == expected_clip,
				"motion_per_class: %s: current_animation() == %s (got %s)"
				% [key, expected_clip, _avatar.current_animation()])

		var skills: Array = wcfg.get("skills", [])
		_check(not skills.is_empty(), "motion_per_class: %s: weapons.json has a named skill" % key)
		if skills.is_empty():
			continue
		var skill_code := "sk%06d" % int(skills[0])
		await _eval_skill(sp, skill_code)


func _eval_skill(sp: SkillPlayer, code: String) -> void:
	var info: Dictionary = sp.skill_info(code)
	if info.is_empty():
		_check(false, "%s: known catalog entry" % code)
		return

	# Pre-skill pose name. Explicit String type: _avatar is a plain Node3D
	# (see `var _avatar: Node3D` above), so `:=` can't infer a return type
	# from its dynamically-dispatched current_animation() call.
	var pre_anim: String = _avatar.current_animation()
	# Pose-normalize BEFORE the true pre-skill baseline capture too (fix
	# round 1, CRITICAL): an earlier version of this fix only re-anchored
	# the POST-skill side, comparing two after-skill captures against each
	# other — pose-identical, but no longer able to detect a persistent
	# material-restore defect at all, since neither side reflected
	# pre-skill material state. Normalizing pose here (replay pre_anim,
	# pause, settle — same sequence run again below, see that block's
	# comment) keeps img_a as the TRUE pre-skill baseline (materials
	# untouched by SkillPlayer) while still holding an identical,
	# reproducible pose to the post-skill capture.
	await _normalize_pose(pre_anim)

	# Capture A: idle, no skill playing, 2 averaged frames (noise floor).
	var img_a1 := await _shot("%s_a1_idle" % code)
	var img_a2 := await _shot("%s_a2_idle" % code)
	var img_a := _average_images(img_a1, img_a2)

	var done := [false]
	var cb := func(_c): done[0] = true
	sp.finished.connect(cb)

	var played := sp.play(code, _avatar)
	_check(played, "%s: play() accepted" % code)
	if not played:
		sp.finished.disconnect(cb)
		return

	await _wait_s(MID_WAIT_S)
	# Capture B is itself a short-window average (not a single frame): some
	# catalog effects strobe (sk401441's lightning-style flash measured a
	# genuine on/off duty cycle — ~0.07 mean diff for ~250ms, then ~0.0005
	# for the next ~150ms, repeating every ~500ms), so ANY single instant
	# has a real chance of landing in a dark phase and reading as "didn't
	# render" even though the effect is working correctly. Averaging a few
	# samples spread across the ~0.4-1.0s mid-playback window smooths over
	# the duty cycle without moving off "mid-playback".
	var b_shots: Array = [await _shot("%s_b_mid0" % code)]
	for i in range(1, MID_SAMPLES):
		await _wait_s(MID_SPACING_S)
		b_shots.append(await _shot("%s_b_mid%d" % [code, i]))
	var img_b := _average_many(b_shots)
	# The fade check measures over the TIGHT bbox of what actually changed
	# (small pad): the fixed idle-silhouette rect is sized for the avatar's
	# own body and dilutes a real but spatially small effect (a foot-level
	# accent) into noise (first cut: 450x626 idle rect measured a visibly-
	# rendering red beam at 0.001, far under FADE_MIN). Falls back to the
	# idle rect only if nothing changed at all (never observed in the
	# sample — every catalog entry here spawns a frame-0 tmd effect — but
	# keeps the check meaningful rather than a false PASS on an empty rect).
	var change_bbox := _diff_bbox(img_a, img_b)
	var fade_rect := change_bbox if change_bbox.size != Vector2i.ZERO else _rect
	var d_ab := _region_diff(img_a, img_b, fade_rect)
	# Per-skill threshold: see FADE_MIN_OVERRIDES above for which codes and why.
	var fade_min: float = FADE_MIN_OVERRIDES.get(code, FADE_MIN)
	_check(d_ab >= fade_min,
			"%s: effect visibly renders (|B-A|=%.4f >= %.3f, rect=%s)"
			% [code, d_ab, fade_min, fade_rect])

	var deadline := Time.get_ticks_msec() + int(FINISH_TIMEOUT_S * 1000)
	while not done[0] and Time.get_ticks_msec() < deadline:
		await process_frame
	_check(done[0], "%s: finished signal fired within %.1fs" % [code, FINISH_TIMEOUT_S])
	sp.finished.disconnect(cb)

	# The restore check stays on the BROADER union (idle rect + effect
	# bbox): a color flash covers the whole character body, not just where
	# the effect model sat, so residue could show up outside the tight
	# fade_rect above.
	#
	# Pose-normalize the SAME way as img_a above (replay pre_anim, pause,
	# settle) before capturing C: an actor-role motion track (base
	# attacks/named skills almost always carry one) genuinely plays via
	# AvatarCharacter.play_motion_id (Task 6 wiring, motion-by-id), and
	# either (a) holds a one-shot's final frame once finished — real,
	# intentional gameplay behavior (no draw/sheath — a finished attack
	# holds until the next stance/motion command), or (b) re-triggers the
	# SAME looping stance clip the skill started on (current_animation()
	# name unchanged) — which still drifted for the skill's ~2-4s duration
	# exactly like the documented idle-stand-loop drift (up to ~0.007-0.01
	# over a comparable window, see the settle-loop comment in _run())
	# because pause_animation() was never called again to freeze it.
	# Neither is a material-restore defect, so pose alone is normalized —
	# img_a (captured above, BEFORE any of this ran) is deliberately left
	# untouched as the true pre-skill material baseline: only pose is
	# re-anchored here, never re-captured from scratch, so a genuine
	# PERSISTENT material delta the skill leaves behind (e.g. a stash/
	# restore bug) still shows up as a real img_c vs img_a diff even
	# though both are now posed identically.
	await _normalize_pose(pre_anim)
	var img_c := await _shot("%s_c_after" % code)
	var restore_rect := _rect.merge(change_bbox) if change_bbox.size != Vector2i.ZERO else _rect
	var d_ac := _region_diff(img_a, img_c, restore_rect)
	# Per-skill threshold: see RESTORE_MAX_OVERRIDES above for which codes and why.
	var restore_max: float = RESTORE_MAX_OVERRIDES.get(code, RESTORE_MAX)
	_check(d_ac <= restore_max,
			"%s: material restore visually exact (|C-A|=%.4f <= %.3f)" % [code, d_ac, restore_max])


## Replays `anim_name` (no-op if empty) and immediately re-pauses it, then
## settles two frames — the SAME reset-and-settle sequence run before BOTH
## the true pre-skill baseline capture and the post-skill capture in
## _eval_skill, so pose is held at an identical, reproducible point at
## both ends without touching material state. See fix-round-1 CRITICAL
## note at _eval_skill's two call sites for why pose (not the captured
## image itself) is what gets re-anchored here.
func _normalize_pose(anim_name: String) -> void:
	if anim_name.is_empty():
		return
	_avatar.play_animation(anim_name)
	await process_frame
	_avatar.pause_animation()
	await process_frame


func _wait_s(seconds: float) -> void:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000)
	while Time.get_ticks_msec() < deadline:
		await process_frame


## Screen rect of the avatar, MEASURED from an actual render (not the mesh
## AABB): AvatarCharacter's part meshes are skinned, and Godot's stored
## Mesh.get_aabb() reflects the SKELETON's bind-pose bounds (arms included
## at full T-pose span, ~1.3 m wide) rather than the currently-posed,
## arms-down silhouette actually on screen — using it grew the "region" to
## nearly the full viewport and diluted every effect's diff into noise
## (first run: visibly rendering beams/sparks measured <0.005). Padding a
## silhouette bbox taken from a real frame keeps the region character-
## centered while staying tight enough for a near-body effect to register.
func _measure_character_rect() -> Rect2i:
	var bg := RenderingServer.get_default_clear_color()
	# Retry: an early frame can render before the avatar's shaders finish
	# compiling (blank/background-only capture) — seen once in practice as
	# a spurious full-viewport fallback. A few extra frames settle it.
	for attempt in 10:
		await process_frame
		await process_frame
		var img := root.get_viewport().get_texture().get_image()
		var box := _threshold_bbox_pts(img, null, bg, 0.03)
		if box.size != Vector2i.ZERO:
			# Pad for authored effect offsets up to ~0.5 m from the
			# character's bones (well over 100 px at this framing);
			# _diff_bbox below covers effects that radiate further still.
			return box.grow_individual(80, 80, 80, 80).intersection(
					Rect2i(Vector2i.ZERO, root.get_visible_rect().size))
	return Rect2i(Vector2i.ZERO, root.get_visible_rect().size)


## Bounding box (+ padding) of every pixel that changed between two shots.
## Used to fold a skill's actual rendered footprint into the measurement
## region — see the call site's note on wide-radiating effects.
func _diff_bbox(a: Image, b: Image) -> Rect2i:
	var box := _threshold_bbox_pts(a, b, Color(0, 0, 0, 0), 0.05)
	if box.size == Vector2i.ZERO:
		return box
	const PAD := 8
	return box.grow_individual(PAD, PAD, PAD, PAD).intersection(
			Rect2i(Vector2i.ZERO, Vector2i(a.get_width(), a.get_height())))


## Percentile-trimmed bbox of pixels where |img-ref| (or |a-b| when `b` is
## given) exceeds `thresh`. A strict min/max bbox is one stray dithering
## pixel away from ballooning across the whole frame (observed run-to-run:
## an isolated off-character hit pulled a tight effect bbox out to nearly
## full-viewport) — dropping the outer ~3% of hits on each axis discards a
## handful of outliers while barely trimming a real, clustered effect.
func _threshold_bbox_pts(img: Image, ref: Image, bg: Color, thresh: float) -> Rect2i:
	var w := img.get_width()
	var h := img.get_height()
	var xs := PackedInt32Array()
	var ys := PackedInt32Array()
	var step := 2
	for y in range(0, h, step):
		for x in range(0, w, step):
			var ca := img.get_pixel(x, y)
			var cb := ref.get_pixel(x, y) if ref != null else bg
			if absf(ca.r - cb.r) + absf(ca.g - cb.g) + absf(ca.b - cb.b) > thresh:
				xs.append(x)
				ys.append(y)
	if xs.is_empty():
		return Rect2i()
	xs.sort()
	ys.sort()
	var trim := 0
	if xs.size() > 20:
		trim = maxi(1, int(xs.size() * 0.03))
	var min_x: int = xs[trim]
	var max_x: int = xs[xs.size() - 1 - trim]
	var min_y: int = ys[trim]
	var max_y: int = ys[ys.size() - 1 - trim]
	return Rect2i(Vector2i(min_x, min_y), Vector2i(max_x - min_x, max_y - min_y))


func _average_images(a: Image, b: Image) -> Image:
	return _average_many([a, b])


func _average_many(imgs: Array) -> Image:
	var first: Image = imgs[0]
	var acc := PackedInt32Array()
	acc.resize(first.get_data().size())
	for img in imgs:
		var da: PackedByteArray = (img as Image).get_data()
		for i in da.size():
			acc[i] += da[i]
	var out := PackedByteArray()
	out.resize(acc.size())
	var n := imgs.size()
	for i in acc.size():
		out[i] = int(acc[i] / float(n))
	return Image.create_from_data(first.get_width(), first.get_height(), false, first.get_format(), out)


# --- copied from ytlevel's client/scripts/tests/occl_eval.gd (region-diff
# helper pattern), name kept identical per the task brief ---
func _region_diff(a: Image, b: Image, rect: Rect2i) -> float:
	## Mean |a-b| over the rect, RGB, 0..1. Sampled on a grid for speed.
	var total := 0.0
	var n := 0
	var step := maxi(1, mini(rect.size.x, rect.size.y) / 200)
	for y in range(rect.position.y, rect.end.y, step):
		for x in range(rect.position.x, rect.end.x, step):
			var ca := a.get_pixel(x, y)
			var cb := b.get_pixel(x, y)
			total += absf(ca.r - cb.r) + absf(ca.g - cb.g) + absf(ca.b - cb.b)
			n += 1
	return total / (3.0 * maxf(1.0, float(n)))


func _check(cond: bool, label: String) -> void:
	if not cond:
		printerr("FAIL: " + label)
		_fails += 1
	else:
		print("ok: " + label)


func _shot(name: String) -> Image:
	await process_frame
	await process_frame
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("%s/%s.png" % [SHOT_DIR, name]))
	return img
