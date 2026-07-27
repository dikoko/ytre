class_name PointLights
## Unpacks fixed-function point lights from node metadata into the FF
## shaders' uniform arrays. 30_export_map.py packs each light as 13 floats:
## pos.xyz (Godot-space), diffuse.rgb, ambient.rgb, max_range, a0, a1, a2
## (D3D attenuation 1/(a0 + a1*d + a2*d^2), PointLightData in the map .plt).

const MAX_LIGHTS := 15  # the original renderer's point-light slot cap
const STRIDE := 13


static func apply(source: Node, mat: ShaderMaterial) -> void:
	var count: int = source.get_meta("point_light_count", 0)
	if count <= 0:
		return
	var packed: PackedFloat32Array = source.get_meta("point_lights")
	count = mini(count, MAX_LIGHTS)
	if packed.size() < count * STRIDE:
		push_warning("point_lights: metadata size %d < %d lights * %d"
				% [packed.size(), count, STRIDE])
		return

	# Shader arrays are fixed at MAX_LIGHTS — pad the tail.
	var positions := PackedVector3Array()
	var diffuse := PackedVector3Array()
	var ambient := PackedVector3Array()
	var params := PackedVector4Array()
	positions.resize(MAX_LIGHTS)
	diffuse.resize(MAX_LIGHTS)
	ambient.resize(MAX_LIGHTS)
	params.resize(MAX_LIGHTS)
	for i in count:
		var o := i * STRIDE
		positions[i] = Vector3(packed[o], packed[o + 1], packed[o + 2])
		diffuse[i] = Vector3(packed[o + 3], packed[o + 4], packed[o + 5])
		ambient[i] = Vector3(packed[o + 6], packed[o + 7], packed[o + 8])
		params[i] = Vector4(packed[o + 9], packed[o + 10], packed[o + 11], packed[o + 12])

	mat.set_shader_parameter("point_light_count", count)
	mat.set_shader_parameter("pl_position", positions)
	mat.set_shader_parameter("pl_diffuse", diffuse)
	mat.set_shader_parameter("pl_ambient", ambient)
	mat.set_shader_parameter("pl_params", params)
