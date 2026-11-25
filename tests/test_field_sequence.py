import sys,unittest,struct,zlib,math
from pathlib import Path
from array import array
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game.field_sequence import *
from vapor_game.field_asset import encode_field_asset,decode_field_asset
D=ROOT/'fixtures/field-sequence'
class SequenceTests(unittest.TestCase):
 def setUp(self):self.raw=(D/'sequence.vpa').read_bytes();self.s=FieldSequence.open(D/'sequence.vpa')
 def test_index_and_reencode(self):
  self.assertEqual(self.s.index.times,(0.,.5,1.5));self.assertEqual(index_from_paths(D/frame_filename(i) for i in range(3)),self.raw)
 def test_exact_and_interpolated(self):
  for i,t in enumerate(self.s.index.times):self.assertEqual(encode_field_asset(self.s.sample(t)),(D/frame_filename(i)).read_bytes())
  self.assertEqual(encode_field_asset(self.s.sample(.25)),(D/'sample-025.vpf').read_bytes());self.assertEqual(self.s.cached_frames,2)
 def test_seeks_cache_and_mutation(self):
  calls=[];s=FieldSequence(self.raw,lambda i,n:(calls.append(i),(D/frame_filename(i)).read_bytes())[1]);a=s.sample(.25);a.density[0]=99;s.sample(.25);self.assertEqual(calls,[0,1]);self.assertNotEqual(s.sample(.25).density[0],99);s.sample(99);self.assertEqual(s.cached_frames,2);self.assertEqual(calls,[0,1,2]);self.assertEqual(s.sample(-99).time,0.);s.clear();self.assertEqual(s.cached_frames,0)
 def test_corruption(self):
  for i in [0,4,8,12,16,28,32,56,64,72,76]:
   b=bytearray(self.raw);b[i]^=255
   with self.assertRaises(ValueError):decode_index(b)
  with self.assertRaises(ValueError):decode_index(self.raw+b'0')
  with self.assertRaises(ValueError):FieldSequence(self.raw,lambda i,n:b'0'*n).sample(0)
 def test_valid_crc_bad_time(self):
  b=bytearray(self.raw);struct.pack_into('<d',b,80,0.);struct.pack_into('<I',b,12,zlib.crc32(b[16:]))
  with self.assertRaises(ValueError):decode_index(b)
 def test_encoder_rejects_inconsistent_grid_and_time(self):
  a=(D/frame_filename(0)).read_bytes();b=decode_field_asset(a);f=type(b)(b.cells,(2.,2.,3.),b.density_cap,1.,b.density,b.temperature)
  with self.assertRaises(ValueError):encode_index([a,encode_field_asset(f)])
  with self.assertRaises(ValueError):encode_index([a,a])
 def test_invalid_sample_time(self):
  for t in [math.nan,math.inf,-math.inf]:
   with self.assertRaises(ValueError):self.s.sample(t)
