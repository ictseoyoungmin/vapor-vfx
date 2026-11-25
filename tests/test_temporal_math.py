"""Independent CPU math audit of WebGPU temporal camera packets and FP16 anchors.
Not a shader interpreter or runtime GPU test.
"""
import json, subprocess, unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

class TemporalMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script="""
        import {packVolumeView} from './bindings/web/gpu-render.mjs';
        import {getPreset} from './bindings/web/effects.mjs';
        const keys=['cigarette_smoke','exhaled_aerosol','steam','smoke','flame'];
        const result=[];
        for(const key of keys){const p=getPreset(key,'low'),cells=p.config.cells,extent=cells.map(n=>n*p.config.cellSize),origin=[3,2,-4],center=extent.map((x,i)=>x/2+origin[i]),span=Math.max(...extent);
        for(const [width,height] of [[320,200],[200,320]]){const eye=[center[0]+span*.5,center[1]+span*.15,center[2]-span*1.65];const source={layout:'mac',cells,extent,origin};const packet=packVolumeView(source,{eye,target:center,aspect:width/height,material:p.material});result.push({key,width,height,extent,cells,packet:[...new Float32Array(packet)]});}}
        console.log(JSON.stringify(result));
        """
        cls.rows=json.loads(subprocess.check_output(['node','--input-type=module','-e',script],cwd=ROOT,text=True))
    @staticmethod
    def project(p,points,size):
        # WGSL resolve uses local anchor, previous basis, and texture-space Y down.
        v=points-p[8:11];depth=v@p[12:15]
        uv=np.stack((.5+.5*(v@p[16:19])/(depth*p[15]*p[19]), .5-.5*(v@p[20:23])/(depth*p[15])),axis=-1)
        return uv*np.asarray(size)
    def test_ray_pixel_roundtrip_and_y_orientation(self):
        for row in self.rows:
            p=np.array(row['packet'],dtype=np.float64);w,h=row['width'],row['height']
            pixels=np.array([[.5,.5],[w-.5,.5],[.5,h-.5],[w-.5,h-.5],[w/2,h/2],[w*.26,h*.75]])
            ndc=(pixels/[w,h]*2-1)*[1,-1]
            ray=p[12:15]+ndc[:,0,None]*p[15]*p[19]*p[16:19]+ndc[:,1,None]*p[15]*p[20:23]
            points=p[8:11]+ray*np.linalg.norm(row['extent'])
            np.testing.assert_allclose(self.project(p,points,(w,h)),pixels,atol=3e-4,rtol=0)
    def test_normalized_half_precision_anchor_error_outside_domain(self):
        rng=np.random.default_rng(31011);worst=0
        for row in self.rows:
            p=np.asarray(row['packet'],dtype=np.float64);ext=np.asarray(row['extent']);anchor=rng.random((1024,3));points=anchor*ext
            quantized=anchor.astype(np.float16).astype(np.float64)*ext
            error=np.linalg.norm(self.project(p,points,(row['width'],row['height']))-self.project(p,quantized,(row['width'],row['height'])),axis=-1)
            worst=max(worst,float(error.max()))
            tolerance=min(2*np.linalg.norm(ext/np.asarray(row['cells'])),.12*np.linalg.norm(ext))
            self.assertLess(float(np.linalg.norm(quantized-points,axis=1).max()),tolerance)
        print(f'Independent half-float projection audit: {len(self.rows)*1024} anchors; max screen error {worst:.6f} pixels at 320x200 / 200x320')
        self.assertLess(worst,.25)
    def test_jitter_strata_are_unique_and_unbiased(self):
        offsets=[(((i-1)*5)%8+.5)/8 for i in range(1,9)]
        self.assertEqual(sorted(offsets),[(i+.5)/8 for i in range(8)])
        self.assertEqual(sum(offsets)/8,.5)
