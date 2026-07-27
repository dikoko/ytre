class_name BeachSprites
extends MeshInstance3D
## Beach shore-wave sprite emitter, a port of the original client's
## shore-wave spawn/update/render loop. One node per map holding the
## single spawn accumulator — the original shares one accumulator
## across all water objects. Godot randf() stands in for C rand();
## the exact RNG stream is not reproducible and only the statistics matter.

const BEACH_SHADER_PATH := "res://shaders/beach_ff.gdshader"
const UVS: Array[Vector2] = [
	Vector2(0, 1), Vector2(1, 1), Vector2(0, 0), Vector2(1, 0),
]
# D3D strip (c-u, c+n-u, c+u, c+n+u) -> tris (0,1,2),(2,1,3). Unlike file
# meshes, these quads are REBUILT in Godot space from already-mirrored
# direction vectors — the corner formula absorbs the orientation flip, so
# the index order stays D3D's (verified empirically: the pool's authored
# U/N face the quads up only with this order).
const QUAD_ORDER: Array[int] = [0, 1, 2, 2, 1, 3]

var _params: Dictionary
var _points: Array = []   # {pos, n, u} per shore point, Godot space
var _mats: Dictionary = {}  # texture id -> ShaderMaterial
var _sprites: Array = []  # {center, n, u, life, alpha, tex}
var _acc := 0.0


func setup(data: Dictionary) -> void:
	_params = data["beach"]
	for obj in data["objects"]:
		var pts: Dictionary = obj.get("beach_points", {})
		var p: Array = pts.get("positions", [])
		var n: Array = pts.get("normals", [])
		var u: Array = pts.get("us", [])
		for i in range(p.size() / 3):
			_points.append({
				"pos": Vector3(p[i * 3], p[i * 3 + 1], p[i * 3 + 2]),
				"n": Vector3(n[i * 3], n[i * 3 + 1], n[i * 3 + 2]),
				"u": Vector3(u[i * 3], u[i * 3 + 1], u[i * 3 + 2]),
			})
	var shader: Shader = load(BEACH_SHADER_PATH)
	var textures: Array = data["textures"]
	for tid in _params["texture_ids"]:
		var t := int(tid)
		if _mats.has(t) or t < 0 or t >= textures.size():
			continue
		var mat := ShaderMaterial.new()
		mat.shader = shader
		mat.set_shader_parameter("tex", load(textures[t]))
		# the original draws all beach quads after every water surface
		mat.render_priority = 1
		_mats[t] = mat
	mesh = ImmediateMesh.new()


func _process(dt: float) -> void:
	if _points.is_empty() or _mats.is_empty():
		return
	var freq: float = _params["frequency"]
	var vel: float = _params["velocity"]
	var life0: float = _params["life"]
	var bdelta: float = _params["delta"]
	var tex_ids: Array = _params["texture_ids"]

	_acc += freq * dt * 2.0
	var rounds := int(_acc)
	_acc -= rounds
	if rounds > 0:
		for pt in _points:
			for l in range(rounds):
				if randf() > 0.5:  # coin flip skips half the attempts
					continue
				var fd := randf()
				_sprites.append({
					"center": pt["pos"] + fd * vel * dt * pt["n"]
							+ (fd - 0.5) * bdelta * pt["u"],
					"n": pt["n"], "u": pt["u"],
					"life": life0, "alpha": 0.0,
					# fd*(texture_count-1)+0.5 rounded, texture_count = 2
					"tex": int(tex_ids[0] if fd < 0.5 else tex_ids[1]),
				})

	var alive: Array = []
	for s in _sprites:
		s["life"] -= dt
		if s["life"] <= 0.0:
			continue
		s["center"] += s["n"] * vel * dt
		var d: float = s["life"] / life0
		# fade in over the first 30% of life, out over the remaining 70%
		s["alpha"] = (-3.33 * d + 3.33) if d > 0.7 else (1.43 * d)
		alive.append(s)
	_sprites = alive
	_rebuild()


func _rebuild() -> void:
	var im: ImmediateMesh = mesh
	im.clear_surfaces()
	if _sprites.is_empty():
		return
	var su: float = float(_params["size_u"]) * 0.2
	var sn: float = float(_params["size_n"]) * 0.2
	for t in _mats:
		var began := false
		for s in _sprites:
			if s["tex"] != t:
				continue
			if not began:
				im.surface_begin(Mesh.PRIMITIVE_TRIANGLES, _mats[t])
				began = true
			var c: Vector3 = s["center"]
			var u: Vector3 = s["u"] * su
			var n: Vector3 = s["n"] * sn
			var v := [c - u, c + n - u, c + u, c + n + u]
			# Alpha byte-packed as int(256*a) & 0xFF — alpha can exceed 1.0
			# just below the ramp knee and wrap to ~0 for a frame; shipped
			# quirk, replicated
			var col := Color(1, 1, 1,
					float(int(256.0 * s["alpha"]) & 0xFF) / 255.0)
			for k in QUAD_ORDER:
				im.surface_set_color(col)
				im.surface_set_uv(UVS[k])
				im.surface_add_vertex(v[k])
		if began:
			im.surface_end()
