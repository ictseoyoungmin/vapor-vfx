import unittest,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nested_transport import advance,constant_velocity

class NestedTransport(unittest.TestCase):
    def test_bidirectional_interface_closure(self):
        for u in [0.6,-0.6]:
            f=np.zeros((8,8,8));c=np.zeros((4,4,8));
            if u>0:f[2:6,2:6,-2:]=1
            else:c[1:3,1:3,:2]=1
            vf=constant_velocity(f.shape,u);vc=constant_velocity(c.shape,u);m=f.sum()*.05**3+c.sum()*.1**3
            f2,c2,r=advance(f,c,vf,vc,.05,2,.18);self.assertGreater(r['interface_transfer']*u,0);self.assertAlmostEqual(f2.sum()*.05**3+c2.sum()*.1**3+r['outer_outflow'],m,places=12);self.assertGreaterEqual(min(f2.min(),c2.min()),0)
    def test_nonuniform_velocity_area_consistency(self):
        f=np.full((8,8,4),.4);c=np.full((4,4,4),.2);vf=constant_velocity(f.shape,0.);vc=constant_velocity(c.shape,0.);u=np.linspace(-.2,.4,64).reshape(8,8);vf[0][:]=u[:,:,None];vc[0][:]=u.reshape(4,2,4,2).mean((1,3))[:,:,None];m=f.sum()*.05**3+c.sum()*.1**3
        a,b,r=advance(f,c,vf,vc,.05,2,.1);self.assertAlmostEqual(a.sum()*.05**3+b.sum()*.1**3+r['outer_outflow'],m,places=12)
        vc[0][:,:,0]+=0.1
        with self.assertRaisesRegex(ValueError,'interface'):advance(f,c,vf,vc,.05,2,.1)
    def test_static_and_invalid(self):
        f=np.ones((8,8,4));c=np.ones((4,4,4));vf=constant_velocity(f.shape,0);vc=constant_velocity(c.shape,0);a,b,r=advance(f,c,vf,vc,.05,2,1);np.testing.assert_array_equal(a,f);np.testing.assert_array_equal(b,c);self.assertEqual(r['interface_transfer'],0)
        with self.assertRaises(ValueError):advance(f,c,vf,vc,.05,3,1)
