#!/usr/bin/env python3
"""Fail-closed numerical regression check. Zero tolerance for missing/NaN data.

Accepts v18 samples as either {quality,marks,samples:[{t,front,...}]} or
{quality,marks,samples:[{t,m:{front,...}}]}.
This checks *legacy parity*, not scientific correctness.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'history/legacy/v18/tests/baseline_low.json'
METRICS = ('front', 'centroidAlong', 'spreadSlope', 'backFrac', 'vmax', 'mass')
TOL = {'front': 0.08, 'centroidAlong': 0.06, 'spreadSlope': 0.04,
       'backFrac': 0.03, 'vmax': 3.0, 'massRel': 0.25}


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate(payload, label):
    if not isinstance(payload, dict) or not payload.get('quality') or not isinstance(payload.get('samples'), list):
        raise ValueError(f'{label}: expected {{quality, marks, samples}}')
    marks = payload.get('marks')
    if not isinstance(marks, list) or not marks or not all(finite(t) and t >= 0 for t in marks):
        raise ValueError(f'{label}: missing/invalid marks')
    if marks != sorted(set(marks)):
        raise ValueError(f'{label}: marks not strictly increasing/unique')
    samples = payload['samples']
    if len(samples) != len(marks):
        raise ValueError(f'{label}: {len(samples)} samples but {len(marks)} marks')
    if [s.get('t') for s in samples] != marks:
        raise ValueError(f'{label}: sample timestamps do not match marks')
    for sample in samples:
        obj = sample.get('m', sample)
        if not isinstance(obj, dict): raise ValueError(f'{label}: invalid sample object')
        for name in METRICS:
            if not finite(obj.get(name)):
                raise ValueError(f'{label}: t={sample["t"]} missing or nonfinite {name}')
        if obj['mass'] < 0 or obj['vmax'] < 0:
            raise ValueError(f'{label}: nonphysical negative magnitude')
        if 'nan' in obj and obj['nan'] != 0:
            raise ValueError(f'{label}: t={sample["t"]} nan={obj["nan"]}')
    return samples


def compare(expected, actual, mode='permissive'):
    exp = validate(expected, 'reference')
    got = validate(actual, 'candidate')
    failures = []; results = []
    if expected['quality'] != actual['quality']:
        failures.append(f'quality mismatch: {expected["quality"]} vs {actual["quality"]}')
    if expected['marks'] != actual['marks']:
        failures.append(f'marks mismatch: {expected["marks"]} vs {actual["marks"]}')
    if len(exp) != len(got):
        return {'pass': False, 'failures': failures, 'results': results}
    for a, b in zip(exp, got):
        if a['t'] != b['t']: failures.append(f'sample time mismatch {a["t"]}/{b["t"]}'); continue
        ar = a.get('m',a); br = b.get('m',b)
        for k in METRICS:
            ref, cur = ar[k], br[k]
            tol = TOL['massRel'] * max(ref, 1e-9) if k == 'mass' else TOL[k]
            diff = abs(ref-cur)
            ok = diff <= tol
            results.append({'t': a['t'], 'metric': k, 'reference': ref,
                            'candidate': cur, 'abs_error': round(diff, 9),
                            'tolerance': round(tol, 9), 'pass': ok})
            if not ok: failures.append(f't={a["t"]} {k}: {cur} vs {ref} (tol {tol:.5g})')
    if mode == 'strict':
        # Extra hard constraints apply to every candidate even if reference fails.
        for s in got:
            o = s.get('m', s)
            if o['vmax'] > 8.01: failures.append(f't={s["t"]} vmax={o["vmax"]} exceeds 8.01 m/s')
    return {'pass': not failures, 'failures': failures, 'results': results,
            'sample_count': len(got), 'policy': 'v18 parity tolerances; not a calibration test'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('candidate', type=Path)
    ap.add_argument('--reference', type=Path, default=REFERENCE)
    ap.add_argument('--strict', action='store_true', help='also enforce max speed health limit')
    ap.add_argument('--output', type=Path, help='write JSON report')
    args = ap.parse_args()
    try:
        base = json.loads(args.reference.read_text('utf-8'))
        actual = json.loads(args.candidate.read_text('utf-8'))
        report = compare(base, actual, 'strict' if args.strict else 'permissive')
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as e:
        report = {'pass': False, 'failures': [str(e)], 'results': []}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(f"{'PASS' if report['pass'] else 'FAIL'} GPU numerical parity ({len(report['results'])} comparisons, {len(report['failures'])} failures)")
    for item in report['failures']: print(' - '+item)
    sys.exit(0 if report['pass'] else 1)

if __name__ == '__main__': main()
