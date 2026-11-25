import unittest,sys,json,copy
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'lab'))
from coupled_density import source_distribution,Coupled

class CoupledDensityTests(unittest.TestCase):
    def setUp(self):
        self.p=next(p for p in json.loads((ROOT/'effects/presets.json').read_text())['presets'] if p['key']=='cigarette_smoke')
    def test_physical_source_invariant_grid_phase_and_resolution(self):
        for scale in [.5,1,2,4]:
            c=copy.deepcopy(self.p['config']);c['cells']=[int(n*scale) for n in c['cells']];c['cellSize']/=scale
            for phase in [0,.25,.5,.75]:
                e=copy.deepcopy(self.p['emitter']);e['position'][0]+=phase*c['cellSize'];e['direction']=[.3,1,.2]
                q,m=source_distribution(e,c);self.assertGreater(m,0);self.assertAlmostEqual(q.sum()*c['cellSize']**3/m,1.,places=12);self.assertTrue(np.all(q>=0))
    def test_clipped_source_is_not_renormalized(self):
        e=copy.deepcopy(self.p['emitter']);e['position'][0]=0
        with self.assertRaises(ValueError):source_distribution(e,self.p['config'])
    def test_coupled_mass_budget(self):
        s=Coupled(self.p,'low','physical')
        for _ in range(12):
            s.step();b=s.budgets[-1];self.assertLess(abs(b['residual']),max(1e-14,b['injected']*1e-6));self.assertGreaterEqual(b['outflow'],0.)
        self.assertGreater(float(s.rho.sum()),0)
    def test_emission_stops_without_gain(self):
        s=Coupled(self.p,'low','physical')
        for _ in range(8):s.step()
        before=float(s.rho.sum(dtype=np.float64));s.advance_scalars(False,0.,0.)
        self.assertEqual(s.budgets[-1]['injected'],0.);self.assertLessEqual(float(s.rho.sum(dtype=np.float64)),before+1e-10)
if __name__=='__main__':unittest.main()
