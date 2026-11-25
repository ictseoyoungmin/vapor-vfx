import json,math,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from validate_cloud_equivalence import compare,native_options,read_f32
from package_runtime_candidate import checked_report
class CloudEquivalence(unittest.TestCase):
    def test_numeric_errors_not_hidden_by_average(self):
        self.assertTrue(compare([0.,1.],[0.,1.],1e-6)['passed']);r=compare([0.,1.1],[0.,1.],1e-6);self.assertEqual(r['violations'],1);self.assertFalse(r['passed']);self.assertGreater(r['rmse'],0)
        with self.assertRaises(ValueError):compare([float('nan')],[1.],1)
        with self.assertRaises(ValueError):compare([1.],[1.,2.],1)
    def test_exact_hero_recipe_forwarded(self):
        s=json.loads((ROOT/'contracts/cloud-hero.json').read_text());p=s['profiles']['hero'];o=native_options(s,p);self.assertEqual((o['width'],o['height'],o['steps']),(960,600,224));self.assertEqual(o['lighting']['shadow_steps'],40);self.assertEqual(o['lighting']['light_scale'],.8);self.assertEqual(o['material']['extinction'],.32);self.assertEqual(o['material']['thermal_fade'],0);self.assertEqual(o['lighting']['direction'],s['lighting']['light']['direction']);self.assertEqual(o['exposure'],.95)
    def test_release_rejects_blocked_stale_or_partial_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'report.json';receipt={'artifact_sha256':'artifact'};d={'status':'BLOCKED','complete':True};p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):checked_report(p,receipt,cloud=True)
            d={'status':'PASS','complete':True,'receipt':{'source_fingerprint':'old','artifact_sha256':'artifact'}};p.write_text(json.dumps(d))
            with patch('package_runtime_candidate.source_fingerprint',return_value='new'):
                with self.assertRaisesRegex(ValueError,'stale'):checked_report(p,receipt)
                d['receipt']['source_fingerprint']='new';p.write_text(json.dumps(d))
                with self.assertRaises(ValueError):checked_report(p,receipt,cloud=True)
                with self.assertRaises(ValueError):checked_report(p,receipt)
