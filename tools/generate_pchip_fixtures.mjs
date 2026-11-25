// Original v18 JS (not a reimplementation) is the golden oracle.
// Usage: node tools/generate_pchip_fixtures.mjs [--check]
import { Curve, defaultProfile } from '../history/legacy/v18/src/breath.js';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const out = path.join(root,'fixtures','pchip_v18.tsv');
const xs = [0,0.003,0.01,0.05,0.08,0.1,0.2,0.37,0.5,0.72,0.97,1];
const curves = {
  smooth: [[0,0],[0.1,0.05],[0.4,0.7],[0.7,0.95],[1,1]],
  plateau: [[0,0],[0.2,1],[0.5,1],[0.8,1],[1,0]],
  turning: [[0,0],[0.15,1],[0.4,-0.5],[0.7,0.9],[1,0]],
  sparse: [[0,2.5],[1,0.001]],
};
for (const [name, style] of Object.entries({cloud: {dur: 1.3}, stream: {dur: 3.8}, ring: {dur: 3.6, pulses:[[0.15,0.13],[1.55,0.13]]}})) {
 const p = defaultProfile(style);
 for (const key of ['speed','amount','density']) curves[`${name}_${key}`] = p.curves[key].pts.map(({x,y})=>[x,y]);
}
let body = '# id\txs_csv\tys_csv\teval_x\texpected_y; sampled from legacy/v18/src/breath.js\n';
for (const [key, points] of Object.entries(curves)) {
 const curve = new Curve(points.map(([x,y])=>({x,y})));
 const a=curve.pts.map(p=>p.x.toPrecision(17)).join(',');
 const b=curve.pts.map(p=>p.y.toPrecision(17)).join(',');
 for (const x of xs) body += `${key}\t${a}\t${b}\t${x.toPrecision(17)}\t${curve.eval(x).toPrecision(17)}\n`;
}
if (process.argv.includes('--check')) {
 const prev=readFileSync(out,'utf8');
 if(prev!==body) {console.error('FAIL PCHIP golden drift');process.exit(1)}
 console.log('PASS JS PCHIP golden current',body.trim().split('\n').length-1,'vectors');
} else {
 writeFileSync(out,body);
 console.log('FROZEN PCHIP vectors',out);
}
