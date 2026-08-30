class_name SkillPath
extends RefCounted
## Port of the original client's skill flight-path playback: an
## interpolating cubic B-spline through the authored input points, a
## live frame whose forward axis points base->target (rescaled to the
## live base-target range — see the proof note in bake()), 10 baked
## keys, and a two-level time mapping (t -> authored parameter easing ->
## key pair).
## The serialized quat/vec keys in skills.json are editor leftovers —
## the original client rebuilds them at runtime, and so do we.
##
## Coordinate boundary: input points are D3D-space; z is negated once at
## from_catalog. Everything else runs natively in Godot space.

const KEYNUM := 10

var _points: PackedVector3Array = []   # Godot-space input points
var _parameters: PackedFloat32Array = []

# spline state (order k=4, n = point_count + 1)
var _n := 0
var _knot: PackedFloat32Array
var _cx: PackedFloat32Array
var _cy: PackedFloat32Array
var _cz: PackedFloat32Array

# baked live keys
var _vec_keys: PackedVector3Array = []
var _quat_keys: Array[Quaternion] = []


static func from_catalog(path_dict: Dictionary) -> SkillPath:
	var pts_v: Array = path_dict.get("input_points", [])
	if pts_v.size() < 2:
		return null
	var sp := SkillPath.new()
	for p in pts_v:
		var a: Array = p
		sp._points.append(Vector3(float(a[0]), float(a[1]), -float(a[2])))
	var params_v: Array = path_dict.get("parameters", [])
	for f in params_v:
		sp._parameters.append(float(f))
	while sp._parameters.size() < KEYNUM:
		sp._parameters.append(1.0)
	sp._create_curve()
	return sp


func bake(base_pos: Vector3, base_basis: Basis, target_pos: Variant) -> void:
	## Bakes the flight frame + keys as the original client does: base orientation,
	## overridden so N (forward) points base->target when a target exists;
	## V = +Y; U = V x N.
	##
	## Basis-convention proof (test-driven, see test_skill_path.gd's
	## "baked t=1 reaches the target" check): the authored curve's own
	## forward run sits on LOCAL -Z (after the single D3D->Godot z-negate
	## in from_catalog, a 2-point path [0,0,0]->[0,0,4] ends at local
	## (0,0,-4), not +Z). Wiring N straight onto the Basis()'s +Z argument
	## (columns (U,V,N), N=n) therefore sends the curve's local -Z run out
	## along -n — the WRONG side of base_pos. Measured: base=(1,0,0),
	## target=(1,0,3) landed the baked endpoint at (1,0,-4), 7 units off
	## and on the far side of base from the target. Passing -n instead
	## (N lives on the Basis's -Z column) flips the curve's
	## local -Z run onto +n, the target side.
	##
	## Sign alone still under-shoots/over-shoots by the mismatch between
	## the authored curve's own local run length and the live base-target
	## distance (here, curve run 4 vs target distance 3 -> still 1 unit
	## off, over the test's 0.6 ceiling). The original engine targets a
	## live pair at an arbitrary range with one fixed-length authored
	## template path, so N additionally carries the fit-to-range scale
	## (target distance / authored run length) — U and V stay unit so
	## only the forward reach stretches, not the path's sideways shape.
	## With both fixes the endpoint above lands exactly on (1,0,3).
	var basis := base_basis.orthonormalized()
	if target_pos != null and Vector3(target_pos) != base_pos:
		var n: Vector3 = (Vector3(target_pos) - base_pos).normalized()
		var v := Vector3.UP
		# fwd is the Basis's -Z-column direction (see the proof above); u
		# must be built from fwd, not n, or the frame is an IMPROPER
		# transform (det -1, a reflection) that mirrors any lateral (local
		# X) bow of a curved authored path in world space. Faithful
		# derivation: F = M.B.M (M = the z-mirror diag(1,1,-1), B = the
		# original D3D UVN frame) works out in Godot-column form to
		# u = v.cross(fwd), v = UP, forward-column = fwd * scale, with
		# fwd = -n throughout -- not just on the forward column.
		var fwd := -n
		var u := v.cross(fwd)
		if u.length() > 0.0:
			u = u.normalized()
		var run := (_points[_points.size() - 1] - _points[0]).length()
		var reach := (Vector3(target_pos) - base_pos).length()
		var scale := reach / run if run > 0.0001 else 1.0
		basis = Basis(u, v, fwd * scale)
	var frame := Transform3D(basis, base_pos)
	_vec_keys.clear()
	_quat_keys.clear()
	for i in KEYNUM:
		var data := _curve_data_by_param(float(i) / float(KEYNUM - 1))
		var world_pos: Vector3 = frame * data["pos"]
		_vec_keys.append(world_pos)
		# Shortest-arc rotation from the curve's local direction onto the
		# frame's forward axis (the original client's rotation-arc helper).
		var dir: Vector3 = data["dir"]
		var fwd: Vector3 = basis * Vector3(0, 0, 1)
		var q := Quaternion(dir.normalized(), fwd.normalized()) \
				if dir.length() > 0.0001 else Quaternion.IDENTITY
		_quat_keys.append(q)


