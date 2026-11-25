#!/usr/bin/env python3
"""Recreate the fictional V2 visual study with the existing Lab renderer.
Default is one preview; --full is an explicit offline bake, not runtime physics.
"""
import argparse, os, shutil, subprocess, sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'reports/local/lab/airborne-smoke')
    p.add_argument('--frame',type=int,default=56,help='volume frame index, 29–120')
    p.add_argument('--full',action='store_true',help='render the entire fictional V2 study')
    a=p.parse_args();out=a.output.resolve()
    if not 29<=a.frame<=120:p.error('--frame must be 29–120')
    if not shutil.which('node'):p.error('Node.js is required')
    if a.full and not shutil.which('ffmpeg'):p.error('ffmpeg is required for --full')
    out.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'VAPOR_AIRBORNE_OUTPUT':str(out),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    def run(cmd):subprocess.run(cmd,cwd=HERE,env=env,check=True)
    run([sys.executable,'backdrop.py'])
    indices=range(29,121) if a.full else [a.frame]
    for i in indices:
        run([sys.executable,'bake.py',str(i)])
        if a.full and i==29:run(['node','render.mjs','0'])
        run(['node','render.mjs',str(i)])
        if a.full:
            for ext in ('rho','heat'):(out/'fields'/f'{i:04d}.{ext}').unlink()
    if a.full:
        run([sys.executable,'scene.py'])
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-framerate','24','-i',str(out/'scene/%04d.jpg'),'-frames:v','181','-c:v','libx264','-preset','medium','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'airborne-v2.mp4')],check=True)
        print(out/'airborne-v2.mp4')
    else:
        rgba=(out/'renders'/f'{a.frame:04d}.rgba').read_bytes()
        Image.frombytes('RGBA',(960,540),rgba).save(out/'preview.png')
        print(out/'preview.png')
if __name__=='__main__':main()
