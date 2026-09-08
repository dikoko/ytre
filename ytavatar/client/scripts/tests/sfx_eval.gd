extends SceneTree
## Windowed particle eval (C2, spec §6). Run from the repo root:
##   "$GODOT_BIN" --path client --script scripts/tests/sfx_eval.gd --position 4000,4000
## Part 1 — per sample skill: capture mid-play frames with particles OFF
## (SkillPlayer.sfx_enabled = false; effect models etc. still render) and
## ON, over the same window; the ON-OFF diff inside its own bbox must clear
## FADE_MIN (something rendered) and the ON frame's mean luminance must
## stay under WHITEOUT_MAX (an additive blow-up screens out). Every live
## particle transform must be finite.
## Part 2 — the 154-effect sweep: instantiate each effect on the avatar,
## tick it 2 s, assert it drew at least once when its data says it should
## (billboard, or an emitter whose rate graph peaks above 0), and record
## the fleet-wide particle-count maximum.
##
## Sample codes (picked 2026-09-05 from the catalog by composition):
##   sk040016 — 19 emitter tracks, path-riding (the most sfx-heavy skill)
##   sk110001 — 14 tracks, emitters + billboards
##   sk400162 — 8 billboard-only tracks
## All three resolve with no missing refs.

const SHOT_DIR := "res://../reports/sfx_eval"
const SAMPLE_CODES := ["sk040016", "sk110001", "sk400162"]
const FADE_MIN := 0.02
## Per-code override of FADE_MIN, for compositions whose particle footprint
## is investigated and confirmed genuinely thin/sparse — not a runtime
## defect. Same pattern (and same rule: document the MEASURED value, never
## lower the global floor) as skill_eval.gd's FADE_MIN_OVERRIDES.
const FADE_MIN_OVERRIDES := {}
const WHITEOUT_MAX := 0.85
const MID_WAIT_S := 0.5
const MID_SAMPLES := 4
const MID_SPACING_S := 0.15
## Lead time added to a skill's FIRST authored sfx "play" frame before the
## capture window opens — long enough for an emitter's rate accumulator to
## have produced a visible cloud, short enough to stay inside the shortest
## authored play..stop span in the sample set (sk400162's electric tracks
## run frames 45..72 = 1.50..2.40 s, and the window ends at 2.30 s).
const SFX_LEAD_S := 0.35
const SWEEP_SECONDS := 2.0
const PARTICLE_CAP := 5000

var _fails := 0
var _avatar: Node3D
var _cam: Camera3D


func _init() -> void:
	_run()


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok: " + label)
	else:
		printerr("FAIL: " + label)
		_fails += 1


func _wait_s(seconds: float) -> void:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000)
	while Time.get_ticks_msec() < deadline:
		await process_frame


## Image.save_png needs a REAL path: SHOT_DIR points above the project root
## (res://../reports), which res:// resolution refuses — globalize it, the
## same way skill_eval.gd's _shot does.
func _shot(shot_name: String) -> Image:
	await process_frame
	await process_frame
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("%s/%s.png" % [SHOT_DIR, shot_name]))
	return img


## Mean of N same-format captures. Accumulated over the raw byte buffers
## rather than per-pixel get_pixel/set_pixel (skill_eval.gd's _average_many,
## verbatim in approach): at 640x640 the Color path costs ~2M scripted
## calls per average and six averages would dominate the run. The 1/255
## quantization it costs is three orders of magnitude under FADE_MIN.
func _average(imgs: Array) -> Image:
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
	return Image.create_from_data(first.get_width(), first.get_height(), false,
			first.get_format(), out)


func _diff_bbox(a: Image, b: Image, thresh := 0.04) -> Rect2i:
	var minp := Vector2i(1 << 30, 1 << 30)
	var maxp := Vector2i(-1, -1)
	for y in a.get_height():
		for x in a.get_width():
			var ca := a.get_pixel(x, y)
			var cb := b.get_pixel(x, y)
			if absf(ca.r - cb.r) + absf(ca.g - cb.g) + absf(ca.b - cb.b) > thresh:
				minp = Vector2i(mini(minp.x, x), mini(minp.y, y))
				maxp = Vector2i(maxi(maxp.x, x), maxi(maxp.y, y))
	if maxp.x < 0:
		return Rect2i()
	return Rect2i(minp, maxp - minp + Vector2i.ONE)


func _region_diff(a: Image, b: Image, r: Rect2i) -> float:
	if r.size == Vector2i.ZERO:
		return 0.0
	var acc := 0.0
	for y in range(r.position.y, r.end.y):
		for x in range(r.position.x, r.end.x):
			var ca := a.get_pixel(x, y)
			var cb := b.get_pixel(x, y)
			acc += (absf(ca.r - cb.r) + absf(ca.g - cb.g) + absf(ca.b - cb.b)) / 3.0
	return acc / float(r.size.x * r.size.y)


