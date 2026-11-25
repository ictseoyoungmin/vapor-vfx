import {loadVapor,Simulation,ConfigOptions,Fields} from '../bindings/web/vapor.mjs';
async function main(){const module=await loadVapor(new URL('file:///tmp/vapor.wasm'));const options:ConfigOptions={cells:[16,20,16],cellSize:.04};const sim:Simulation=module.createSimulation(options);sim.setEmitter(0,{position:[.32,.1,.32],direction:[0,1,0],enabled:true});sim.setCapsule(1,[0,0,0],[1,1,1],.1);sim.setProfile(0,[[0,1,0,1],[1,1,1,1]]);sim.advance(1/60);const a:Float32Array=sim.field('density');const b:Uint8Array=sim.atlasRGBA8();console.log(a,b,Fields);sim.dispose();}
void main;

import {VaporWorkerClient} from '../bindings/web/worker-client.mjs';
async function workerExample(){const c=new VaporWorkerClient();await c.init('vapor.wasm',{cells:[16,20,16]});await c.call('setEmitter',0,{speed:1});const m=await c.call('metrics');console.log(m.densityIntegral);await c.tick(.01);await c.dispose();}void workerExample;

import {createVaporSimulation,BackendInfo} from '../bindings/web/gpu.mjs';
async function gpuExample(){const sim=await createVaporSimulation({cells:[16,20,16]},{backend:'hybrid',detailScale:2});const info:BackendInfo=sim.backendInfo;const a:Uint8Array=await sim.atlasRGBA8();const f:Float32Array=await sim.field();console.log(info.active,a.length,f.length);sim.dispose();const w=new VaporWorkerClient();await w.init('vapor.wasm',{}, {backend:'gpu'});await w.dispose();}void gpuExample;
async function hardenedClientExample(){
 const client=new VaporWorkerClient(undefined,{maxPendingRequests:8,requestTimeoutMs:30000,shutdownTimeoutMs:500});
 await client.init(undefined,{}, {backend:'gpu',readbackTimeoutMs:15000});
 client.discardPendingTime();
 const localPending:number=client.diagnostics.pendingRequests;
 const remote=await client.call('diagnostics');
 const allocations:number|undefined=remote.readback?.allocations;
 console.log(localPending,allocations);await client.dispose();
}
void hardenedClientExample;
async function cpuPreviewExample(){const module=await loadVapor();const sim=module.createSimulation();const rgba:Uint8Array=sim.renderRGBA8({eye:[1,1,1],target:[.3,.3,.3],width:320,height:240});console.log(rgba.length);sim.dispose();}void cpuPreviewExample;
import {createEffect,getPreset,EffectsWorld,lodFor,createEffectFromRecipe} from '../bindings/web/effects.mjs';
async function effectTypes(){const d=getPreset('cumulus_cloud','low');const e=await createEffectFromRecipe({schema:'vapor.effect-recipe/1',preset:d.key});const a:Uint8Array=await e.atlasRGBA8();e.dispose();const world=new EffectsWorld({maxEffects:3});const f=await world.createEffect('steam',{execution:{backend:'gpu'}});f.setPose([0,1,0],[0,1,0]);world.dispose();lodFor(3,[1,1,1]);return a;}
import {GpuVolumeRenderer} from '../bindings/web/gpu-render.mjs';
async function directVolumeTypes(){const s=await createVaporSimulation({}, {backend:'gpu'});if('renderSource' in s){const r=await GpuVolumeRenderer.create(s);r.render({}, {eye:[0,1,-1],target:[.1,.1,.1],material:getPreset('smoke').material});r.dispose();}s.dispose();}
import {prepareVolume,ReprojectedPreview,PreviewFrame} from '../bindings/web/preview.mjs';
async function temporalExample(){const effect=await createEffect('cumulus_cloud');const volume=prepareVolume({atlas:await effect.atlasRGBA8(),cells:effect.renderCells,extent:effect.extent,densityCap:effect.config.densityCap,material:effect.definition.material});const history=new ReprojectedPreview(4);const frame:PreviewFrame=volume.renderFrame({eye:[30,30,-100],target:[0,10,0],volumeOrigin:[2,0,0]});const r=history.accumulate('static cloud',frame);const p:Uint8Array=r.rgba;const accepted:number=r.diagnostics.acceptedPixels;console.log(p,accepted);effect.dispose();}
import {GpuTemporalVolumeRenderer} from '../bindings/web/gpu-temporal.mjs';
async function gpuTemporalTypes(){const s=await createVaporSimulation({}, {backend:'gpu'});if('renderSource' in s){const r=await GpuTemporalVolumeRenderer.create(s);const v=r.render({}, {width:640,height:400,eye:[0,1,-1],target:[.1,.1,.1],material:getPreset('smoke').material,historyMode:'static'});const eligible:boolean=v.historyEligible;console.log(eligible);r.resetHistory();r.dispose();}s.dispose();}
async function sceneDepthExample(){const s=await createVaporSimulation({}, {backend:'gpu'});if('renderSource' in s){const r=await GpuVolumeRenderer.create(s,{enableSceneDepth:true});r.render({}, {sceneDepth:{},width:640,height:400,load:true,eye:[0,1,-1],target:[.1,.1,.1],material:getPreset('smoke').material});r.dispose();}s.dispose();const p=prepareVolume({fields:{density:new Float32Array(64),temperature:new Float32Array(64)},cells:[4,4,4],extent:[1,1,1],densityCap:1,material:getPreset('smoke').material});p.render({eye:[.5,.5,-1],target:[.5,.5,.5],width:1,height:1,scene:{depth:new Float32Array(1),colour:new Uint8Array([0,0,0,255])}});}
import {generateFidelityVolume,getFidelityPreset,prepareFidelityVolume,FidelityFrame} from '../bindings/web/fidelity.mjs';
function fidelityExample(){const v=generateFidelityVolume('cumulus_cloud',{cells:[24,16,24]});const s=getFidelityPreset('cumulus_cloud');const p=prepareFidelityVolume({...v,material:s.material,...s.lighting});const f:FidelityFrame=p.render({width:16,height:16,eye:[50,20,-90],target:[30,20,30]});console.log(f.alpha);}

