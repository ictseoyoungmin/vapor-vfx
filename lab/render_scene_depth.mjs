/** Node execution of actual SDK fog and the same opaque scene as the browser demo. */
import {createEffect} from '../bindings/web/effects.mjs';
import {prepareVolume} from '../bindings/web/preview.mjs';
import {demoCamera,renderOpaqueScene} from '../examples/scene-depth/scene.mjs';
import {writeFile,mkdir} from 'node:fs/promises';import {createHash} from 'node:crypto';
const hash=a=>createHash('sha256').update(a).digest('hex'),out=new URL('../reports/local/lab/effects/',import.meta.url);await mkdir(out,{recursive:true});
const e=await createEffect('ground_fog',{quality:'medium'});
try{const atlas=await e.atlasRGBA8(),scene=renderOpaqueScene(demoCamera),start=performance.now(),p=prepareVolume({atlas,cells:[...e.renderCells],extent:e.extent,densityCap:e.config.densityCap,material:e.definition.material});
 const before=p.render({...demoCamera,scene:{colour:scene.colour,depth:new Float32Array(scene.depth.length)}}),after=p.render({...demoCamera,scene});let changes=0,foreground=0,legacyLeaks=0,correctedLeaks=0;const {width,height}=demoCamera;
 for(let i=0;i<width*height;i++){const j=i*4,delta=(a,b)=>Math.max(...[0,1,2].map(k=>Math.abs(a[j+k]-b[j+k])));if(delta(before,after)>=2)changes++;if(scene.objectMask[i]&&scene.depth[i]<28){foreground++;legacyLeaks+=delta(before,scene.colour)>=2;correctedLeaks+=delta(after,scene.colour)>=2;}}
 if(!changes||!foreground||!legacyLeaks||correctedLeaks!==0)throw Error('scene comparison failed '+JSON.stringify({changes,foreground,legacyLeaks,correctedLeaks}));
 const frames=[scene.colour,before,after];for(let i=0;i<frames.length;i++)await writeFile(new URL(`scene-depth-${i}.rgba`,out),frames[i]);
 // Independently known low density: below half an 8-bit code at cap 2.
 const cells=[4,4,4],fields={density:new Float32Array(64).fill(.002),temperature:new Float32Array(64)},extent=[1,1,1],material={...e.definition.material,colour:[1,1,1],extinction:40,anisotropy:0,albedo:1,ambient:1,emission:0,thermalFade:0},camera={eye:[.5,.5,-1],target:[.5,.5,.5],width:1,height:1,steps:64,scene:{colour:new Uint8Array([0,0,0,255]),depth:new Float32Array(1)}};const empty=new Uint8Array(256);for(let i=3;i<256;i+=4)empty[i]=255;const common={cells,extent,densityCap:2,material};
 const raw=prepareVolume({...common,fields}).render(camera),quant=prepareVolume({...common,atlas:empty}).render(camera);
 const report={status:'PASS',sdkVersion:'0.12.0',evidence:'Actual JS CPU procedural ground fog and reference software ray march with an analytic opaque test scene, not a game-engine or Rust/GPU runtime capture',preset:e.definition.key,cells:e.renderCells,width,height,atlasSha256:hash(atlas),camera:demoCamera,changedPixels:changes,foregroundObjectPixels:foreground,legacyForegroundLeaks:legacyLeaks,depthForegroundLeaks:correctedLeaks,rawFrameHashes:frames.map(hash),thinUniformAnalytic:{density:fields.density[0],densityCap:2,expectedQuantizedCode:0,extinction:40,segmentMetres:1,float32RGBA:[...raw],rgba8RGBA:[...quant]},wallMs:performance.now()-start};await writeFile(new URL('scene-depth-0.12.json',out),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{e.dispose();}