func _mean_luma(img: Image, r: Rect2i) -> float:
	if r.size == Vector2i.ZERO:
		return 0.0
	var acc := 0.0
	for y in range(r.position.y, r.end.y):
		for x in range(r.position.x, r.end.x):
			acc += img.get_pixel(x, y).get_luminance()
	return acc / float(r.size.x * r.size.y)


## Wall-clock wait that re-pauses the avatar's AnimationPlayer every frame.
##
## A skill's motion track drives the avatar through a fast clip (play_motion_id),
## and the off and on passes are two SEPARATE wall-clock playbacks: they settle
## at slightly different sub-frame points, so the POSE differs between them and
## that pose delta lands in the same on-minus-off image the particle check
## reads. Measured on run 1 (no freeze): sk400162, whose capture window did not
## even overlap its authored sfx frames, still produced 18,325 changed pixels
## and |on-off| = 0.0099 with ZERO particles on screen — i.e. two thirds of the
## FADE_MIN bar earned by pose noise alone. Holding the pose pinned in both
## passes leaves the particles as the only thing that can differ.
func _hold_pose_wait(seconds: float) -> void:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000)
	while Time.get_ticks_msec() < deadline:
		_avatar.pause_animation()
		await process_frame


## Seconds from play() to the first capture, DERIVED FROM THE CATALOG rather
## than assumed to be MID_WAIT_S.
##
## A skill's sfx tracks do not all start at frame 0, and they are not all live
## at once: sk400162's eight electric tracks arm at frames 45/49 (1.50/1.63 s)
## and stop at 72/75, so run 1's fixed 0.50..0.95 s window measured a stretch
## with NO particles authored in it at all and read the skill as 0.0099
## ("broken") when nothing was; and sk040016 authors 3 tracks at frame 0 but
## its real burst — 12 more — at frame 68, so a frame-0 window sees a sixth of
## the effect (measured 0.0050 there vs 0.0911 at the burst).
##
## Rule: over every sfx play..stop interval, pick the play frame whose window
## start has the MOST intervals live (ties → earliest), skipping any candidate
## whose sample span would run past the end of the skill's own timeline. This
## is "mid-play" in the sense the brief means it — the moment the composition
## is actually showing its particles.
func _sfx_window_start(sp: SkillPlayer, code: String) -> float:
	var info: Dictionary = sp.skill_info(code)
	var fps := float(info.get("fps", 30.0))
	if fps <= 0.0:
		fps = 30.0
	var end_s := float(info.get("frames", 0)) / fps
	var span_s := float(MID_SAMPLES - 1) * MID_SPACING_S
	var intervals: Array = []   # [play_frame, stop_frame] (stop = INF if none)
	for track_v in (info.get("tracks", []) as Array):
		var track: Dictionary = track_v
		if String(track.get("kind", "")) != "sfx":
			continue
		var commands: Array = track.get("commands", [])
		for cmd_v in commands:
			var cmd: Dictionary = cmd_v
			if String(cmd.get("kind", "")) != "play":
				continue
			var pf := int(cmd.get("frame", 0))
			var sf := INF
			for other_v in commands:
				var other: Dictionary = other_v
				if String(other.get("kind", "")) == "stop" and int(other.get("frame", 0)) > pf:
					sf = minf(sf, float(other.get("frame", 0)))
			intervals.append([float(pf), sf])
	if intervals.is_empty():
		return MID_WAIT_S
	var best_start := -1.0
	var best_count := -1
	for iv in intervals:
		var start: float = maxf(MID_WAIT_S, iv[0] / fps + SFX_LEAD_S)
		if end_s > 0.0 and start + span_s > end_s - 0.05:
			continue
		var probe := start * fps
		var count := 0
		for other in intervals:
			if other[0] <= probe and probe < other[1]:
				count += 1
		if count > best_count or (count == best_count and start < best_start):
			best_count = count
			best_start = start
	return best_start if best_start >= 0.0 else MID_WAIT_S


