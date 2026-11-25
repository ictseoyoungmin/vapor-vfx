/** High-level game effect API. Explicit procedural path; fluid effects use the real SDK. */
import catalog from './effect-catalog.mjs';
import {createVaporSimulation} from './gpu.mjs';
import {normalizeConfig,normalizeExecution,Scene} from './gpu-protocol.mjs';
import {proceduralAtlas} from './procedural.mjs';
const clone=x=>JSON.parse(JSON.stringify(x));
const freeze=x=>{if(x&&typeof x==='object'){for(const v of Object.values(x))freeze(v);Object.freeze(x);}return x;};
export const effectCatalog=freeze(clone(catalog));
const finite=(x,label)=>{if(typeof x!=='number'||!Number.isFinite(x))throw new TypeError(`${label} must be finite`);return x;};
const vector=(v,label)=>{if(!Array.isArray(v)||v.length!==3)throw new TypeError(`${label} needs 3 components`);return v.map(x=>finite(x,label));};
export function getPreset(key,quality='medium'){
 const p=effectCatalog.presets.find(p=>p.key===key||p.id===key),q=Object.hasOwn(effectCatalog.quality,quality)?effectCatalog.quality[quality]:null;
 if(!p||!q)throw new RangeError('unknown effect or quality');
 const d=clone(p);d.config.cells=d.config.cells.map(n=>n*q.scale);d.config.cellSize/=q.scale;d.config.pressureIterations=q.pressureIterations;
 d.quality=quality;d.raySteps=q.steps;d.uploadHz=d.kind==='fluid'?q.uploadHz:q.proceduralUploadHz;return d;
}
/** Opt-in starting points for the 0.15 fine kinematic curl, not calibrated physics.
 * Keeps fine cell count bounded across the three standard coarse qualities.
 * Custom config overrides must be revalidated by createEffect(). */
const detailPresets=Object.freeze({cigarette_smoke:[.10,100],exhaled_aerosol:[.24,70],steam:[.18,45],smoke:[.22,35],flame:[.12,45]});
export function getDetailExecution(key,quality='medium',backend='gpu'){
 const p=getPreset(key,quality);if(p.kind!=='fluid'||!['gpu','hybrid'].includes(backend))throw new RangeError('fine detail requires a fluid effect and GPU/Hybrid');
 const [detailTurbulence,detailFrequency]=detailPresets[p.key];const detailScale=quality==='high'?2:4;
 const result={backend,detailScale,detailTurbulence,detailFrequency};normalizeExecution(normalizeConfig(p.config),result);return Object.freeze(result);
}
export function lodFor(distance,extent,quality='medium',procedural=false){
 const q=Object.hasOwn(effectCatalog.quality,quality)?effectCatalog.quality[quality]:null;if(!q||finite(distance,'distance')<0)throw new RangeError('invalid LOD');
 const radius=Math.hypot(...vector(extent,'extent'))*.5;if(radius<=0)throw new RangeError('invalid extent');
 const d=distance/radius,hz=procedural?q.proceduralUploadHz:q.uploadHz;return Object.freeze({visible:d<100,steps:d<4?q.steps:d<12?Math.max(16,Math.floor(q.steps*.65)):24,uploadHz:d<4?hz:d<12?Math.min(10,hz):2});
}
/** Render-only glowing ember descriptor, independent of physics; host maps to emissive mesh. */
export function emberVisual(time,lit=true,progress=0){finite(time,'time');finite(progress,'progress');if(time<0||time>1e7||progress<0||progress>1||typeof lit!=='boolean')throw new RangeError('invalid ember animation input');const heat=lit ? .72+.08*Math.sin(time*2.9)+.045*Math.sin(time*7.3):0;return {heat,colour:[1,.24+.22*heat,.035+.05*heat],intensity:heat*3.2,ashFraction:progress};}
export class Effect {
 constructor(def,simulation){this.definition=freeze(clone(def));this.simulation=simulation;this.config=simulation?.config??freeze(normalizeConfig(def.config));this.backend=simulation?.backendInfo.active??'procedural-cpu';this.renderCells=Object.freeze([...(simulation?.backendInfo.renderCells??this.config.cells)]);this.emitter=clone(def.emitter);this.settings=clone(def.procedural);this.time=0;this.playing=false;this.closed=false;this.paused=false;this.revision=0;this._snapshot=null;this._cached=null;this._cachedRevision=-1;}
 _check(){if(this.closed)throw new Error('effect disposed');}
 get extent(){return this.config.cells.map(n=>n*this.config.cellSize);}
 setPose(position,direction=this.emitter.direction){this._check();if(!this.simulation)throw new Error('move a procedural volume using its host transform');const e={...this.emitter,position:vector(position,'position'),direction:vector(direction,'direction')};const scene=new Scene(this.config);scene.setEmitter(0,e);if(this.playing)this.simulation.setEmitter(0,e);this.emitter=e;}
 play(){this._check();if(this.simulation){this.simulation.setEmitter(0,this.emitter);try{const p=this.definition.profile;this.simulation.setProfile(0,p?.points??null,{duration:p?.duration??2,startTime:this.time,repeat:false});}catch(e){this.simulation.removeEmitter(0);this.playing=false;throw e;}}this.playing=true;this.revision++;return this;}
 stop(){this._check();if(this.simulation)this.simulation.removeEmitter(0);this.playing=false;this.revision++;}
 reset(){this._check();this.stop();this.simulation?.reset();this.time=0;this.revision++;}
 setWind(wind){this._check();if(this.simulation)throw new Error('fluid wind is immutable; pass config.wind when creating the effect');const w=vector(wind,'wind');if(w.some((v,i)=>Math.abs(v)>100||Math.abs(v)/this.extent[i]>100))throw new RangeError('invalid procedural wind');this.settings.wind=w;this.revision++;}
 advance(seconds){this._check();finite(seconds,'seconds');if(seconds<0||seconds>10)throw new RangeError('advance requires 0..10 s');if(this.paused||seconds===0)return null;
   if(this.simulation){const r=this.simulation.advance(seconds);this.time=r.simulatedSeconds;if(r.steps)this.revision++;return r;}
   if(this.playing){const next=this.time+seconds;if(next>1e7)throw new RangeError('procedural time limit reached; reset before continuing');this.time=next;this.revision++;}return null;}
 async atlasRGBA8(){this._check();if(this._snapshot)throw new Error('snapshot already pending');if(!this.simulation){if(this._cachedRevision!==this.revision){this._cached=proceduralAtlas(this.config,this.definition.kind,this.settings,this.time);this._cachedRevision=this.revision;}return this._cached.slice();}
   const token=this.revision;const p=Promise.resolve(this.simulation.atlasRGBA8());this._snapshot=p;try{const a=await p;this._check();if(token!==this.revision)throw new Error('stale effect snapshot; retry');return a;}finally{if(this._snapshot===p)this._snapshot=null;}}
 dispose(){if(this.closed)return;this.closed=true;this._cached=null;this.simulation?.dispose();}
}
export async function createEffect(key,{quality='medium',execution={},config={},procedural={},emitter={},material={}}={}){
 const d=getPreset(key,quality);d.config={...d.config,...config};d.emitter={...d.emitter,...emitter};d.material=validateMaterial({...d.material,...material});
 const c=normalizeConfig(d.config);if(d.kind!=='fluid'){
   if((execution.backend&&!['cpu','auto'].includes(execution.backend))||(execution.detailScale??1)!==1||(execution.detailTurbulence??0)!==0)throw new Error('procedural volume currently uses CPU; GPU procedural generation is not implemented');
   for(const k of Object.keys(procedural))if(!Object.hasOwn(d.procedural,k))throw new TypeError('unknown procedural option '+k);d.procedural={...d.procedural,...procedural};const e=new Effect(d,null);e._cached=proceduralAtlas(c,d.kind,d.procedural,0);e._cachedRevision=0;return e;
 }
 if(Object.keys(procedural).length)throw new Error('procedural options are not valid for fluid');new Scene(c).setEmitter(0,d.emitter);
 const s=await createVaporSimulation(d.config,execution);try{return new Effect(d,s);}catch(e){s.dispose();throw e;}
}
function validateMaterial(m){const keys=['colour','extinction','anisotropy','albedo','emission','thermalFade','ambient'];if(Object.keys(m).some(k=>!keys.includes(k)))throw new TypeError('unknown material option');if(vector(m.colour,'colour').some(v=>v<0||v>1))throw new RangeError('invalid material colour');for(const [k,a,b] of [['extinction',0,1000],['anisotropy',-.9,.9],['albedo',0,1],['emission',0,10],['thermalFade',0,1],['ambient',0,1]])if(finite(m[k],k)<a||m[k]>b)throw new RangeError('invalid material '+k);return m;}
/** Recipe data is portable; execution/device is deliberately supplied separately. */
export function createEffectFromRecipe(recipe,execution={}){if(typeof recipe==='string')recipe=JSON.parse(recipe);if(!recipe||recipe.schema!=='vapor.effect-recipe/1'||Object.keys(recipe).some(k=>!['schema','preset','quality','config','emitter','procedural','material'].includes(k)))throw new TypeError('invalid effect recipe');return createEffect(recipe.preset,{quality:recipe.quality,config:recipe.config??{},emitter:recipe.emitter??{},procedural:recipe.procedural??{},material:recipe.material??{},execution});}
/** Count/estimated memory budget and shared host-owned GPU device/WASM module options.
 * No native GPU zero-copy. Call advance, then await snapshots before mutating again. */
