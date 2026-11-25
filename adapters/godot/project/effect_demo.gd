extends Node3D
# Preset IDs: see effects/presets.json. The core uses right-handed metres, Y-up.
@export_range(1,8) var preset_id: int = 3
@export_enum("Low", "Medium", "High") var quality: int = 1
@export_enum("cpu", "gpu", "hybrid", "auto") var backend: String = "cpu"
var effect: RefCounted
var texture: ImageTexture
var period := 0.05
var elapsed := 0.0
func _ready() -> void:
 if not ClassDB.class_exists("VaporEffect"):
  push_error("Build the native library and GDExtension first.");set_process(false);return
 effect=ClassDB.instantiate("VaporEffect")
 if not effect.create_effect(preset_id,quality,backend,1):
  set_process(false);return
 var d: Dictionary=effect.get_definition()
 var ex: Vector3=d["extent"]
 var volume:=MeshInstance3D.new()
 var mesh:=BoxMesh.new();mesh.size=Vector3.ONE;volume.mesh=mesh;volume.position=ex*.5;volume.scale=ex
 var material:=ShaderMaterial.new();material.shader=load("res://vapor_volume.gdshader")
 material.set_shader_parameter("cells",Vector3(d["render_cells"]));material.set_shader_parameter("extent_m",ex)
 material.set_shader_parameter("density_cap",d["density_cap"]);material.set_shader_parameter("extinction",d["extinction"]);material.set_shader_parameter("ray_steps",d["ray_steps"])
 var col:Vector3=d["colour"];material.set_shader_parameter("smoke_colour",Color(col.x,col.y,col.z))
 for key in ["anisotropy","albedo","ambient","emission","thermal_fade"]: material.set_shader_parameter(key,d[key])
 var fine:Vector3i=d["render_cells"]
 texture=ImageTexture.create_from_image(Image.create_empty(fine.x,fine.y*fine.z,false,Image.FORMAT_RGBA8));material.set_shader_parameter("density_atlas",texture);volume.material_override=material;add_child(volume)
 var initial:Image=effect.pump_atlas_image(true)
 if initial!=null:texture.update(initial)
 period=1.0/float(d["upload_hz"])
 var camera:=Camera3D.new();var span:float=max(ex.x,max(ex.y,ex.z));camera.position=ex*.5+Vector3(.4,.2,1.5)*span;add_child(camera);camera.look_at(ex*.5);camera.far=max(1000.0,span*5.0);camera.current=true
 effect.play()
func _process(delta:float)->void:
 if not effect.advance(delta):set_process(false);return
 elapsed+=delta
 var request:=elapsed>=period
 if request:elapsed=fmod(elapsed,period)
 var image:Image=effect.pump_atlas_image(request)
 if image!=null:texture.update(image)
func _exit_tree()->void:
 if effect!=null:effect.close()