func _capture_mid(sp: SkillPlayer, code: String, tag: String, start_s: float) -> Image:
	var played := sp.play(code, _avatar)
	_check(played, "%s %s: play() accepted" % [code, tag])
	await _hold_pose_wait(start_s)
	var shots: Array = [await _shot("%s_%s_0" % [code, tag])]
	for i in range(1, MID_SAMPLES):
		await _hold_pose_wait(MID_SPACING_S)
		shots.append(await _shot("%s_%s_%d" % [code, tag, i]))
	# NaN screen while particles are live
	var finite := true
	for o in sp._sfx_objects:
		if not is_instance_valid(o):
			continue
		for i in (o as SfxObject).drawn_instances():
			var t: Transform3D = (o as SfxObject).instance_transform(i)
			if not (t.origin.is_finite() and t.basis.x.is_finite() and t.basis.y.is_finite()):
				finite = false
	_check(finite, "%s %s: all particle transforms finite" % [code, tag])
	sp.stop()
	await process_frame
	return _average(shots)


func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOT_DIR))
	await process_frame
	RenderingServer.set_default_clear_color(Color(0.35, 0.35, 0.35))
	root.get_viewport().size = Vector2i(640, 640)

	# Same two-light rig as skill_eval.gd / avatar_shot.gd. Particles are
	# rendered by unshaded sfx shaders, so the lights change NO measurement
	# here (both the on and off capture carry the identical rig) — they only
	# make the avatar and the effect GLBs visible in the saved PNGs, which
	# the brief requires a human to be able to read by eye.
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
	# Blinks land inside capture windows and pollute the diff bbox with a
	# second cluster far from the effect (skill_eval.gd, task-7 fix round 2).
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
	if not settled:
		printerr("SFX EVAL FAILED: avatar has no visible mesh (base load failed?)")
		quit(2)
		return
	# Freeze the autoplaying idle-stand loop: its continuous bone motion
	# otherwise drifts between the off and on captures and contaminates the
	# particle bbox (skill_eval.gd documents the same measurement).
	_avatar.pause_animation()

	_cam = Camera3D.new()
	root.add_child(_cam)
	_cam.current = true
	_cam.fov = 45.0
	_cam.global_position = Vector3(0, 1.2, 3.2)
	_cam.look_at(Vector3(0, 1.0, 0))
	await process_frame

	var sp := SkillPlayer.new()
	root.add_child(sp)
	sp.load_catalog()

	# --- Part 1: particles on vs off ---
	for code in SAMPLE_CODES:
		var start_s := _sfx_window_start(sp, code)
		SfxRandom.reset()
		sp.sfx_enabled = false
		var off := await _capture_mid(sp, code, "off", start_s)
		SfxRandom.reset()
		sp.sfx_enabled = true
		var on := await _capture_mid(sp, code, "on", start_s)
		var bbox := _diff_bbox(off, on)
		var d := _region_diff(off, on, bbox)
		var fade_min: float = FADE_MIN_OVERRIDES.get(code, FADE_MIN)
		_check(bbox.size != Vector2i.ZERO and d >= fade_min,
				"%s: particles visibly render (|on-off|=%.4f >= %.3f, bbox=%s, window +%.2fs)"
				% [code, d, fade_min, bbox, start_s])
		var luma := _mean_luma(on, bbox)
		_check(luma <= WHITEOUT_MAX,
				"%s: no additive white-out (mean luma %.3f <= %.2f)" % [code, luma, WHITEOUT_MAX])

	# --- Part 2: 154-effect sweep ---
	var lib := sp.sfx_library()
	var max_particles := 0
	var max_name := ""
	for n in lib.names():
		var obj := lib.instantiate(n)
		if obj == null:
			_check(false, "%s: instantiates" % n)
			continue
		root.add_child(obj)
		obj.global_transform = _avatar.global_transform
		obj.play()
		var drew := false
		var t := 0.0
		var last := Time.get_ticks_msec()
		while t < SWEEP_SECONDS:
			await process_frame
			var now := Time.get_ticks_msec()
			var dt := float(now - last) / 1000.0
			last = now
			t += dt
			obj.tick(dt, _cam.global_transform)
			drew = drew or obj.drawn_instances() > 0
			if obj.particle_count() > max_particles:
				max_particles = obj.particle_count()
				max_name = n
		var raw: Dictionary = lib.info(n)
		var should_draw: bool = raw.get("kind", "") == "billboard" \
				or (lib.config(n)["graphs"]["rate"] as SfxGraph).max_value() > 0.0
		_check(drew or not should_draw,
				"%s: drew at least once (%s)" % [n, "expected" if should_draw else "no emission authored"])
		obj.queue_free()
	print("sweep: fleet max live particles %d (%s)" % [max_particles, max_name])
	_check(max_particles < PARTICLE_CAP, "fleet max live particles %d < %d" % [max_particles, PARTICLE_CAP])

	sp.stop()
	print("EVAL FAILED: %d" % _fails if _fails else "EVAL ALL OK")
	quit(1 if _fails else 0)
