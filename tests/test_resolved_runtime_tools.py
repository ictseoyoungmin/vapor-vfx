"""Report/capture boundary checks only: no Rust runtime substitution."""
import sys,unittest,tempfile,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from validate_resolved_plume import check_metrics,convert_ppm

class ResolvedRuntimeToolTests(unittest.TestCase):
    def test_capture_conversion_and_bad_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'x.ppm';f.write_bytes(b'P6\n2 1\n255\n'+bytes(range(6)));p=convert_ppm(f);self.assertEqual(p.read_bytes()[:8],b'\x89PNG\r\n\x1a\n')
            f.write_bytes(b'P6\n2 1\n255\n'+bytes(range(5)))
            with self.assertRaises(ValueError):convert_ppm(f)
    def test_metrics_differentiate_pressure_and_velocity(self):
        row=dict(effect='cigarette_smoke',mode='matched',tick=1,seconds=.008333,density_integral=.0009,divergence_rms=1e-6,pressure_residual_rms=1e-6,clamps=0,step_ms=10,injected=.001,outflow=.0001,decayed=0,saturated=0,budget_residual=0,substeps=1,cg_iterations=12,cg_initial_rms=1,cg_residual_rms=1e-6)
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'metrics.csv'
            def write(r):
                with f.open('w',newline='') as out:w=csv.DictWriter(out,fieldnames=r.keys());w.writeheader();w.writerow(r)
            write(row);self.assertFalse(check_metrics(f,1)['full_plume_capture_eligible'])
            for change in ({'cg_residual_rms':.01},{'divergence_rms':.01},{'clamps':1},{'density_integral':.001}):
                write({**row,**change})
                with self.assertRaises(ValueError):check_metrics(f,1)
            write(row)
            with self.assertRaises(ValueError):check_metrics(f,2)
if __name__=='__main__':unittest.main()
