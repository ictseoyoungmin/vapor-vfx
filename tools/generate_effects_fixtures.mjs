// Cross-language CPU procedural checks: execute actual JS density generator, compare all sampled
// red-channel bytes and global density sum. Native runtime runs separately, never replaced by JS.
import {writeFile,readFile} from 'node:fs/promises';
import {createEffect} from '../bindings/web/effects.mjs';
const rows=[];
for(const key of ['cumulus_cloud','ground_fog','dust']){
  const effect=await createEffect(key,{quality:'low'});effect.play();
  for(const time of [0,2]){
    if(time)effect.advance(time);
    const a=await effect.atlasRGBA8();let sum=0;for(let i=0;i<a.length;i+=4)sum+=a[i];
    const n=a.length/4;const samples=Array.from({length:128},(_,i)=>{const j=Math.floor(i*(n-1)/127);return [j,a[j*4]];});
    rows.push({key,time,bytes:a.length,sum,samples});
  }effect.dispose();
}
const file=new URL('../fixtures/effects-atlas-golden.json',import.meta.url),data=JSON.stringify({schema:'vapor.procedural-golden/1',source:'actual Node CPU procedural generator; tolerance required for Rust f32 config',rows},null,2)+'\n';
if(process.argv.includes('--check')){if(data!==await readFile(file,'utf8'))throw Error('procedural fixture changed');console.log('PASS 6 actual Node atlas fixtures');}else await writeFile(file,data);
