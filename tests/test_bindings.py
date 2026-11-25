"""ABI wrapper tests against an explicit C test double, NOT Rust/physics tests."""
import ctypes as C
import json,os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game import Simulation,VaporError,Config,Emitter,Obstacle,Metrics,Advance,Render,BackendOptions,BackendInfo,_CAtlasTicket
LIB=os.environ.get('VAPOR_TEST_FIXTURE_LIBRARY')
@unittest.skipUnless(LIB,'C ABI test double was not built')
class BindingTests(unittest.TestCase):
 def sim(self,**kwargs):return Simulation(library=LIB,cells=(4,5,6),**kwargs)
 def test_sizes(self):
  for typ,size in [(Config,100),(Emitter,56),(Obstacle,56),(Metrics,112),(Advance,40),(Render,76)]:self.assertEqual(C.sizeof(typ),size)
  self.assertEqual(Metrics.centroid.offset,56);self.assertEqual(Metrics.cpu_bytes.offset,104)
 def test_create_close(self):
  s=self.sim();s.close();s.close()
  with self.assertRaises(VaporError):s.step()
 def test_config(self):
  with self.sim(cell_size=.125,origin=(1,2,3)) as s:self.assertEqual(s.shape,(6,5,4));self.assertEqual(s.config['cell_size'],.125);self.assertEqual(s.config['origin'],[1,2,3])
 def test_unknown_and_unsigned(self):
  with self.assertRaises(TypeError):self.sim(unknown=1)
  with self.assertRaises(ValueError):Simulation(library=LIB,cells=(-1,5,6))
 def test_snapshot_layout_owned(self):
  with self.sim() as s:
   a=s.field();self.assertEqual(len(a),120);self.assertEqual(a[98],1);b=s.field();b[0]=999;self.assertEqual(a[0],0)
   v=s.field('velocity',numpy=True);self.assertEqual(v.shape,(6,5,4,3));self.assertEqual(float(v.flat[1]),1.5)
 def test_atlas_layout(self):
  with self.sim() as s:a=s.atlas_rgba8();self.assertEqual(len(a),480);self.assertEqual(a[4:8],bytes([1,9,3,255]))
 def test_emitter_marshalling(self):
  with self.sim() as s:
   s.set_emitter(2,position=(1.25,2.5,3.75),speed=.5,density_rate=7.5,enabled=True);m=s.metrics();self.assertEqual(m['centroid'],[1.25,2.5,3.75]);self.assertEqual(m['max_density'],7.5);self.assertEqual(m['max_speed'],.5)
 def test_obstacle_marshalling(self):
  with self.sim() as s:s.set_capsule(3,(0,0,0),(1,1,1),.25);self.assertEqual(s.metrics()['pressure_residual_rms'],.25);s.set_box(3,(0,0,0),(1,1,1));s.remove_obstacle(3)
 def test_advance_metrics_and_reset(self):
  with self.sim() as s:
   s.step(3);a=s.advance(.1);self.assertEqual(a['steps'],1);self.assertEqual(a['alpha'],.25);self.assertEqual(a['dropped_seconds'],.5);m=s.metrics();self.assertEqual(m['ticks'],4);self.assertEqual(m['cpu_bytes'],1234567);self.assertEqual(m['clamped_velocities'],17);s.reset();self.assertEqual(s.metrics()['ticks'],0)
 def test_profile_and_errors(self):
  with self.sim() as s:
   s.set_profile(0,[(0,1,0,1),(1,1,1,1)],duration=2,repeat=True);s.set_profile(0,None)
   with self.assertRaises(ValueError):s.set_profile(0,[(0,1)])
   with self.assertRaises(VaporError) as e:s.step(601)
   self.assertIn('fixture rejected',str(e.exception))
 def test_render_layout(self):
  with self.sim() as s:self.assertEqual(len(s.render(eye=(0,0,1),target=(0,0,0),width=8,height=4)),128)
 def test_backend_layout_offsets(self):
  self.assertEqual(C.sizeof(BackendOptions),32);self.assertEqual(C.sizeof(BackendInfo),64)
  self.assertEqual(BackendOptions.reserved.offset,20);self.assertEqual(BackendOptions.detail_turbulence.offset,24)
  self.assertEqual(BackendOptions.detail_frequency.offset,28);self.assertEqual(BackendInfo.cpu_bytes.offset,40)
 def test_auto_fallback_is_reported_not_gpu(self):
  with self.sim(backend="auto",detail_scale=2,allow_cpu_fallback=True) as s:
   self.assertEqual(s.backend_info['requested'],0);self.assertEqual(s.backend_info['active'],1)
   self.assertEqual(s.render_shape,(6,5,4));self.assertEqual(len(s.atlas_rgba8()),480)
   self.assertEqual(s.backend_info['flags']&8,8)
 def test_strict_gpu_and_hybrid_fail_not_cpu(self):
  for backend in ['gpu','hybrid','auto']:
   with self.assertRaises(VaporError) as e:self.sim(backend=backend)
   self.assertEqual(e.exception.code,-7)
 def test_extended_options_binary_marshalling(self):
  import struct
  with self.sim(backend="auto",allow_cpu_fallback=True,allow_software_gpu=True,detail_scale=2,detail_turbulence=.25,detail_frequency=12.5) as s:
   word=s._lib.dll.vapor_test_backend_word;word.argtypes=[C.c_uint32];word.restype=C.c_uint32
   self.assertEqual([word(i) for i in range(6)],[32,1,0,2,3,0])
   self.assertEqual(word(6),struct.unpack('<I',struct.pack('<f',.25))[0]);self.assertEqual(word(7),struct.unpack('<I',struct.pack('<f',12.5))[0])
 def test_exact_mac_padded_layout_and_owned_copy(self):
  with self.sim() as s:
   a=s.mac_cells();self.assertEqual(len(a),5*6*7*8);self.assertEqual(list(a[:8]),list(range(8)))
   b=s.mac_cells();b[0]=99;self.assertEqual(a[0],0)
 def test_atlas_ticket_layout(self):
  self.assertEqual(C.sizeof(_CAtlasTicket),32);self.assertEqual(_CAtlasTicket.id.offset,8);self.assertEqual(_CAtlasTicket.ticks.offset,16);self.assertEqual(_CAtlasTicket.bytes.offset,24)
 def test_atlas_pending_busy_then_submission_tick(self):
  with self.sim() as s:
   s.step(7);ticket=s.begin_atlas();self.assertEqual((ticket.ticks,ticket.bytes),(7,480));self.assertIsNone(s.begin_atlas());s.step(5)
   self.assertIsNone(s.poll_atlas(ticket));data=s.poll_atlas(ticket);self.assertEqual(data[0],7);self.assertEqual(len(data),480);self.assertEqual(s.metrics()['ticks'],12)
   with self.assertRaises(VaporError) as e:s.poll_atlas(ticket)
   self.assertEqual(e.exception.code,-2)
 def test_atlas_reset_cancel_and_foreign_owner(self):
  with self.sim() as s,self.sim() as other:
   t=s.begin_atlas();u=other.begin_atlas()
   with self.assertRaises(ValueError):s.poll_atlas(u)
   s.cancel_atlas(t)
   with self.assertRaises(VaporError):s.poll_atlas(t)
   n=s.begin_atlas();self.assertGreater(n.id,t.id);s.reset()
   with self.assertRaises(VaporError):s.poll_atlas(n)
   final=s.begin_atlas();self.assertGreater(final.id,n.id);self.assertEqual(final.ticks,0)
   s.cancel_atlas(final);other.cancel_atlas(u)
 def test_atlas_short_buffer_is_retryable_and_pending_does_not_write(self):
  with self.sim() as s:
   t=s.begin_atlas();lib=s._lib;ready=C.c_uint32(99);small=(C.c_uint8*4)(*[77]*4)
   self.assertEqual(lib.poll_atlas(s._h(),t.id,small,len(small),C.byref(ready)),-3);self.assertEqual(bytes(small),bytes([77]*4));self.assertEqual(ready.value,0)
   output=(C.c_uint8*t.bytes)(*[55]*t.bytes);self.assertEqual(lib.poll_atlas(s._h(),t.id,output,len(output),C.byref(ready)),0);self.assertEqual(ready.value,0);self.assertEqual(bytes(output),bytes([55]*t.bytes));self.assertIsNotNone(s.poll_atlas(t))
 def test_cpu_detail_and_unknown_mode_rejected(self):
  with self.assertRaises(VaporError):self.sim(backend="cpu",detail_scale=2)
  with self.assertRaises(ValueError):self.sim(backend="invalid")
if __name__=='__main__':unittest.main(verbosity=2)
