import copy
import hashlib
import json
import math
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from compare_baseline import compare, validate
from freeze_contract import dims

class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads((ROOT/'fixtures/v18-baseline-low.json').read_text())

    def test_frozen_contract_structure(self):
        frozen = json.loads((ROOT/'contracts/source_v18.json').read_text())
        self.assertEqual(len(frozen['integrity_sha256']), 46)
        self.assertEqual(hashlib.sha256((ROOT/'fixtures/v18-baseline-low.json').read_bytes()).hexdigest(), frozen['integrity_sha256']['tests/baseline_low.json'])
        self.assertTrue(all(len(h)==64 and all(c in "0123456789abcdef" for c in h) for h in frozen['integrity_sha256'].values()))
        self.assertEqual(frozen['algorithm']['projection'], 'Red-Black SOR')
        self.assertEqual(frozen['quality']['low']['sor'], 10)
        self.assertEqual(frozen['grid_default_texture_limit_assumption']['low']['coarse']['nx'], 51)
        self.assertEqual(frozen['grid_default_texture_limit_assumption']['low']['coarse']['ny'], 67)
        self.assertEqual(frozen['grid_default_texture_limit_assumption']['low']['coarse']['nz'], 59)
        self.assertEqual(frozen['grid_default_texture_limit_assumption']['low']['fine']['voxels'], 1612824)

    def test_parity_identity_passes(self):
        r = compare(self.base, self.base, 'strict')
        self.assertTrue(r['pass'])
        self.assertEqual(len(r['results']), 24)

    def test_fails_on_abs_error(self):
        bad = copy.deepcopy(self.base)
        bad['samples'][2]['spreadSlope'] += 0.041
        self.assertFalse(compare(self.base, bad)['pass'])

    def test_fails_on_mass_relative_error(self):
        bad = copy.deepcopy(self.base)
        bad['samples'][1]['mass'] *= 1.27
        self.assertFalse(compare(self.base, bad)['pass'])

    def test_fails_on_extra_or_missing_samples(self):
        bad = copy.deepcopy(self.base)
        bad['samples'].pop()
        with self.assertRaises(ValueError): compare(self.base, bad)
        bad = copy.deepcopy(self.base)
        bad['marks'].pop()
        with self.assertRaises(ValueError): compare(self.base, bad)

    def test_fails_on_nan_and_none(self):
        for value in (float('nan'), float('inf'), None):
            bad = copy.deepcopy(self.base)
            bad['samples'][0]['vmax'] = value
            with self.assertRaises(ValueError): compare(self.base, bad)

    def test_fails_on_quality_and_time_mismatch(self):
        bad = copy.deepcopy(self.base)
        bad['quality'] = 'mid'
        self.assertFalse(compare(self.base, bad)['pass'])
        bad = copy.deepcopy(self.base)
        bad['samples'][1]['t'] = 1.0000001
        with self.assertRaises(ValueError): compare(self.base, bad)

    def test_nested_gpu_candidate(self):
        actual = copy.deepcopy(self.base)
        actual['samples'] = [{'t': s['t'], 'm': {k: v for k, v in s.items() if k != 't'}} for s in actual['samples']]
        self.assertTrue(compare(self.base, actual)['pass'])

    def test_grid_fallback_budget(self):
        d = {'width': .64, 'height': .84, 'depth': .74}
        q = {'cell': .0055, 'up': 2, 'sor': 16}
        got = dims(d, q)
        self.assertLessEqual(got['fine']['voxels'], 11_000_000)
        self.assertLessEqual(got['fine']['width'], 16384)
        self.assertLess(got['effective_up'], 2)

if __name__ == '__main__': unittest.main()
