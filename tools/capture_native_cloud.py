"""Capture a high-quality cloud with the actual Rust Fidelity CPU ABI.
Requires a verified native build, not JS or Python density generation.
"""
import argparse,sys,time,json
from pathlib import Path
from runtime_common import ROOT,default_library,require_receipt,sha256,clear_previous_outputs
from png_codec import write_rgba
from check_sdk import atomic_report
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game.fidelity import FidelityCPU

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hero',action='store_true',help='Same density grid and camera as the 0.13 JS hero. Slow offline reference.');p.add_argument('--output',type=Path,default=ROOT/'reports/local/native-cloud');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);clear_previous_outputs(out,['cloud.png','capture.json']);report={'status':'BLOCKED','evidence':'Actual Rust CPU ABI only'};atomic_report(out/'capture.json',report)
    try:
        report['receipt']=require_receipt(default_library());sdk=FidelityCPU(default_library());cells=[176,88,120] if a.hero else [96,48,64];extent=[144,72,96];width,height,steps=(960,600,224) if a.hero else (480,300,128)
        t=time.perf_counter();field=sdk.generate('cumulus_cloud',cells=cells,extent=extent);generation_ms=(time.perf_counter()-t)*1000
        t=time.perf_counter();pixels,alpha=sdk.render(field,eye=[110,15,-150],target=[72,32,48],width=width,height=height,steps=steps,exposure=.95,material={'colour':[.96,.97,1.],'extinction':.32,'anisotropy':.58,'albedo':.95,'emission':0.,'thermal_fade':0.,'ambient':.10},lighting={'light_scale':.8,'shadow_steps':40});render_ms=(time.perf_counter()-t)*1000
        if not any(v>0.001 for v in alpha):raise RuntimeError('empty cloud')
        write_rgba(out/'cloud.png',width,height,pixels);report.update(status='PASS',cells=cells,extent=extent,width=width,height=height,steps=steps,generation_ms=generation_ms,render_ms=render_ms,capture_sha256=sha256(out/'cloud.png'));atomic_report(out/'capture.json',report);return 0
    except FileNotFoundError as e:report.update(status='BLOCKED',reason=str(e));code=2
    except Exception as e:report.update(status='FAIL',reason=str(e));code=1
    atomic_report(out/'capture.json',report);print(report['status'],report['reason']);return code
if __name__=='__main__':raise SystemExit(main())
