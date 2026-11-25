import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from detail_curl_math import curl,old_curl,velocity_bases

class CurlMath(unittest.TestCase):
    def setUp(self):
        self.e=np.array([.24,.384,.24]);self.dx=.003;self.k=100;self.a=.1
        self.q=np.random.default_rng(19).uniform(.001,.999,(4096,3))*self.e
    def test_continuous_divergence_including_taper(self):
        h=1e-6;div=np.zeros(len(self.q))
        for i in range(3):
            d=np.eye(3)[i]*h;div+=(curl(self.q+d,self.e,self.k,self.a,1.125,self.dx)[:,i]-curl(self.q-d,self.e,self.k,self.a,1.125,self.dx)[:,i])/(2*h)
        self.assertLess(np.sqrt(np.mean(div**2)),2e-4)
    def test_domain_wall_velocity_and_exterior_zero(self):
        for i in range(3):
            for x in (0,self.e[i],-.01,self.e[i]+.01):
                q=self.q.copy();q[:,i]=x;self.assertFalse(np.any(curl(q,self.e,self.k,self.a,2,self.dx)))
    def test_amplitude_bound(self):
        for k in (0.1,8,55,100):
            for dx in (.003,.01,.03):
                v=curl(self.q,self.e,k,self.a,1.45,dx)
                self.assertLessEqual(np.max(np.linalg.norm(v,axis=-1)),2*self.a+1e-12)
    def test_phase_wrap(self):
        np.testing.assert_allclose(curl(self.q,self.e,self.k,self.a,16-1e-7,self.dx),curl(self.q,self.e,self.k,self.a,-1e-7,self.dx),atol=1e-10)
        np.testing.assert_allclose(curl(self.q,self.e,self.k,self.a,0,self.dx),curl(self.q,self.e,self.k,self.a,16,self.dx),atol=1e-10)
    def test_unresolved_band_culled(self):
        self.assertFalse(np.any(curl(self.q,self.e,self.k,self.a,1,.04)))
        self.assertGreater(np.max(np.abs(curl(self.q,self.e,self.k,self.a,1,.003))),.02)
    def test_precomputed_basis_matches_continuous_formula(self):
        q=self.q[:128].reshape(4,4,8,3);t=1.234
        for name,expected in [('legacy',old_curl(q,self.k,self.a,t)),('curl',curl(q,self.e,self.k,self.a,t,self.dx))]:
            b,w,phi=velocity_bases(q,self.e,self.k,self.dx,name);v=np.einsum('i,iczyx->zyxc',self.a*np.cos(w*t+phi),b)
            np.testing.assert_allclose(v,expected,atol=2e-8)
    def test_zero_amplitude_and_local_coordinate_translation(self):
        self.assertFalse(np.any(curl(self.q,self.e,self.k,0,1,self.dx)))
        offset=np.array([13.,-7.,100.]);np.testing.assert_allclose(curl(self.q,self.e,self.k,self.a,1,self.dx),curl((self.q+offset)-offset,self.e,self.k,self.a,1,self.dx),atol=1e-12)
        self.assertGreater(np.max(np.abs(old_curl(self.q,self.k,self.a,1,offset)-old_curl(self.q,self.k,self.a,1))),.01)
if __name__=='__main__':unittest.main()