func sample(t: float) -> Transform3D:
	## Two-level lookup, matching the original client — t picks a parameter-easing
	## segment; the eased parameter picks the key pair to slerp/lerp.
	t = clampf(t, 0.0, 1.0)
	var ikey := int(t * (KEYNUM - 1))
	var f := t * (KEYNUM - 1) - ikey
	var p_start := _parameters[ikey]
	var p_end := _parameters[ikey] if ikey == KEYNUM - 1 else _parameters[ikey + 1]
	var param := p_start + f * (p_end - p_start)

	var istart := int(param * (KEYNUM - 1))
	var iend := istart + 1
	if iend > KEYNUM - 2:
		iend = KEYNUM - 1
	var f2 := 0.0
	if iend != istart:
		f2 = (param * (KEYNUM - 1) - istart) / float(iend - istart)

	if istart >= KEYNUM - 1:
		return Transform3D(Basis(_quat_keys[KEYNUM - 1]), _vec_keys[KEYNUM - 1])
	var q := _quat_keys[istart].slerp(_quat_keys[iend], f2)
	var v := _vec_keys[istart].lerp(_vec_keys[iend], f2)
	return Transform3D(Basis(q), v)


# === order-4 interpolating B-spline (port of the original client's curve math) ===

func _create_curve() -> void:
	var m := _points.size()          # pointNum
	_n = m + 1
	var k := 4
	# data rows 1..m are the points; rows 0 and m+1 are phantom tangents.
	var dx := PackedFloat32Array(); dx.resize(m + 2)
	var dy := PackedFloat32Array(); dy.resize(m + 2)
	var dz := PackedFloat32Array(); dz.resize(m + 2)
	for i in m:
		dx[i + 1] = _points[i].x
		dy[i + 1] = _points[i].y
		dz[i + 1] = _points[i].z
	dx[0] = dx[2] - dx[1];       dy[0] = dy[2] - dy[1];       dz[0] = dz[2] - dz[1]
	dx[m + 1] = dx[m] - dx[m - 1]; dy[m + 1] = dy[m] - dy[m - 1]; dz[m + 1] = dz[m] - dz[m - 1]

	_knot = _chord_knots(k, dx, dy, dz)
	var sys := _setup_system(_knot)
	_cx = _solve(sys, dx.duplicate())
	_cy = _solve(sys, dy.duplicate())
	_cz = _solve(sys, dz.duplicate())


func _chord_knots(k: int, dx: PackedFloat32Array, dy: PackedFloat32Array,
		dz: PackedFloat32Array) -> PackedFloat32Array:
	## Chord-length knots. NOTE: the length
	## ratios read the DATA rows (incl. the phantom tangent rows), exactly
	## as the original does — port verbatim, do not "fix".
	var knot := PackedFloat32Array()
	knot.resize(_n + k + 1)
	var p: Array[Vector3] = []
	for i in _n:
		p.append(Vector3(dx[i], dy[i], dz[i]))
	for i in k:
		knot[i] = 0.0
	knot[k] = 1.0
	for i in range(k + 1, _n + 2):
		var num := (p[i - k + 2] - p[i - k + 1]).length()
		var den := (p[i - k + 1] - p[i - k]).length()
		var delta := num / den if den > 0.0 else 1.0
		knot[i] = knot[i - 1] + (knot[i - 1] - knot[i - 2]) * delta
	for i in range(_n + 2, _n + k + 1):
		knot[i] = knot[i - 1]
	return knot


