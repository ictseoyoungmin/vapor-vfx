import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from conservative_transport import transport

def vel(shape,speed):
    nz,ny,nx=shape
    return [np.full((nz,ny,nx+1),speed),np.zeros((nz,ny+1,nx)),np.zeros((nz+1,ny,nx))]
class Conservation(unittest.TestCase):
    def test_stationary_is_exact(self):
        q=np.random.default_rng(2).random((5,6,7));r,loss,_=transport(q,vel(q.shape,0),.2,.2);np.testing.assert_array_equal(r,q);self.assertEqual(loss,0)
    def test_open_boundary_budget_and_positivity(self):
        q=np.random.default_rng(4).random((9,10,11));dx=.1;v=vel(q.shape,1.2);r,loss,n=transport(q,v,dx,.6);self.assertGreater(n,1);self.assertGreater(loss,0);self.assertGreaterEqual(float(r.min()),0);self.assertAlmostEqual(float(q.sum()-r.sum())*dx**3,loss,places=12)
    def test_inflow_does_not_create_scalar(self):
        q=np.zeros((7,6,5));r,loss,_=transport(q,vel(q.shape,-2),.1,.1);self.assertFalse(r.any());self.assertEqual(loss,0)
    def test_invalid_shape_and_negative_rejected(self):
        q=np.ones((4,4,4));v=vel(q.shape,1);self.assertRaises(ValueError,transport,q,v[:2],1,1);self.assertRaises(ValueError,transport,-q,v,1,1)
if __name__=='__main__':unittest.main()
