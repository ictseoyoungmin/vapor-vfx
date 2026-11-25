"""Lexical guard only. Actual WGSL validation belongs to naga/runtime gates."""
import importlib.util
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('wgsl_source',ROOT/'tools/check_wgsl_source.py')
wgsl=importlib.util.module_from_spec(spec);spec.loader.exec_module(wgsl)
class ShaderSourceTests(unittest.TestCase):
    def test_old_target_regression_is_rejected(self):
        self.assertEqual(wgsl.violations('@binding(3) var<storage,read_write> target:array<f32>;'),[(1,'target')])
    def test_comments_are_not_identifiers(self):
        self.assertEqual(wgsl.violations('// target\n/* active /* pass */ filter */\nlet output_cells=0;'),[])
    def test_line_numbers_and_nested_comments(self):
        self.assertEqual(wgsl.violations('/* target\n*/\nlet target=0;'),[(3,'target')])
    def test_unclosed_comment_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):wgsl.violations('/* unfinished')
    def test_canonical_shaders_have_no_reserved_words(self):
        for path in (ROOT/'shaders/compute').glob('*.wgsl'):
            with self.subTest(path=path.name):self.assertEqual(wgsl.violations(path.read_text()),[])
if __name__=='__main__':unittest.main()
