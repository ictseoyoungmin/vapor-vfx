import {readFile} from 'node:fs/promises';
import {loadVapor} from '../../bindings/web/vapor.mjs';
const wasm=await readFile(new URL('../../bindings/web/vapor.wasm',import.meta.url));
const module=await loadVapor(wasm);
const sim=module.createSimulation({cells:[12,16,12],cellSize:.05});
try{sim.setEmitter(0,{position:[.3,.1,.3]});sim.step(60);const m=sim.metrics();if(m.nonFinite!==0||m.densityIntegral<=0||m.ticks!==60||m.maxDensity>sim.config.densityCap)throw Error('Real Rust WASM smoke failed');console.log(JSON.stringify({profile:'game-mac-v1',backend:'rust-wasm',metrics:sim.metrics()},null,2));}
finally{sim.dispose();}
