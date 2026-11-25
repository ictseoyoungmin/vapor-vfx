"""Validation-tool self tests; these do NOT execute or certify the Rust solver."""
import json,os,struct,subprocess,sys,tempfile,tomllib,unittest,zlib
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,runtime_common as common
from png_codec import write_rgba,composite_linear_premultiplied
from validate_runtime import parity,finite_tree
from check_sdk import atomic_report,incomplete_report

class RuntimeToolsTests(unittest.TestCase):
    def test_interrupted_validation_cannot_retain_old_success(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'validation.json';atomic_report(p,{'complete':True,'core_release_gates_passed':True})
            atomic_report(p,incomplete_report({'source':{'status':'PASS'}},cpu=True,gpu=False,wasm=False,active='rust'))
            value=json.loads(p.read_text());self.assertFalse(value['complete']);self.assertFalse(value['core_release_gates_passed']);self.assertFalse(value['cpu_runtime_gates_passed']);self.assertEqual(value['active_check'],'rust');self.assertEqual(value['checks']['source']['status'],'PASS')
            self.assertEqual(len(list(Path(t).iterdir())),1)
    def test_blocked_rerun_does_not_keep_previous_capture(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'cpu-vent.png').write_bytes(b'old capture');(root/'user-note.txt').write_text('preserve')
            common.clear_previous_outputs(root,['cpu-vent.png','captures.json'])
            self.assertFalse((root/'cpu-vent.png').exists());self.assertTrue((root/'user-note.txt').exists())
    def test_output_cleanup_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'keep.txt').write_text('preserve')
            with self.assertRaises(ValueError):common.clear_previous_outputs(root,['keep.txt','../escape'])
            self.assertTrue((root/'keep.txt').exists())
    def test_cpu_workspace_has_no_registry_dependency(self):
        root=build.cpu_workspace()
        for manifest in root.parent.glob('*/Cargo.toml'):
            data=tomllib.loads(manifest.read_text())
            for dep in data.get('dependencies',{}).values():self.assertEqual(set(dep),{'path'})
            self.assertTrue(Path(data['lib']['path']).is_file())
            self.assertNotIn('wgpu',manifest.read_text())
    def test_cpu_workspace_includes_new_actual_physics_tests(self):
        root=build.cpu_workspace();data=tomllib.loads((root.parent/'vapor-core/Cargo.toml').read_text())
        self.assertIn('cpu_physics',[t['name'] for t in data['test']]);self.assertIn('conservative_density',[t['name'] for t in data['test']]);self.assertIn('m2_density',[t['name'] for t in data['example']])
    def test_manifest_has_current_package_version(self):
        root=build.cpu_workspace()
        for manifest in root.parent.glob('*/Cargo.toml'):
            self.assertEqual(tomllib.loads(manifest.read_text())['package']['version'],tomllib.loads((ROOT/'Cargo.toml').read_text())['workspace']['package']['version'])
    def test_missing_binary_never_passes(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(FileNotFoundError):common.require_receipt(Path(t)/'missing.so')
    def test_unreceipted_fixture_never_passes(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'fixture.so';p.write_bytes(b'test fixture')
            with self.assertRaises(RuntimeError):common.require_receipt(p)
    def test_receipt_detects_changed_binary(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'sample';p.write_bytes(b'unit-test-only')
            common.write_receipt(p,features=['cpu'],command=['TEST-NOT-RUST'],rustc='test only')
            p.write_bytes(b'modified')
            with self.assertRaises(RuntimeError):common.require_receipt(p)
    def test_receipt_detects_stale_sources(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'sample';p.write_bytes(b'unit-test-only')
            common.write_receipt(p,features=['cpu'],command=[],rustc='test only')
            with patch.object(common,'source_fingerprint',return_value='changed'):
                with self.assertRaises(RuntimeError):common.require_receipt(p)
    def test_cpu_artifact_cannot_satisfy_gpu_gate(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'sample';p.write_bytes(b'unit-test-only')
            common.write_receipt(p,features=['cpu'],command=[],rustc='test only')
            with self.assertRaises(RuntimeError):common.require_receipt(p,gpu=True)
    def test_png_dimensions_and_scanlines(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'sample.png';pixels=bytes([0,1,2,3,4,5,6,7]);write_rgba(p,2,1,pixels)
            raw=p.read_bytes();self.assertEqual(raw[:8],b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II',raw[16:24]),(2,1))
            i=8;data=b''
            while i<len(raw):
                n=struct.unpack('>I',raw[i:i+4])[0]
                if raw[i+4:i+8]==b'IDAT':data+=raw[i+8:i+8+n]
                i+=n+12
            self.assertEqual(zlib.decompress(data),b'\0'+pixels)
    def test_png_rejects_short_buffer(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):write_rgba(Path(t)/'bad.png',2,2,b'\0'*15)
    def test_premultiplied_linear_to_srgb(self):
        self.assertEqual(composite_linear_premultiplied(bytes([0,0,0,0]),(0,0,0)),bytes([0,0,0,255]))
        self.assertEqual(composite_linear_premultiplied(bytes([255]*4)),bytes([255]*4))
        self.assertGreater(composite_linear_premultiplied(bytes([128,0,0,255]))[0],128)
    def test_parity_thresholds_are_fixed(self):
        self.assertTrue(parity([1.],[1.001])['passed'])
        self.assertFalse(parity([1.],[1.1])['passed'])
        with self.assertRaises(AssertionError):parity([1.],[])
    def test_nonfinite_metrics_detected(self):
        self.assertFalse(finite_tree({'nested':[1.,float('nan')]}));self.assertTrue(finite_tree({'ticks':3,'m':1.}))
    def test_optimized_python_cannot_disable_runtime_assertions(self):
        p=subprocess.run([sys.executable,'-O',str(ROOT/'tools/validate_runtime.py'),'--help'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0);self.assertIn('do not run Python with -O',p.stderr)

if __name__=='__main__':unittest.main()
