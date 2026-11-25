// Render actual independent CPU fields. Same camera/optics for all variants.
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {prepareFidelityVolume} from '../bindings/web/fidelity.mjs';
import {spawnSync} from 'node:child_process';
const [input,output,...keys]=process.argv.slice(2);
const decode=b=>{const a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;};
for(const key of keys)for(const model of ['none','legacy','curl']){
 const stem=key+'-'+model,spec=JSON.parse(await readFile(join(input,stem+'.json'),'utf8')),density=decode(await readFile(join(input,stem+'.density.f32'))),temperature=decode(await readFile(join(input,stem+'.temperature.f32')));
 const smoke=key==='cigarette_smoke',material={...spec.material,extinction:smoke?135:14,ambient:.03,colour:smoke?[.72,.81,.96]:[.94,.96,1]},lighting={light:{direction:[-.82,.49,.19],radiance:smoke?[2.2,2.4,2.8]:[1.8,1.9,2.1]},sky:[.016,.024,.037],ground:[.008,.012,.018],multiScatter:.14};
 const camera=smoke?{width:360,height:480,eye:[.14,.20,-.48],target:[.12,.20,.12],fov:39,steps:192,exposure:1.15,background:'dark'}:{width:480,height:320,eye:[.48,.44,-.84],target:[.47,.40,.4],fov:40,steps:160,exposure:1.05,background:'dark'};
 const p=prepareFidelityVolume({...spec,fields:{density,temperature},material,...lighting,lightScale:.5,shadowSteps:24}),img=p.render(camera);
 const result=spawnSync(process.env.PYTHON??'python',['-c','from PIL import Image; import sys; Image.frombytes("RGBA",(int(sys.argv[1]),int(sys.argv[2])),sys.stdin.buffer.read()).save(sys.argv[3])',String(camera.width),String(camera.height),join(output,stem+'.png')],{input:img.rgba});if(result.status!==0)throw Error(String(result.stderr));console.log('Rendered',stem);
}
