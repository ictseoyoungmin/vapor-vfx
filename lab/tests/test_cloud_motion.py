import sys,unittest,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud_motion import curl_velocity
from conservative_transport import transport
class CloudMotionTests(unittest.TestCase):
 def test_discrete_divergence_and_boundary(self):
  for t in [0,1,3.5]:
   u,v,w=curl_velocity([16,8,12],[16,8,12],t,2.)
   self.assertLess(np.abs(np.diff(u,axis=2)+np.diff(v,axis=1)+np.diff(w,axis=0)).max(),1e-12)
   for a,k in [(u,2),(v,1),(w,0)]:self.assertEqual(np.abs(np.take(a,[0,-1],axis=k)).max(),0.)
 def test_constant_and_mass(self):
  vel=curl_velocity([16,8,12],[16,8,12],1,1.)
  rho=np.ones((12,8,16));a,loss,_=transport(rho,vel,1.,.5);self.assertLess(np.max(np.abs(a-rho)),1e-12);self.assertEqual(loss,0)
  rho[1:-1,2:-2,3:-3]=.25;a,loss,_=transport(rho,vel,1.,.5);self.assertAlmostEqual(a.sum(),rho.sum(),places=9);self.assertEqual(loss,0);self.assertTrue(np.isfinite(a).all());self.assertGreater(np.abs(a-rho).sum(),0)
 def test_flowmap_zero_velocity_and_normalization(self):
  from cloud_flowmap import step_map,normalize
  coords=np.indices((8,8,8),dtype=np.float64);mac=curl_velocity([8,8,8],[8,8,8],0,0.)
  self.assertTrue(np.array_equal(step_map(coords,coords,mac,1.,.5),coords))
  a=np.full((4,4,4),.5);b,f=normalize(a,32.1,1);self.assertAlmostEqual(b.sum(),32.1);self.assertAlmostEqual(f,32.1/32.)
  with self.assertRaises(ArithmeticError):normalize(a,50,1)
