import {createInspector} from './volume-render.mjs';
const get=async url=>{const r=await fetch(url);if(!r.ok)throw new Error(`Asset load failed (${r.status}): ${url.pathname}`);return r;};
let renderer=null,busy=false;
self.onmessage=async ({data})=>{if(busy){self.postMessage({id:data.id,error:'Renderer busy'});return;}busy=true;
 try{if(!renderer){const scene=await (await get(new URL('../../contracts/airborne-smoke.json',import.meta.url))).json();renderer=createInspector(scene,async name=>{if(!/^smoke-\d{4}\.vpf$/.test(name))throw Error('Unexpected field filename');return (await get(new URL(`../../assets/airborne-smoke/${name}`,import.meta.url))).arrayBuffer();});}const result=await renderer(data.options);self.postMessage({id:data.id,...result},[result.rgba.buffer]);}
 catch(e){self.postMessage({id:data.id,error:e instanceof Error?e.message:String(e)});}finally{busy=false;}
};
