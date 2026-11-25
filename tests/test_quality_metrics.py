import math,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from quality_metrics import density_summary,atlas_summary,timing_summary
from profile_effects import checkpoint_ticks
from check_sdk import runtime_required

class QualityMetricsTests(unittest.TestCase):
    def test_empty_valid(self):
        s=density_summary(np.zeros((4,4,4)),cells=[4]*3,extent=[4]*3,source=[0]*3,direction=[1,0,0]);self.assertEqual(s['density_integral'],0);self.assertIsNone(s['plume']);self.assertIsNone(s['centroid_world'])
    def test_world_coordinates_anisotropic_grid(self):
        d=np.zeros((2,3,4));d[1,2,3]=2
        s=density_summary(d,cells=[4,3,2],extent=[4,6,6],origin=[-2,10,1],cap=2)
        self.assertEqual(s['density_integral'],12);self.assertEqual(s['centroid_world'],[1.5,15.,5.5]);self.assertEqual(s['bounds_min_world'],[1.,14.,4.]);self.assertEqual(s['bounds_max_world'],[2.,16.,7.]);self.assertEqual(s['saturation_mass_fraction'],1)
    def test_signed_axial_and_weighted_spread(self):
        d=np.zeros((1,1,4));d[0,0,:]=[1,0,2,1]
        s=density_summary(d,cells=[4,1,1],extent=[4,1,1],source=[1,.5,.5],direction=[2,0,0]);p=s['plume']
        self.assertEqual(p['axial_q05_q50_q95'],[-.5,1.5,2.5]);self.assertEqual(p['backward_mass_fraction'],.25);self.assertEqual(p['forward_mass_fraction'],.75);self.assertEqual(p['radial_rms'],0);self.assertAlmostEqual(p['axial_mean'],1.25)
    def test_radial_world_distance(self):
        d=np.ones((1,2,2));s=density_summary(d,cells=[2,2,1],extent=[2,4,1],source=[0,2,.5],direction=[1,0,0]);self.assertEqual(s['plume']['radial_rms'],1.)
    def test_boundary_fraction(self):
        d=np.zeros((3,3,3));d[0,1,1]=1;d[1,1,1]=3
        s=density_summary(d,cells=[3]*3,extent=[3]*3);self.assertEqual(s['outer_cell_mass_fraction'],.25)
    def test_invalid_field(self):
        for d in [np.full((1,1,1),float('nan')),np.full((1,1,1),-1.),np.ones((2,1,1)),np.full((1,1,1),3.)]:
            with self.subTest(d=d):
                with self.assertRaises(ValueError):density_summary(d,cells=[1]*3,extent=[1]*3,cap=2)
    def test_invalid_axis(self):
        with self.assertRaises(ValueError):density_summary(np.zeros((1,1,1)),cells=[1]*3,extent=[1]*3,source=[0]*3,direction=[0]*3)
    def test_atlas_layout_quantization(self):
        a=np.array([[[[255,4,0,255],[0,0,255,255]]]],np.uint8)
        s=atlas_summary(a.tobytes(),cells=[2,1,1],extent=[2,3,4],density_cap=2);self.assertEqual(s['density_integral'],24);self.assertEqual(s['centroid_world'],[.5,1.5,2]);self.assertEqual(s['density_quantization_step'],2/255)
    def test_malformed_atlas(self):
        for a in [b'',bytes([1,0,255,255]),bytes([0,0,0,0]),bytes([0,0,5,255])]:
            with self.assertRaises(ValueError):atlas_summary(a,cells=[1]*3,extent=[1]*3,density_cap=1)
    def test_timing(self):
        t=timing_summary([1,2,3]);self.assertEqual(t['p50_ms'],2);self.assertEqual(t['max_ms'],3);self.assertEqual(t['total_ms'],6)
        with self.assertRaises(ValueError):timing_summary([math.inf])
    def test_fixed_tick_schedule(self):
        self.assertEqual(checkpoint_ticks([.25,.5,.25,1],1/60),[15,30,60]);self.assertEqual(checkpoint_ticks([.001],1/60),[1])
        with self.assertRaises(ValueError):checkpoint_ticks([0],1/60)
    def test_explicit_gpu_or_wasm_requires_runtime(self):
        self.assertTrue(runtime_required(False,True,False));self.assertTrue(runtime_required(False,False,True));self.assertTrue(runtime_required(True,False,False));self.assertFalse(runtime_required(False,False,False))
if __name__=='__main__':unittest.main()
