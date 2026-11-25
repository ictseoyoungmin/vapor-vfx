"""Host ABI layout only; no native runtime claim."""
import unittest,sys,ctypes as C,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'bindings/python'));sys.path.insert(0,str(ROOT/'tools'))
from vapor_game.fidelity import _Grid,_Density,_Optics,_Camera,_grid
class PortContract(unittest.TestCase):
    def test_layout(self):
        self.assertEqual([C.sizeof(x) for x in [_Grid,_Density,_Optics,_Camera]],[56,64,200,96])
        self.assertEqual(_Grid.extent.offset,24);self.assertEqual(_Optics.direction.offset,88);self.assertEqual(_Camera.eye.offset,24)
    def test_invalid_grid(self):
        for cells in ([512]*3,[3,4,4],[4.,4,4],[4,4]):
            with self.assertRaises(ValueError):_grid(cells,[1,1,1],1)
if __name__=='__main__':unittest.main()