export class EffectsWorld {
 constructor({maxEffects=8,maxBytes=128*1024*1024,execution={}}={}){if(!Number.isInteger(maxEffects)||maxEffects<1||maxEffects>64||!Number.isSafeInteger(maxBytes)||maxBytes<1)throw new RangeError('invalid world budget');this.maxEffects=maxEffects;this.maxBytes=maxBytes;this.execution={...execution};this.effects=new Map();this.pending=0;this.bytes=0;this.closed=false;}
 async createEffect(key,options={}){if(this.closed)throw new Error('world disposed');const d=getPreset(key,options.quality??'medium'),c=normalizeConfig({...d.config,...options.config}),exec={...this.execution,...options.execution};
   const o=d.kind==='fluid'?normalizeExecution(c,exec):null;const bytes=o?(o.backend==='cpu'?c.paddedCount*112+c.voxelCount*8:c.paddedCount*336+c.voxelCount*o.detailScale**3*68+8192):c.voxelCount*8;
   if(this.effects.size+this.pending>=this.maxEffects||this.bytes+bytes>this.maxBytes)throw new RangeError('effect world budget exceeded');this.pending++;this.bytes+=bytes;
   try{const e=await createEffect(key,{...options,execution:exec});if(this.closed){e.dispose();throw new Error('world disposed during creation');}this.effects.set(e,bytes);return e;}catch(e){this.bytes-=bytes;throw e;}finally{this.pending--;}}
 remove(effect){const bytes=this.effects.get(effect);if(bytes===undefined)return;this.effects.delete(effect);this.bytes-=bytes;effect.dispose();}
 advance(seconds){if(this.closed)throw new Error('world disposed');for(const e of this.effects.keys())e.advance(seconds);}
 dispose(){if(this.closed)return;this.closed=true;let error;for(const e of this.effects.keys()){try{this.remove(e);}catch(x){error??=x;}}if(error)throw error;}
}
