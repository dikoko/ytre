class_name CameraOcclusion
extends Node
## Run-mode camera occlusion fading: props standing between the camera and
## the avatar (walls, trees, buildings) fade to a recognizable ghost so the
## character stays visible — standard third-person behaviour.
##
## VIEWER ENHANCEMENT, not a port: the original client had no occlusion
## handling — blocking geometry simply blocked the view.
##
## Mechanism: AABB broad phase (per-map index of every Props MeshInstance3D
## world AABB, segment test camera -> avatar chest), then a MESH-ACCURATE
## narrow phase: the segment must hit an actual triangle of the mesh
## (Geometry3D.segment_intersects_triangle over cached local-space faces,
## early-exit). The broad phase alone is wrong for big props: s_SEmain's
## 62x18x43 m AABB covers the whole forecourt, so standing on the plaza put
## camera AND avatar inside the box and the school faded with nothing
## actually blocking (2026-08-10 report). Worst case measured 383 us for a
## full no-hit scan of that 6,737-triangle mesh — fine per frame.
## Occluders get their surface materials swapped to a derived variant
## carrying an `occ_alpha` uniform — the same runtime-derivation trick
## prop_animator uses for its fade curves, with a distinct uniform so the
## two never collide. NOT GeometryInstance3D.transparency: the Mobile
## renderer ignores it (Forward+ only), which reads as "occlusion silently
## does nothing".

## Alpha of a fully faded occluder: 50% (user-picked 2026-08-11 after 10%
## read as not enough; the original had no occlusion, so there is no
## authored value) — see-through but clearly recognizable.
const FADED_ALPHA := 0.5
## Alpha units per second. Fading IN is urgent (the avatar is being
## hidden); restoring is gentle so borderline flips blur instead of pop.
const FADE_SPEED := 3.5
const RESTORE_SPEED := 1.2
## Hysteresis: a faded prop must be continuously clear of the sightline
## this long before it eases back. The blocked test is binary, so a
## razor-edge hit flipping with sub-pixel camera drift would otherwise pop
## the prop solid/ghost every few frames ("walls flicker on and off",
## 2026-08-11 report — static scenes measure bit-stable, so boundary
## oscillation under micro camera motion is the only flicker mechanism).
const RESTORE_DELAY := 0.3
## Props whose AABB top sits at or below the avatar's knees cannot block the
## view — floor plates, stairs, ground decals. Skipping them also keeps the
## navmesh-source surfaces solid underfoot.
const KNEE_HEIGHT := 0.4
## Mass-fade guard for dense areas: only the nearest N occluders fade.
const MAX_FADED := 12
## "Blocked" must mean "actually hides the character" (2026-08-11 report:
## distant stairs ghosted while the avatar stood in plain sight — the
## school complex is CHUNKED into arbitrary >256-surface MeshInstances, so
## one curb sliver clipping the sightline faded a chunk whose visible bulk
## is stairs 20 m away). Two rules kill sliver hits:
## - consensus: rays to feet/waist/head; >= 2 must be blocked to fade.
## - near-camera exclusion: rays start this far in front of the camera, so
##   lens-hugging geometry (bush tops, terrace lips just under an elevated
##   camera) can't trigger fades it can't visually cause.
const SAMPLE_HEIGHTS: Array[float] = [0.2, 1.0, 1.5]
const MIN_BLOCKED_RAYS := 2
const RAY_START_OFFSET := 0.5

var _index: Array = []        # [{mi: MeshInstance3D, aabb: AABB}]
var _faces: Dictionary = {}   # Mesh RID id -> PackedVector3Array (local faces)
# MeshInstance3D -> {target: float, alpha: float, clear: float (seconds
#                    continuously off the sightline — hysteresis),
#                    prev: [prior overrides], mats: [occ ShaderMaterials]}
var _fading: Dictionary = {}
var _variants: Dictionary = {} # source shader RID id -> occ variant Shader
var _camera: Camera3D = null
var _runner: AvatarRunner = null
var enabled := false


func setup(camera: Camera3D, runner: AvatarRunner) -> void:
	_camera = camera
	_runner = runner


func rebuild(props_root: Node3D) -> void:
	## Called on every map load, after props instantiate (prop_lighting has
	## already swapped materials by then — it runs on tree entry).
	_restore_all()
	_index.clear()
	_faces.clear()
	if props_root == null:
		return
	for mi_node in props_root.find_children("*", "MeshInstance3D", true, false):
		var mi := mi_node as MeshInstance3D
		if mi.mesh == null:
			continue
		_index.append({"mi": mi, "aabb": mi.global_transform * mi.mesh.get_aabb()})


