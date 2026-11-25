/** Actual CPU rendering of previous/new procedural cloud fields. */
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {getPreset} from '../bindings/web/effects.mjs';
import {proceduralAtlas} from '../bindings/web/procedural.mjs';
import {prepareVolume} from '../bindings/web/preview.mjs';
import {generateFidelityVolume,prepareFidelityVolume,getFidelityPreset,atlasToFidelityFields} from '../bindings/web/fidelity.mjs';
const dir=new URL('../reports/local/lab/fidelity/',import.meta.url);await mkdir(dir,{recursive:true});
const hash=x=>createHash('sha256').update(Buffer.isBuffer(x)?x:Buffer.from(x.buffer,x.byteOffset,x.byteLength)).digest('hex');
const rows=[];
const save=async(name,result,camera,details={})=>{await writeFile(new URL(name+'.rgba',dir),result.rgba);const row={name,width:camera.width,height:camera.height,...details,rgbaSha256:hash(result.rgba),diagnostics:result.diagnostics??null};rows.push(row);console.log(name,details.renderMs??'',result.diagnostics?.visiblePixels??'');return row;};
function timed(f){const t=performance.now(),v=f();return [v,performance.now()-t];}
const cloud=getPreset('cumulus_cloud','high'),cloudCells=[144,72,96],cloudExtent=[144,72,96],cloudCamera={width:800,height:500,eye:[110,15,-150],target:[72,32,48],fov:40,steps:112,exposure:.95};
const opt=getFidelityPreset('cumulus_cloud','high');
const [oldAtlas,oldGen]=timed(()=>proceduralAtlas({...cloud.config,cells:cloudCells,cellSize:1},cloud.kind,cloud.procedural,0));
const oldFields=atlasToFidelityFields(oldAtlas,cloudCells,1);
const [classic,classicPrep]=timed(()=>prepareVolume({atlas:oldAtlas,cells:cloudCells,extent:cloudExtent,densityCap:1,material:cloud.material,light:opt.lighting.light.direction,shadowSteps:32}));
const [classicPixels,classicMs]=timed(()=>classic.render({...cloudCamera,background:'sky'}));await save('cloud-legacy',{rgba:classicPixels},cloudCamera,{source:'0.12 density + 0.12 renderer',cells:cloudCells,generateMs:oldGen,prepareMs:classicPrep,renderMs:classicMs});
const shared={cells:cloudCells,extent:cloudExtent,densityCap:1,material:opt.material,...opt.lighting,lightScale:.8,shadowSteps:40};
const [optOld,oldPrep]=timed(()=>prepareFidelityVolume({...shared,fields:oldFields}));const [optOldImage,oldMs]=timed(()=>optOld.render(cloudCamera));await save('cloud-optics',optOldImage,cloudCamera,{source:'0.12 density + new optics',cells:cloudCells,generateMs:oldGen,prepareMs:oldPrep,renderMs:oldMs,fieldSha256:hash(oldFields.density)});
const [cloudVolume,cloudGen]=timed(()=>generateFidelityVolume('cumulus_cloud',{cells:cloudCells,extent:cloudExtent}));const [newCloud,newPrep]=timed(()=>prepareFidelityVolume({...shared,fields:cloudVolume.fields}));const [cloudImage,cloudMs]=timed(()=>newCloud.render(cloudCamera));await save('cloud-fidelity',cloudImage,cloudCamera,{source:'new density + new optics',cells:cloudCells,generateMs:cloudGen,prepareMs:newPrep,renderMs:cloudMs,fieldSha256:hash(cloudVolume.fields.density)});
const [full,fullMs]=timed(()=>newCloud.render({...cloudCamera,skipEmpty:false}));if(hash(full.rgba)!==hash(cloudImage.rgba)||hash(full.linear)!==hash(cloudImage.linear)||hash(full.alpha)!==hash(cloudImage.alpha))throw Error('empty skip mismatch');
const skipAudit={sameRGBA:true,sameFloatRadiance:true,sameAlpha:true,withSkipMs:cloudMs,withoutSkipMs:fullMs,withSkipSamples:cloudImage.diagnostics.samples,withoutSkipSamples:full.diagnostics.samples,skipped:cloudImage.diagnostics.skippedSamples};
const heroCam={...cloudCamera,width:960,height:600,steps:224};const [heroV,heroGen]=timed(()=>generateFidelityVolume('cumulus_cloud',{cells:[176,88,120],extent:cloudExtent}));const [heroP,heroPrep]=timed(()=>prepareFidelityVolume({...shared,...heroV}));const [hero,heroMs]=timed(()=>heroP.render(heroCam));await save('cloud-hero',hero,heroCam,{source:'new density and optics; larger grid',cells:heroV.cells,generateMs:heroGen,prepareMs:heroPrep,renderMs:heroMs,fieldSha256:hash(heroV.fields.density)});
await writeFile(new URL('render-report.json',dir),JSON.stringify({status:'PASS',evidence:'actual JS CPU rendering of previous/new procedural cloud fields; NOT Rust/GPU/engine',skipAudit,rows},null,2)+'\n');
