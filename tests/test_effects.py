import ctypes as C,sys,unittest,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game import get_preset,ember_visual,create_effect_from_recipe
from vapor_game.effects import _Procedural,_validate_material
class EffectTests(unittest.TestCase):
    def test_catalog_quality_preserves_extent(self):
        for i in range(1,9):
            b=get_preset(i);self.assertEqual(b['id'],i)
            for q in ('low','medium','high'):
                d=get_preset(i,q);self.assertEqual([n*d['config']['cellSize'] for n in d['config']['cells']],[n*b['config']['cellSize'] for n in b['config']['cells']]);_validate_material(d['material'])
    def test_catalog_no_mutation(self):
        p=get_preset(3);p['config']['cells'][0]=4;self.assertNotEqual(get_preset(3)['config']['cells'][0],4)
    def test_layout(self):self.assertEqual(C.sizeof(_Procedural),40)
    def test_bad_quality_id(self):
        for a,b in [(9,'medium'),(1,'none'),(True,'medium')]:
            with self.assertRaises(ValueError):get_preset(a,b)
    def test_ember(self):
        self.assertEqual(ember_visual(1,False,.5)['intensity'],0);self.assertEqual(ember_visual(1,True,.5)['ash_fraction'],.5)
        with self.assertRaises(ValueError):ember_visual(math.nan)
    def test_recipe_injection(self):
        with self.assertRaises(ValueError):create_effect_from_recipe({'schema':'vapor.effect-recipe/1','preset':'steam','execution':{'backend':'gpu'}})
    def test_data_copy(self):self.assertEqual((ROOT/'effects/presets.json').read_bytes(),(ROOT/'bindings/python/vapor_game/presets.json').read_bytes())