func set_active(active: bool) -> void:
	enabled = active
	if not active:
		_restore_all()


func _process(delta: float) -> void:
	if enabled and _camera != null and _runner != null and _runner.active:
		_update_targets(delta)
	var done: Array = []
	for mi in _fading:
		if not is_instance_valid(mi):
			done.append(mi)
			continue
		var entry: Dictionary = _fading[mi]
		var speed: float = FADE_SPEED if entry["target"] < 1.0 else RESTORE_SPEED
		entry["alpha"] = move_toward(entry["alpha"], entry["target"],
				speed * delta)
		for mat in entry["mats"]:
			(mat as ShaderMaterial).set_shader_parameter("occ_alpha", entry["alpha"])
		if entry["target"] == 1.0 and entry["alpha"] == 1.0:
			_restore(mi, entry)
			done.append(mi)
	for mi in done:
		_fading.erase(mi)


func _update_targets(delta: float = 1.0) -> void:
	var cam_pos := _camera.global_position
	var knee := _runner.avatar_position.y + KNEE_HEIGHT
	# One ray per sample height, each starting RAY_START_OFFSET past the lens.
	var rays: Array = []   # [[from, to], ...]
	for h in SAMPLE_HEIGHTS:
		var to := _runner.avatar_position + Vector3(0, h, 0)
		var dir := to - cam_pos
		var offset: float = minf(RAY_START_OFFSET, dir.length() * 0.3)
		rays.append([cam_pos + dir.normalized() * offset, to])
	var hits: Array = []   # [{mi, d}]
	for entry in _index:
		var mi: MeshInstance3D = entry["mi"]
		if not is_instance_valid(mi):
			continue
		var aabb: AABB = entry["aabb"]
		if aabb.end.y <= knee:
			continue
		var blocked := 0
		for r in range(rays.size()):
			if blocked + (rays.size() - r) < MIN_BLOCKED_RAYS:
				break   # can no longer reach consensus
			# Broad phase: any AABB overlap; the narrow phase is exact.
			if _segment_crossing(aabb, rays[r][0], rays[r][1]) <= 0.0:
				continue
			if _blocks_sightline(mi, rays[r][0], rays[r][1]):
				blocked += 1
				if blocked >= MIN_BLOCKED_RAYS:
					break
		if blocked < MIN_BLOCKED_RAYS:
			continue
		hits.append({"mi": mi, "d": cam_pos.distance_squared_to(aabb.get_center())})
	hits.sort_custom(func(a, b): return a["d"] < b["d"])
	var keep := {}
	for i in range(mini(hits.size(), MAX_FADED)):
		var mi: MeshInstance3D = hits[i]["mi"]
		keep[mi] = true
		if _fading.has(mi):
			_fading[mi]["target"] = FADED_ALPHA
			_fading[mi]["clear"] = 0.0
		else:
			var entry := _begin_fade(mi)
			if not entry.is_empty():
				_fading[mi] = entry
	# Everything previously faded but no longer occluding eases back — after
	# RESTORE_DELAY of continuously clear sightline (hysteresis: a binary
	# blocked test on razor-edge geometry flips with sub-pixel camera drift,
	# and an instant restore turns each flip into a visible pop).
	for mi in _fading:
		if not keep.has(mi):
			var entry: Dictionary = _fading[mi]
			entry["clear"] = entry["clear"] + delta
			if entry["clear"] >= RESTORE_DELAY:
				entry["target"] = 1.0


func _begin_fade(mi: MeshInstance3D) -> Dictionary:
	## Swap every surface to an occ-variant material; remember what was
	## there so _restore puts back EXACTLY the prior state (including a
	## prop_animator fade material, which resumes its own uniform).
	var prev: Array = []
	var mats: Array = []
	for s in range(mi.mesh.get_surface_count()):
		prev.append(mi.get_surface_override_material(s))
		var src := mi.get_active_material(s) as ShaderMaterial
		if src == null or src.shader == null:
			continue
		var faded: ShaderMaterial = src.duplicate()
		faded.shader = _occ_variant(src.shader)
		faded.set_shader_parameter("occ_alpha", 1.0)
		mi.set_surface_override_material(s, faded)
		mats.append(faded)
	if mats.is_empty():
		return {}
	return {"target": FADED_ALPHA, "alpha": 1.0, "clear": 0.0,
			"prev": prev, "mats": mats}


