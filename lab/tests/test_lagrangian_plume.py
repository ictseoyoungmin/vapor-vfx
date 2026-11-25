import json,sys,unittest
from pathlib import Path
import numpy as np
from numba import set_num_threads
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'lab'))
from lagrangian_plume import Plume, deposition, velocity, basis
CAT={x['key']:x for x in json.loads((ROOT/'effects/presets.json').read_text())['presets']}
class LagrangianTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):set_num_threads(2)
    def test_cic_budget(self):
        points=np.array([[.5,.5,.5],[.6,.55,.4],[.2,.3,.4]]);mass=np.array([1e-5,2e-5,3e-5]);d,t,b=deposition(points,mass,np.array([1.,2.,3.]),[16,16,16],[1,1,1],.75,100.)
        self.assertAlmostEqual(b['grid_mass'],float(mass.sum()),places=12);self.assertAlmostEqual(b['closure'],0.,places=14);self.assertTrue(np.all(d>=0));self.assertTrue(np.all(t>=0))
    def test_boundary_and_saturation_budget(self):
        d,t,b=deposition(np.array([[.001,.5,.5]]),np.array([1.]),np.array([2.]),[8,8,8],[1,1,1],1.,.05)
        self.assertGreater(b['deposition_loss'],0.);self.assertGreater(b['saturation'],0.);self.assertAlmostEqual(b['closure'],0.,places=12);self.assertLessEqual(float(d.max()),.050001)
    def test_seeded_replay(self):
        a=Plume(CAT['cigarette_smoke'],'packets',markers=32);b=Plume(CAT['cigarette_smoke'],'packets',markers=32)
        for _ in range(18):a.advance();b.advance()
        np.testing.assert_array_equal(a.q,b.q);np.testing.assert_array_equal(a.mass,b.mass);self.assertAlmostEqual(float(a.mass.sum()),a.injected-a.decayed-a.outflow,places=13)
    def test_emission_identical_mass_by_model(self):
        a=Plume(CAT['exhaled_aerosol'],'base',markers=32);b=Plume(CAT['exhaled_aerosol'],'packets',markers=32)
        for _ in range(25):a.advance();b.advance()
        self.assertEqual(a.injected,b.injected);self.assertEqual(a.rng.bit_generator.state,b.rng.bit_generator.state)
    def test_axis_frame(self):
        b=basis([1,.08,0]);np.testing.assert_allclose(b@b.T,np.eye(3),atol=1e-14);self.assertGreater(np.linalg.det(b),0)
    def test_local_velocity_divergence_away_from_cutoffs(self):
        p=Plume(CAT['cigarette_smoke'],'packets',markers=32);t=1.5;v=p.rings(t);q=np.array([.12,.012,.014]);h=1e-5;div=0.
        for k in range(3):
            a=q.copy();b=q.copy();a[k]+=h;b[k]-=h;va=velocity(*a,t,p.par,v,p.table,p.td,p.model);vb=velocity(*b,t,p.par,v,p.table,p.td,p.model);div+=(va[k]-vb[k])/(2*h)
        self.assertLess(abs(div),.002)
