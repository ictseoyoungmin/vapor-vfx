import json,sys,unittest,copy
from pathlib import Path
import numpy as np
from numba import set_num_threads
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'lab'))
from resolved_plume import source_basis,fast_advect,Resolved,local_preset,CASES
from reference_fluid import lattice,advect
from pressure_audit import apply,cg,exact

class ResolvedPlumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        set_num_threads(2);cls.p={p['key']:p for p in json.loads((ROOT/'effects/presets.json').read_text())['presets']}
    def test_fast_mac_advection_matches_independent_scipy(self):
        rng=np.random.default_rng(11);nz,ny,nx=5,6,7
        v=[rng.uniform(-.4,.4,(nz+(a==2),ny+(a==1),nx+(a==0))).astype(np.float32) for a in range(3)]
        for a,field in enumerate([*v,rng.random((nz,ny,nx),dtype=np.float32)]):
            ref=advect(field,v,lattice(field.shape,a),a,.65);q=fast_advect(field,*v,a,.65)
            np.testing.assert_allclose(q,ref,atol=2e-6,rtol=2e-6)
    def test_physical_support_and_rotating_seed_bounds(self):
        for key,p in self.p.items():
            if key not in CASES:continue
            p=local_preset(p);e=p['emitter'];c=p['config'];d=np.array(e['direction'],float);d/=np.linalg.norm(d);n=c['cells'];dx=c['cellSize']
            self.assertGreaterEqual(2*e['radius']/dx,4)
            for a in range(4):
                shape=tuple(n[i]+int(a==i) for i in [2,1,0]);w,x,y=source_basis(lattice(shape,a),e,dx,a,d)
                self.assertTrue(np.all((w>=0)&(w<=1)));self.assertGreater(w.sum(),0)
                self.assertLessEqual(float(np.hypot(x,y).max()),1.00001)
                self.assertEqual(float(w[0,0,0]),0.)
    def test_pressure_cg_against_exact_dst(self):
        rng=np.random.default_rng(7);b=rng.normal(size=(12,14,16))*.00001
        q,it=cg(b,.01);self.assertLessEqual(it,256);np.testing.assert_allclose(q,exact(b),atol=1e-9,rtol=5e-5)
        self.assertLess(float(np.sqrt(np.mean((b-apply(q.astype(np.float64)))**2)))/.01**2,1e-5)
    def test_matched_source_and_seed_advance_actual_fields(self):
        for mode in ('matched','seeded'):
            s=Resolved(self.p['cigarette_smoke'],mode)
            for _ in range(3):_,div=s.step()
            self.assertLess(div,1e-4);self.assertGreater(float(s.rho.sum()),0)
            self.assertLess(abs(s.budgets[-1]['residual']),1e-11)
if __name__=='__main__':unittest.main()
