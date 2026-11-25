"""Independent quadrature test. No Rust runtime claim."""
import unittest,sys,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'lab'))
from reference_fluid import lattice
from resolved_source_lab import physical_weights,physical_integral
class SourceQuadrature(unittest.TestCase):
    def test_physical_source_quadrature(self):
        # Interior source and 3 oblique/shifted placements at 2 resolutions.
        for dx,n in [(.012,24),(.004,72)]:
            p=lattice((n,n,n),3)
            for axis,pos in [([0,1,0],[.12,.10,.12]),([1,1,0],[.121,.104,.127]),([1,-.2,1],[.128,.108,.114])]:
                d=np.asarray(axis,dtype=float);d/=np.linalg.norm(d);e={'radius':.007,'length':.018,'position':pos}
                w=physical_weights(p,e,dx,d,3,6);actual=float(w.sum(dtype=np.float64))*dx**3;target=physical_integral(e)
                self.assertGreater(actual,0);self.assertLess(abs(actual/target-1),.05);self.assertAlmostEqual(actual*(target/actual)/target,1,places=12)
                self.assertTrue(np.all((w>=0)&(w<=1)))
if __name__=='__main__':unittest.main()
