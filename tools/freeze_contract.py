#!/usr/bin/env python3
"""Freeze *source-derived* v18 contracts without executing app code.

Run only with --write when intentionally accepting a new source snapshot.
--check (default) fails closed when source code or frozen snapshots drift.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "history/legacy/v18"
DEST = ROOT / "contracts/source_v18.json"
# Freeze every delivered legacy file, not just selected modules. An added or
# deleted file also changes the manifest and fails --check.
def input_files() -> list[str]:
    return sorted(str(p.relative_to(LEGACY)).replace('\\', '/') for p in LEGACY.rglob('*') if p.is_file())


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def object_block(src: str, start: str) -> str:
    found = re.search(start + r'\s*=\s*\{', src)
    if found is None:
        raise ValueError(f"missing JS object: {start}")
    pos = found.end() - 1
    depth = 0
    for i in range(pos, len(src)):
        if src[i] == '{': depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[pos + 1:i]
    raise ValueError(f"unclosed JS object: {start}")


def numbers(obj: str) -> dict[str, float | int]:
    # Only accepts simple literal numeric properties: never eval JavaScript.
    pat = r'\b(\w+)\s*:\s*(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?=\s*(?:[,}\n]|$))'
    return {k: (int(v) if re.fullmatch(r'-?\d+', v) else float(v)) for k, v in re.findall(pat, obj)}


def quality(src: str) -> dict:
    b = object_block(src, r'export\s+const\s+QUALITY')
    q = {}
    for key in ('low', 'mid', 'high', 'ultra'):
        entry = re.search(r'\b' + key + r'\s*:\s*\{([^{}]+)\}', b)
        if entry is None: raise ValueError(f"missing quality {key}")
        n = numbers(entry.group(1))
        if set(n) != {'cell', 'up', 'sor', 'steps', 'stepScale', 'scale', 'lightEvery'}:
            raise ValueError(f"quality {key}: incomplete numbers: {n}")
        q[key] = n
    return q


def dims(dom: dict, q: dict, max_texture: int = 16384) -> dict:
    cell = q['cell']; up = q['up']; budget = 11_000_000
    nx, ny, nz = [max(24, math.floor(dom[d] / cell + 0.5)) for d in ('width', 'height', 'depth')]
    def atlas(x: int, y: int, z: int):
        tx = math.ceil(math.sqrt(z * y / x)); ty = math.ceil(z / tx)
        return {'nx': x, 'ny': y, 'nz': z, 'tx': tx, 'ty': ty, 'width': x*tx, 'height': y*ty, 'voxels': x*y*z}
    coarse = atlas(nx, ny, nz)
    while True:
        fine = atlas(math.ceil(nx*up), math.ceil(ny*up), math.ceil(nz*up))
        fits = fine['width'] <= max_texture and fine['height'] <= max_texture and fine['voxels'] <= budget
        if fits or up <= 1.0: break
        up = max(1.0, up - 0.25)
    return {'coarse': coarse, 'fine': fine, 'effective_up': up, 'fine_cell': cell/up,
            'max_texture_assumed': max_texture, 'fine_budget': budget}


def build() -> dict:
    main = (LEGACY/'src/main.js').read_text('utf-8')
    fluid = (LEGACY/'src/fluid.js').read_text('utf-8')
    breath = (LEGACY/'src/breath.js').read_text('utf-8')
    health = (LEGACY/'src/health.js').read_text('utf-8')
    sh = (LEGACY/'src/shaders.js').read_text('utf-8')
    dom = numbers(object_block(fluid, r'export\s+const\s+DOMAIN'))
    if set(dom) != {'width','height','depth'}: raise ValueError('domain fields changed')
    q = quality(fluid)
    ui = numbers(object_block(main, r'const\s+DEF'))
    sim = numbers(object_block(fluid, r'this\.P'))
    limits = numbers(object_block(health, r'export\s+const\s+LIMITS'))
    if not all(k in ui for k in ('speedMul','vort','buoy','decay','settle','sigma')): raise ValueError('UI defaults changed syntax')
    if not all(k in sim for k in ('omega','mac','macS','warm','inertia','drag')): raise ValueError('solver fields changed syntax')
    if not all(k in limits for k in ('speedCap','speedCapMin')): raise ValueError('health limit fields changed')
    if not re.search(r'for\s*\(let i = 0; i < P\.iters; i\+\+\)', fluid): raise ValueError('SOR loop not found')
    if not re.search(r'for\s*\(let col = 0; col < 2; col\+\+\)', fluid): raise ValueError('SOR coloring not found')
    if 'FRAG_SOR' not in sh or 'faceOff(int a)' not in sh: raise ValueError('MAC/SOR shaders not found')
    if 'Fritsch–Carlson' not in breath: raise ValueError('PCHIP implementation changed')
    if not re.search(r'const STEP = 1\s*/\s*60\s*;', main): raise ValueError('fixed dt changed')
    stages = ['force','curl','vort','advVA','advVB','solid','div','sor','grad','advAs','advBs','srcS','advAm','srcM','advAf','advBf','srcF']
    # Checks that implementation invokes every expected pass, in that order;
    # the SOR invocation is nested and repeats twice per iteration.
    step = fluid[fluid.index('  step(dt, time) {'):fluid.index('  /** 광량 볼륨 갱신 */')]
    starts = [step.index('this._run(f,') if k == 'force' else step.index('this._run(m.' + k + ',') for k in stages]
    if starts != sorted(starts): raise ValueError('GPU pass order changed')
    base = json.loads((LEGACY/'tests/baseline_low.json').read_text('utf-8'))
    if base['quality'] != 'low' or len(base['marks']) != len(base['samples']) or base['marks'] != [s['t'] for s in base['samples']]:
        raise ValueError('low baseline invalid sample timing')
    return {
      'schema': 'vapor.source-contract/1',
      'origin': 'user-upload vapor_v18.zip; archived legacy/v18 untouched',
      'integrity_sha256': {f: digest(LEGACY/f) for f in input_files()},
      'domain_m': dom, 'quality': q,
      'grid_default_texture_limit_assumption': {key: dims(dom, val) for key, val in q.items()},
      'runtime_ui_defaults': ui, 'solver_constructor_defaults': sim,
      'health_limits': limits,
      'algorithm': {'grid': 'MAC/staggered-face', 'velocity_advection': 'RK2+MacCormack',
                    'projection': 'Red-Black SOR', 'projection_omega_initial': sim['omega'],
                    'projection_passes_per_iteration': 2, 'fixed_dt_seconds': 1/60,
                    'gpu_backend': 'Three.js / GLSL ES 3.0 / WebGL2 RGBA atlas',
                    'passes_per_step': stages},
      'stored_low_baseline': {'kind': 'imported-not-remeasured', 'gpu': base['gpu'], 'marks': base['marks'],
                              'values_are': ['front','centroidAlong','spreadSlope','backFrac','vmax','mass']},
      'known_document_discrepancy': [
          'reference/settings.json reports legacy Jacobi and old defaults; not active runtime config',
          'reference/SCIENCE_LIMITATIONS_KO.md section 3 still describes collocated + Jacobi, superseded by v7/v18 notes'
      ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--write', action='store_true', help='explicitly freeze source; never use in routine checks')
    g.add_argument('--check', action='store_true', help='default')
    args = ap.parse_args()
    new = build()
    if args.write:
        DEST.parent.mkdir(parents=True, exist_ok=True)
        DEST.write_text(json.dumps(new, ensure_ascii=False, indent=2, sort_keys=True)+'\n', 'utf-8')
        print('FROZEN', DEST)
    else:
        if not DEST.exists(): print('FAIL contract missing; use --write once'); sys.exit(2)
        old = json.loads(DEST.read_text('utf-8'))
        if old != new:
            print('FAIL contract drift (source or algorithm changed): baseline needs review'); sys.exit(1)
        print('PASS source hashes, grid contract, solver pass order, low baseline integrity')

if __name__ == '__main__': main()