func _restore(mi: MeshInstance3D, entry: Dictionary) -> void:
	if not is_instance_valid(mi) or mi.mesh == null:
		return
	var prev: Array = entry["prev"]
	for s in range(mini(mi.mesh.get_surface_count(), prev.size())):
		mi.set_surface_override_material(s, prev[s])


func _occ_variant(src: Shader) -> Shader:
	## Same derivation pattern as prop_animator's fade variant, distinct
	## uniform. PITFALL (learned the hard way): never write
	## ALPHA_SCISSOR_THRESHOLD in a derived variant — any scissor write
	## moves the material to the opaque pass and additive glows render as
	## opaque geometry.
	var key := src.get_rid().get_id()
	if _variants.has(key):
		return _variants[key]
	var code := src.code
	if code.contains("uniform float occ_alpha"):
		return src
	code = code.replace("shader_type spatial;",
			"shader_type spatial;\nuniform float occ_alpha : hint_range(0.0, 1.0) = 1.0;")
	# STRIP any inherited scissor write (prop_ff's masked branch, and the
	# anim fade variant derived from it). With the scissor in place the
	# material stays in the alpha-scissor OPAQUE pass, where our reduced
	# ALPHA falls below the threshold and every masked pixel is DISCARDED —
	# the prop vanishes outright instead of ghosting (the 2026-08-10
	# "school disappears" report). Removing it moves the ghost to the
	# transparent pass; tex.a still shapes the masked texture.
	code = code.replace("ALPHA_SCISSOR_THRESHOLD = alpha_scissor;", "")
	if code.contains("blend_add") or code.contains("anim_alpha"):
		# ALPHA is already written (additive pass or an animator fade
		# variant): multiply so the existing behaviour survives.
		var idx := code.rfind("}")
		code = code.substr(0, idx) + "\tALPHA *= occ_alpha;\n" + code.substr(idx)
	else:
		code = code.replace("render_mode unshaded, cull_back;",
				"render_mode unshaded, cull_back, depth_draw_opaque;")
		code = code.replace("render_mode unshaded, cull_disabled;",
				"render_mode unshaded, cull_disabled, depth_draw_opaque;")
		# Splice AFTER the replaces above — they lengthen the string, and a
		# stale rfind index lands the ALPHA line mid-token.
		var idx := code.rfind("}")
		code = code.substr(0, idx) + "\tALPHA = tex.a * occ_alpha;\n" + code.substr(idx)
	var variant := Shader.new()
	variant.code = code
	_variants[key] = variant
	return variant


func _blocks_sightline(mi: MeshInstance3D, from: Vector3, to: Vector3) -> bool:
	## Narrow phase: does the segment hit an actual triangle of the mesh?
	## Faces are cached in LOCAL space (lazily — only AABB-passing candidates
	## ever pay get_faces()); the segment transforms into local space instead.
	## Geometry3D.segment_intersects_triangle is Moller-Trumbore WITHOUT
	## backface culling, so mixed prop windings are fine with one test.
	var faces := _mesh_faces(mi.mesh)
	var inv := mi.global_transform.affine_inverse()
	var lf := inv * from
	var lt := inv * to
	for i in range(0, faces.size(), 3):
		if Geometry3D.segment_intersects_triangle(
				lf, lt, faces[i], faces[i + 1], faces[i + 2]) != null:
			return true
	return false


func _mesh_faces(mesh: Mesh) -> PackedVector3Array:
	var key := mesh.get_rid().get_id()
	if not _faces.has(key):
		_faces[key] = mesh.get_faces()
	return _faces[key]


static func _segment_crossing(aabb: AABB, from: Vector3, to: Vector3) -> float:
	## Length of the segment's overlap with the AABB (slab method), 0 if none.
	var dir := to - from
	var t0 := 0.0
	var t1 := 1.0
	for axis in 3:
		var d := dir[axis]
		var lo := aabb.position[axis]
		var hi := aabb.end[axis]
		if absf(d) < 1e-9:
			if from[axis] < lo or from[axis] > hi:
				return 0.0
			continue
		var ta := (lo - from[axis]) / d
		var tb := (hi - from[axis]) / d
		if ta > tb:
			var tmp := ta
			ta = tb
			tb = tmp
		t0 = maxf(t0, ta)
		t1 = minf(t1, tb)
		if t0 > t1:
			return 0.0
	return (t1 - t0) * dir.length()


func _restore_all() -> void:
	for mi in _fading:
		if is_instance_valid(mi):
			_restore(mi, _fading[mi])
	_fading.clear()
