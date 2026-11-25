"""Run after tools/build.py --native. Writes RGBA and JSON; PNG if Pillow is installed."""
from pathlib import Path
import json,sys,time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game import Simulation
out=ROOT/'reports/local';out.mkdir(exist_ok=True)
with Simulation(cells=(16,20,16),cell_size=.04) as sim:
    sim.set_emitter(0,position=(.32,.1,.32),direction=(.15,1.,.1),radius=.055)
    start=time.perf_counter();sim.step(90);elapsed=time.perf_counter()-start
    metrics=sim.metrics()
    assert metrics['non_finite']==0 and metrics['density_integral']>0, "Real solver smoke failed"
    assert metrics['ticks']==90 and metrics['max_density']<=sim.config['density_cap'], "Clock/density contract failed"
    report={"profile":"game-mac-v1","backend":"rust-cpu","metrics":sim.metrics(),"elapsed_seconds":elapsed}
    (out/'python-smoke.json').write_text(json.dumps(report,indent=2))
    image=sim.render(eye=(1.1,.7,1.3),target=(.32,.38,.32),width=320,height=240)
    try:
        from PIL import Image
        straight=bytearray(image)
        for i in range(0,len(straight),4):
            alpha=image[i+3]/255
            for channel in range(3):
                linear=min(1.,image[i+channel]/255/alpha) if alpha>0 else 0.
                srgb=12.92*linear if linear<=.0031308 else 1.055*linear**(1/2.4)-.055
                straight[i+channel]=round(srgb*255)
        Image.frombytes('RGBA',(320,240),bytes(straight)).save(out/'python-smoke.png')
    except ImportError:(out/'python-smoke.rgba').write_bytes(image)
    print(json.dumps(report,indent=2))
