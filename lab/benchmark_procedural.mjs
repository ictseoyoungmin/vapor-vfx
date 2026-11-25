/** Compare actual JS density generation, requiring bitwise equality. Not Rust/GPU FPS. */
import {readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import os from 'node:os';
import {getPreset} from '../bindings/web/effects.mjs';
import {proceduralAtlas as current} from '../bindings/web/procedural.mjs';
const hash=a=>createHash('sha256').update(a).digest('hex');
const median=a=>[...a].sort((x,y)=>x-y)[Math.floor(a.length/2)];
const root=process.argv[2];if(!root)throw new Error('Usage: node lab/benchmark_procedural.mjs BASELINE_SDK_ROOT [report.json]');
const baselinePath=resolve(root,'bindings/web/procedural.mjs');
const {proceduralAtlas:baseline}=await import(pathToFileURL(baselinePath));
const rows=[],fixtures=[];
for(const key of ['cumulus_cloud','ground_fog','dust'])for(const quality of ['low','medium','high']){
 const d=getPreset(key,quality),args=[d.config,d.kind,d.procedural];
 for(const time of [0,.25,2.5,513.75,9999999]){
  const a=baseline(...args,time),b=current(...args,time);
  if(Buffer.compare(a,b)!==0)throw new Error(`atlas mismatch: ${key}/${quality}/${time}`);
  fixtures.push({key,quality,time,sha256:hash(a)});
 }
 const prev=[],next=[];let checksum='';
 for(let i=0;i<7;i++){
  const time=.25+i*.125;const measure=(fn,arr)=>{const start=performance.now(),a=fn(...args,time);arr.push(performance.now()-start);return a;};
  let a,b;if(i%2){b=measure(current,next);a=measure(baseline,prev);}else{a=measure(baseline,prev);b=measure(current,next);}
  if(Buffer.compare(a,b)!==0)throw new Error(`benchmark atlas mismatch: ${key}/${quality}/${time}`);checksum=hash(a);
 }
 const before=median(prev),after=median(next);
 rows.push({key,quality,cells:d.config.cells,baselineMs:before,currentMs:after,speedup:before/after,baselineSamplesMs:prev,currentSamplesMs:next,lastAtlasSha256:checksum});
 console.log(key,quality,before.toFixed(2),after.toFixed(2));
}
const report={schema:'vapor.procedural-performance/1',evidence:'actual Node JS CPU procedural generation, full byte parity, not Rust fluid or game FPS',node:process.version,platform:process.platform,arch:process.arch,cpu:os.cpus()[0]?.model,baselineSourceSha256:hash(await readFile(baselinePath)),currentSourceSha256:hash(await readFile(new URL('../bindings/web/procedural.mjs',import.meta.url))),fixtureCount:fixtures.length,rows,fixtures};
if(process.argv[3])await writeFile(process.argv[3],JSON.stringify(report,null,2)+'\n');else console.log(JSON.stringify(report,null,2));
