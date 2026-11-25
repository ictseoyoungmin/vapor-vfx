"""Static publication boundaries and relative-link regression tests; no native/GPU runtime."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_pages',ROOT/'tools/build_pages.py')
pages=importlib.util.module_from_spec(spec);spec.loader.exec_module(pages)

class PagesTests(unittest.TestCase):
    def test_lightweight_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'site'; report=pages.build(out,'none')
            self.assertFalse(any(report['asset_groups'].values()))
            self.assertFalse((out/'examples/airborne-smoke/inspect.html').exists())
            self.assertNotIn('href="inspect.html"',(out/'examples/airborne-smoke/index.html').read_text())
            self.assertIn('examples/airborne-smoke/index.html',(out/'examples.html').read_text())
            self.assertNotIn('href="examples/animated-cloud/index.html"',(out/'examples.html').read_text())
            self.assertNotIn('@@FEATURED@@',(out/'index.html').read_text())
            self.assertFalse(report['runtime_binaries']);self.assertFalse(report['release_certification'])
            self.assertGreater(report['static_references_checked'],60)

    def test_full_assets_when_available(self):
        if not all(pages.available_assets('auto').values()):self.skipTest('optional assets not present in source checkout')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'site';report=pages.build(out,'full')
            self.assertTrue(all(report['asset_groups'].values()))
            self.assertTrue((out/'examples/airborne-smoke/inspect.html').exists())
            self.assertTrue((out/'assets/cloud-motion/sequence.vpa').is_file())
            self.assertEqual((out/'assets/airborne-smoke/smoke-0056.vpf').read_bytes(),(ROOT/'assets/airborne-smoke/smoke-0056.vpf').read_bytes())
            self.assertNotIn('href="../../history/',(out/'examples/high-fidelity/index.html').read_text())

    def test_missing_groups_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(pages,'ROOT',Path(tmp)):
            self.assertFalse(any(pages.available_assets('auto').values()))
            with self.assertRaises(ValueError):pages.available_assets('full')

    def test_broken_absolute_escape_and_native_rejected(self):
        for bad in ('/rooted.html','missing.html','../outside.html'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);(p/'index.html').write_text(f'<a href="{bad}">broken</a>')
                with self.assertRaises(ValueError):pages.verify_site(p)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'vapor.wasm').write_bytes(b'not a real binary')
            with self.assertRaises(ValueError):pages.verify_site(p)

    def test_hosted_variants_do_not_offer_unbuilt_rust(self):
        groups=pages.available_assets('none')
        for folder, expected in [('fidelity-cloud','<option value="rust" disabled>'),('webgpu-volume','<option value="hybrid" disabled>')]:
            original=(ROOT/'examples'/folder/'index.html').read_text()
            self.assertIn(expected,pages.hosted_example(folder,original,groups))

    def test_output_requires_clean_staging_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):pages.build(Path(tmp),'none')

if __name__=='__main__':unittest.main()
