"""Larger uniform MAC domain audit. Uses the actual coupled reference solver,
original source profile and scalar transport, not a particle animation or Rust.
The change is domain extent/resolution, not a new validated turbulence closure.
"""
import argparse,copy,json
from pathlib import Path
from numba import set_num_threads
import bootstrap
from runtime_common import ROOT
from check_sdk import atomic_report
from resolved_plume import run
DOMAINS={
 'exhaled_aerosol':([112,56,56],.015,[.105,.36,.42]),
 'cigarette_smoke':([64,144,64],.0035,[.112,.035,.112]),
}
def full_preset(p):
    q=copy.deepcopy(p);cells,dx,pos=DOMAINS[p['key']]
    q['config'].update(cells=cells.copy(),cellSize=dx,origin=[0,0,0],fixedDt=1/60,pressureIterations=256)
    q['emitter']['position']=pos.copy();return q

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--effect',choices=DOMAINS,default='exhaled_aerosol');p.add_argument('--seconds',type=float,default=3);p.add_argument('--output',type=Path,required=True);p.add_argument('--threads',type=int,default=3);a=p.parse_args()
    if not .25<=a.seconds<=4 or not 1<=a.threads<=4:p.error('seconds .25..4 and threads 1..4')
    set_num_threads(a.threads);out=a.output;out.mkdir(parents=True,exist_ok=True);r={'status':'RUNNING','scope':__doc__,'rows':[]};path=out/'experiment.json';atomic_report(path,r)
    try:
        preset=next(p for p in json.loads((ROOT/'effects/presets.json').read_text())['presets'] if p['key']==a.effect);domain=full_preset(preset)
        r['rows'].append(run(preset,'seeded',a.seconds,out,domain=domain));r['status']='PASS_EXECUTION_ONLY';atomic_report(path,r)
    except BaseException as e:r.update(status='FAIL',error=str(e));atomic_report(path,r);raise
if __name__=='__main__':main()