func _setup_system(knot: PackedFloat32Array) -> Dictionary:
	## Clamped-end tridiagonal system + LU factorization, ported verbatim.
	var n := _n
	var alpha := PackedFloat32Array(); alpha.resize(n + 1)
	var beta := PackedFloat32Array(); beta.resize(n + 1)
	var gamma := PackedFloat32Array(); gamma.resize(n + 1)
	for i in range(2, n - 1):
		var d_i := knot[i + 1] - knot[i]
		var d1 := knot[i + 2] - knot[i + 1]
		var d2 := knot[i + 3] - knot[i + 2]
		var d3 := knot[i + 4] - knot[i + 3]
		var s := d1 + d2
		alpha[i] = (d2 * d2 / (d_i + s)) / s
		beta[i] = (d2 * (d_i + d1) / (d_i + s) + d1 * (d2 + d3) / (s + d3)) / s
		gamma[i] = (d1 * d1 / (s + d3)) / s
	beta[0] = 1.0; gamma[0] = 0.0
	alpha[1] = -3.0; beta[1] = 3.0; gamma[1] = 0.0
	alpha[n - 1] = 0.0; beta[n - 1] = -3.0; gamma[n - 1] = 3.0
	alpha[n] = 0.0; beta[n] = 1.0
	var up := PackedFloat32Array(); up.resize(n + 1)
	var low := PackedFloat32Array(); low.resize(n + 1)
	up[0] = beta[0]
	for i in range(1, n + 1):
		low[i] = alpha[i] / up[i - 1]
		up[i] = beta[i] - low[i] * gamma[i - 1]
	return {"up": up, "low": low, "gamma": gamma}


func _solve(sys: Dictionary, rhs: PackedFloat32Array) -> PackedFloat32Array:
	## Forward/back substitution ported verbatim, including the end swaps.
	var n := _n
	var up: PackedFloat32Array = sys["up"]
	var low: PackedFloat32Array = sys["low"]
	var gamma: PackedFloat32Array = sys["gamma"]
	var tmp := rhs[0]; rhs[0] = rhs[1]; rhs[1] = tmp
	tmp = rhs[n - 1]; rhs[n - 1] = rhs[n]; rhs[n] = tmp
	var w := PackedFloat32Array(); w.resize(n + 1)
	w[0] = rhs[0]
	for i in range(1, n + 1):
		w[i] = rhs[i] - low[i] * w[i - 1]
	var v := PackedFloat32Array(); v.resize(n + 1)
	v[n] = w[n] / up[n]
	for i in range(n - 1, -1, -1):
		v[i] = (w[i] - gamma[i] * v[i + 1]) / up[i]
	return v


func _basis_n(i: int, k: int, u: float) -> float:
	## Cox–de Boor recursion, ported verbatim.
	if k == 1:
		return 1.0 if _knot[i] <= u and u < _knot[i + 1] else 0.0
	var n1 := _basis_n(i, k - 1, u)
	var n2 := _basis_n(i + 1, k - 1, u)
	var r1 := 0.0
	if _knot[i + k - 1] - _knot[i] != 0.0:
		r1 = (u - _knot[i]) / (_knot[i + k - 1] - _knot[i])
	var r2 := 0.0
	if _knot[i + k] - _knot[i + 1] != 0.0:
		r2 = (_knot[i + k] - u) / (_knot[i + k] - _knot[i + 1])
	return r1 * n1 + r2 * n2


func _curve_data_by_param(f_param: float) -> Dictionary:
	## Curve sample at a parameter: position by basis sum;
	## fParam==1 returns the last data point VERBATIM; "direction" is the
	## first support CONTROL POINT of the active span, normalized — a
	## quirk of the original (not a true tangent), ported as-is.
	var k := 4
	var u_start := _knot[k - 1]
	var u_end := _knot[_n + 1]
	var u := u_start + (u_end - u_start) * f_param
	var kid := k - 1
	while u >= _knot[kid + 1] and kid < _n:
		kid += 1
	var pos := Vector3.ZERO
	for i in range(kid - k + 1, mini(kid, _n) + 1):
		var nb := _basis_n(i, k, u)
		pos += Vector3(_cx[i], _cy[i], _cz[i]) * nb
	if f_param == 1.0:
		pos = _points[_points.size() - 1]
	var dir := Vector3(_cx[kid - k + 1], _cy[kid - k + 1], _cz[kid - k + 1])
	return {"pos": pos, "dir": dir}
