import sys,unittest,struct,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bindings/python'))
from vapor_game.field_asset import *
from array import array
ROOT=Path(__file__).resolve().parents[1]
class FieldAssetTests(unittest.TestCase):
    def setUp(self):self.raw=(ROOT/'fixtures/field-asset.vpf').read_bytes();self.field=decode_field_asset(self.raw)
    def test_fixture(self):
        f=self.field;self.assertEqual(f.cells,(4,5,6));self.assertEqual(f.extent,(1.,2.,3.));self.assertEqual(f.time,1.25);self.assertEqual(f.density[3],3/128);self.assertEqual(encode_field_asset(f),self.raw)
    def test_native_bridge_no_runtime(self):
        f=self.field.native_fields();self.assertEqual(f.cells,(4,5,6));self.assertEqual(len(f.temperature),120)
    def test_invalid_bytes(self):
        for i in [0,4,8,20,64,68,72,76,80]:
            b=bytearray(self.raw);b[i]^=255
            with self.assertRaises(ValueError):decode_field_asset(b)
        for b in [self.raw[:-1],self.raw+b'\x00']:
            with self.assertRaises(ValueError):decode_field_asset(b)
    def test_nan_even_valid_crc(self):
        b=bytearray(self.raw);struct.pack_into('<f',b,80,float('nan'));struct.pack_into('<I',b,64,zlib.crc32(b[80:]))
        with self.assertRaises(ValueError):decode_field_asset(b)
    def test_invalid_encode(self):
        f=self.field;f.density[0]=float('inf')
        with self.assertRaises(ValueError):encode_field_asset(f)
