import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {createInspector} from '../../examples/airborne-smoke/volume-render.mjs';
import {decodeFieldAsset,encodeFieldAsset} from '../../bindings/web/field-asset.mjs';
const root=new URL('../../',import.meta.url),base=new URL('assets/airborne-smoke/',root),scene=JSON.parse(await readFile(new URL('contracts/airborne-smoke.json',root))),manifest=JSON.parse(await readFile(new URL('manifest.json',base)));const hash=x=>createHash('sha256').update(x).digest('hex');
const out=new URL('reports/local/airborne-inspection/',root);await mkdir(out,{recursive:true});
for(const f of manifest.frames){const bytes=await readFile(new URL(f.file,base));if(hash(bytes)!==f.sha256)throw Error('Asset digest mismatch');const v=decodeFieldAsset(bytes);if(hash(encodeFieldAsset(v,v.time))!==f.sha256)throw Error('JS field roundtrip mismatch');}
const render=createInspector(scene,name=>readFile(new URL(name,base)));const rows=[];
for(const [name,options] of [['front',{frame:1}],['orbit',{frame:1,yaw:55,pitch:15}],['later',{frame:2,yaw:55,pitch:15}],['backlight',{frame:2,yaw:55,pitch:15,light:'back'}]]){
 const r=await render(options);if(!r.visiblePixels)throw Error('No visible volume');const {rgba,...meta}=r;const png=new URL(name+'.png',out);const child=spawnSync(process.env.PYTHON??'python',['-c','import sys; from PIL import Image; Image.frombytes("RGBA",(int(sys.argv[1]),int(sys.argv[2])),sys.stdin.buffer.read()).save(sys.argv[3])',String(r.width),String(r.height),decodeURIComponent(png.pathname)],{input:rgba});if(child.status!==0)throw Error(child.stderr?.toString()||'PNG failed');rows.push({name,sha256:hash(rgba),...meta});
}
if(rows[0].reused||!rows[1].reused||rows[2].reused||rows[3].reused||rows[0].sha256===rows[1].sha256)throw Error('Unexpected cache or orbit result');
const report={status:'PASS',scope:'Actual Node JS CPU optical renders, Python-exported Float32 VPF1; no Rust/GPU runtime',assetRoundtripFrames:manifest.frames.length,rows};await writeFile(new URL('validation.json',out),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
