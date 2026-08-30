extends SceneTree
## Headless math checks for SkillPath — the port of the original's
## interpolating cubic B-spline path + two-level time mapping.
## Run: "$GODOT_BIN" --headless --path client --script scripts/tests/test_skill_path.gd

var _fails := 0


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok: " + label)
	else:
		printerr("FAIL: " + label)
		_fails += 1


func _linear_params() -> Array:
	var p: Array = []
	for i in 10:
		p.append(float(i) / 9.0)
	return p


func _init() -> void:
	# Straight 2-point path, identity frame, no target: start pin + end pin.
	var d := {
		"input_points": [[0.0, 0.0, 0.0], [0.0, 0.0, 4.0]],
		"parameters": _linear_params(),
		"base_character": 256, "base_bone": 11,
		"target_character": 0, "target_bone": 11,
	}
	var path := SkillPath.from_catalog(d)
	_check(path != null, "2-point path builds")
	path.bake(Vector3.ZERO, Basis.IDENTITY, null)
	var p0 := path.sample(0.0).origin
	var p1 := path.sample(1.0).origin
	# D3D->Godot: input z negated, so the curve runs 0 -> (0,0,-4).
	_check(p0.distance_to(Vector3.ZERO) < 0.05, "t=0 at first input point (got %s)" % p0)
	_check(p1.distance_to(Vector3(0, 0, -4)) < 0.05, "t=1 at last input point, z-mirrored (got %s)" % p1)
	var pm := path.sample(0.5).origin
	_check(absf(pm.x) < 0.05 and absf(pm.y) < 0.05 and pm.z < -0.5 and pm.z > -3.5,
			"midpoint on the segment (got %s)" % pm)
	# monotone progress along -z for a straight line with linear parameters
	var prev_z := 1.0
	var monotone := true
	for i in 11:
		var z := path.sample(float(i) / 10.0).origin.z
		if z > prev_z + 0.01:
			monotone = false
		prev_z = z
	_check(monotone, "straight path progresses monotonically")

	# Frame re-anchoring: bake with a live base->target pair; the sampled
	# start rides the base position and the end reaches the target.
	var base_pos := Vector3(1, 0, 0)
	var target_pos := Vector3(1, 0, 3)
	path.bake(base_pos, Basis.IDENTITY, target_pos)
	var q0 := path.sample(0.0).origin
	var q1 := path.sample(1.0).origin
	_check(q0.distance_to(base_pos) < 0.1, "baked t=0 at base (got %s)" % q0)
	# Measured exactly 0.0 (verbatim endpoint through the base frame, with N
	# scaled to the live base->target range): tightened from a 0.6 ceiling.
	_check(q1.distance_to(target_pos) < 0.0001, "baked t=1 reaches the target (got %s)" % q1)

	# Curved 4-point path builds and stays finite.
	var d4 := {
		"input_points": [[0, 0, 0], [0.5, 1, 1], [-0.5, 1, 2], [0, 0, 3]],
		"parameters": _linear_params(),
		"base_character": 256, "base_bone": 11,
		"target_character": 512, "target_bone": 11,
	}
	var path4 := SkillPath.from_catalog(d4)
	_check(path4 != null, "4-point path builds")
	path4.bake(Vector3.ZERO, Basis.IDENTITY, Vector3(0, 0, -3))
	var ok := true
	for i in 21:
		var tr := path4.sample(float(i) / 20.0)
		if not tr.origin.is_finite():
			ok = false
	_check(ok, "4-point path finite everywhere")

	# Curved-path handedness (fix round 1): a path authored with a local
	# +X bow, baked base->target straight along Godot -Z, must keep that
	# bow on the FAITHFUL (+X) side in world space, not mirror it. This
	# discriminates u = v.cross(fwd) [correct] from the old u = v.cross(n)
	# bug -- both prior fixtures have zero local X/Y so neither caught it.
	#
	# Derivation (F = M.B.M, M = z-mirror diag(1,1,-1), B = the original
	# D3D UVN frame; Godot-column form: u = v.cross(fwd), v = UP,
	# forward-column = fwd*scale, fwd = -n):
	#   input_points [[0,0,0],[0.5,0,0.5],[0,0,1]] -> after from_catalog's
	#   single z-negate: local (0,0,0), (0.5,0,-0.5), (0,0,-1) -- the curve
	#   bows toward LOCAL +X at its midpoint.
	#   base=(0,0,0), target=(0,0,-1): n = (target-base).normalized() =
	#   (0,0,-1); fwd = -n = (0,0,1); v = UP = (0,1,0);
	#   u = v.cross(fwd) = (0,1,0) x (0,0,1) = (1,0,0).
	#   run = reach = 1, so scale = 1: basis = Basis((1,0,0),(0,1,0),(0,0,1))
	#   = identity here, so the local +X bow maps 1:1 -- the faithful
	#   mid-flight world sample has POSITIVE X.
	#   The old buggy u = v.cross(n) gives u = (0,1,0) x (0,0,-1) = (-1,0,0)
	#   instead -- the same local +X bow would map to NEGATIVE world X, a
	#   mirrored path.
	var dbow := {
		"input_points": [[0.0, 0.0, 0.0], [0.5, 0.0, 0.5], [0.0, 0.0, 1.0]],
		"parameters": _linear_params(),
	}
	var pathbow := SkillPath.from_catalog(dbow)
	pathbow.bake(Vector3.ZERO, Basis.IDENTITY, Vector3(0, 0, -1))
	var bow_x := pathbow.sample(0.5).origin.x
	_check(bow_x > 0.1, "curved path keeps its +X bow on the faithful side (got x=%s)" % bow_x)

	# Degenerate: 1 input point -> null (original requires >= 2).
	_check(SkillPath.from_catalog({"input_points": [[0, 0, 0]],
			"parameters": _linear_params()}) == null, "1-point path rejected")

	if _fails == 0:
		print("ALL OK")
	else:
		printerr("%d FAILURES" % _fails)
	quit(1 if _fails else 0)
