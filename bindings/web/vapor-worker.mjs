import {createVaporSimulation} from './gpu.mjs';
let sim=null;
let queue=Promise.resolve();
async function dispatch(data){
 const {id,method,args=[]}=data;
 try{
  let value;
  if(method==='init'){
   if(sim)throw new Error('worker already initialized');
   sim=await createVaporSimulation(args[1],{backend:'cpu',...args[2],wasmURL:args[0]});value={...sim.config,backendInfo:sim.backendInfo};
  }else{
   if(!sim)throw new Error('worker is not initialized');
   if(method==='diagnostics'){value={backendInfo:sim.backendInfo,readback:sim.readbackStats??null};self.postMessage({id,value});return;}
   if(method==='tick'){const timing=sim.advance(args[0]);const atlas=await sim.atlasRGBA8();value={timing,atlas};self.postMessage({id,value},[atlas.buffer]);return;}
   const allowed=new Set(['step','advance','setEmitter','removeEmitter','setSphere','setCapsule','setBox','removeObstacle','setProfile','reset','metrics','dispose']);
   if(!allowed.has(method))throw new Error('unknown worker operation');value=await sim[method](...args);
   if(method==='dispose')sim=null;
  }
  self.postMessage({id,value});
 }catch(error){self.postMessage({id,error:{message:String(error.message??error),code:error.code??null}});}
}
self.onmessage=({data})=>{queue=queue.then(()=>dispatch(data),()=>dispatch(data));};
