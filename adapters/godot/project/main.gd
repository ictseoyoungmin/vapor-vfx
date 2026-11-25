extends Node3D
# Godot 4.4+ native desktop; GDExtension and Rust library must be built first.
@export_enum("cpu", "gpu", "hybrid", "auto") var backend: String = "cpu"
@export_range(1,4) var detail_scale: int = 1
var simulation: RefCounted
var texture: ImageTexture
var upload_elapsed := 0.0
func _ready() -> void:
 if not ClassDB.class_exists("VaporSimulation"):
  push_error("Build the Rust library and Godot GDExtension first."); set_process(false); return
 simulation = ClassDB.instantiate("VaporSimulation")
 if not simulation.configure(Vector3i(16,20,16),0.04,{"pressure_iterations":24,"backend":backend,"detail_scale":detail_scale}):
  set_process(false); return
 simulation.set_emitter(0,Vector3(0.32,0.1,0.32),Vector3.UP,{"density_rate":20.0,"speed":0.6})
 var volume := MeshInstance3D.new()
 var box := BoxMesh.new(); box.size = Vector3.ONE; volume.mesh=box
 volume.position=Vector3(.32,.4,.32);volume.scale=Vector3(.64,.8,.64)
 var material := ShaderMaterial.new(); material.shader=load("res://vapor_volume.gdshader")
 material.set_shader_parameter("cells",Vector3(simulation.get_backend_info()["render_cells"]))
 var fine: Vector3i=simulation.get_backend_info()["render_cells"]
 texture=ImageTexture.create_from_image(Image.create_empty(fine.x,fine.y*fine.z,false,Image.FORMAT_RGBA8));material.set_shader_parameter("density_atlas",texture)
 var initial: Image=simulation.pump_atlas_image(true)
 if initial!=null:texture.update(initial)
 volume.material_override=material;add_child(volume)
 var camera := Camera3D.new();camera.position=Vector3(1.5,1.0,1.6);add_child(camera);camera.look_at(Vector3(.32,.4,.32));camera.current=true
func _process(delta: float) -> void:
 var report: Dictionary=simulation.advance(delta)
 if report.is_empty():set_process(false);return
 upload_elapsed+=delta
 var request:=upload_elapsed>=.05
 if request:upload_elapsed=fmod(upload_elapsed,.05)
 var image: Image=simulation.pump_atlas_image(request)
 if image!=null:texture.update(image)
func _exit_tree() -> void:
 if simulation!=null:simulation.close()