import {GpuFidelityVolumeRenderer} from '../bindings/web/gpu-fidelity.mjs';
async function gpuFidelityTypes(){const s=await createVaporSimulation({}, {backend:'gpu',detailScale:2});if('renderSource' in s){const r=await GpuFidelityVolumeRenderer.create(s,{enableSceneDepth:true});const d=r.render({}, {eye:[0,1,-1],target:[.1,.1,.1],material:getPreset('smoke').material,lightScale:.5,lightSteps:24});const cache:boolean=d.cacheReused;console.log(cache);r.dispose();}s.dispose();}
import {NativeFidelityCPU} from '../bindings/web/native-fidelity.mjs';
async function nativeFidelityExample(){const cpu=new NativeFidelityCPU(await loadVapor());const volume=cpu.generate('cumulus_cloud',{cells:[16,16,16]});const frame=cpu.render(volume,{eye:[50,20,-90],target:[30,20,30],width:64,height:40});const pixels:Uint8Array=frame.rgba;console.log(pixels);}
void nativeFidelityExample;

import {GpuFieldVolume,packFloatField} from '../bindings/web/gpu-field.mjs';
async function nativeCloudGpuTypes(device:unknown){const native=new NativeFidelityCPU(await loadVapor());const cloud=native.generate('cumulus_cloud');const packet=packFloatField(cloud);const volume=await GpuFieldVolume.create(device,cloud);const renderer=await GpuFidelityVolumeRenderer.create(volume);renderer.render({}, {eye:[110,15,-150],target:[72,32,48],material:getFidelityPreset('cumulus_cloud').material});volume.setOrigin([1,0,0]);console.log(packet.packed.length,volume.bytes);renderer.dispose();volume.dispose();}
void nativeCloudGpuTypes;

import {encodeFieldAsset,decodeFieldAsset} from '../bindings/web/field-asset.mjs';
function bakedTypes(){const v=generateFidelityVolume('cumulus_cloud');const a=decodeFieldAsset(encodeFieldAsset(v,1));const n:number=a.time;return packFloatField(a).packed.length+n;}void bakedTypes;
import {FieldSequence,GpuSequencePlayer,openFieldSequence} from '../bindings/web/field-sequence.mjs';
async function sequenceTypes(device:unknown){const s:FieldSequence=await openFieldSequence('sequence.vpa');const player=new GpuSequencePlayer(device,s);const volume=await player.seek(s.startTime);volume.renderSource();player.dispose();s.dispose();}void sequenceTypes;
