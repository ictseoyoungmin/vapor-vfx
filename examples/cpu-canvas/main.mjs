import {loadVapor} from '../../bindings/web/vapor.mjs';
const $=id=>document.getElementById(id),query=new URLSearchParams(location.search);
const capturing=query.get('capture')==='1';let module,sim,paused=false,last=performance.now(),lastRender=0;
const canvas=$('view'),ctx=canvas.getContext('2d');
const titles={vent:'Steam vent',wind:'Crosswind',pulse:'Pulsed emitter'};
window.__VAPOR_CAPTURE__={status:'LOADING',backend:'rust-cpu-wasm'};
const scene=query.get('scene')??'vent';if(Object.hasOwn(titles,scene))$('scenario').value=scene;
function fail(error){
  paused=true;$('status').textContent='RUNTIME NOT READY';$('error').textContent=String(error?.stack??error)+'\n\n먼저 실행: python tools/build.py --web';
  window.__VAPOR_CAPTURE__={status:'FAIL',backend:'rust-cpu-wasm',error:String(error)};
}
function reset(){
  sim?.dispose();const name=$('scenario').value;
  sim=module.createSimulation({cells:[12,20,12],cellSize:.05,pressureIterations:48,maxVelocity:2,
    wind:name==='wind'?[.7,0,0]:[0,0,0],drag:name==='wind'?.7:.08,vorticity:.15});
  sim.setEmitter(0,{position:[.3,.08,.3],direction:[.12,1,.04],radius:.075,length:.1,speed:.65,densityRate:14,temperature:1.5});
  if(name==='pulse')sim.setProfile(0,[[0,.3,0,1],[.15,1,1,1],[.5,.7,.5,1],[.8,.2,0,1],[1,.2,0,1]],{duration:1.6,repeat:true});
  $('title').textContent=titles[name];$('error').textContent='';last=performance.now();lastRender=0;
}
function draw(){
  const begin=performance.now();
  const raw=sim.renderRGBA8({width:400,height:300,steps:80,eye:[1.05,.7,1.15],target:[.3,.43,.3],extinction:22,colour:[.78,.87,1]});
  const renderMs=performance.now()-begin,pixels=new Uint8ClampedArray(raw.length);let nonzero=0;
  // Convert linear-premultiplied output to straight sRGB for Canvas ImageData.
  for(let i=0;i<raw.length;i+=4){const alpha=raw[i+3]/255;nonzero+=Number(alpha>0);
    for(let c=0;c<3;c++){let linear=alpha>0?Math.min(1,raw[i+c]/255/alpha):0;pixels[i+c]=Math.round(255*(linear<=.0031308?12.92*linear:1.055*linear**(1/2.4)-.055));}
    pixels[i+3]=raw[i+3];
  }
  ctx.putImageData(new ImageData(pixels,400,300),0,0);
  const m=sim.metrics();$('time').textContent=`${m.time.toFixed(2)} s / ${m.ticks} ticks`;
  $('mass').textContent=m.densityIntegral.toExponential(4);$('render-ms').textContent=`${renderMs.toFixed(1)} ms`;
  $('health').textContent=`${m.nonFinite} / ${m.clampedVelocities}`;
  $('stamp').textContent=`${$('scenario').value.toUpperCase()} · 12 × 20 × 12 · STEP ${m.ticks} · OWNED RGBA SNAPSHOT`;
  $('status').textContent=paused?'CPU PREVIEW · PAUSED':'CPU PREVIEW · LIVE';
  return {metrics:m,renderMs,visiblePixels:nonzero};
}
async function capture(){
  const count=Number(query.get('steps')??180);
  if(!Number.isInteger(count)||count<24||count>600)throw new Error('capture steps must be 24..600');
  for(let remaining=count;remaining>0;remaining-=4){sim.step(Math.min(remaining,4));await new Promise(r=>setTimeout(r,0));}
  paused=true;const result=draw();
  if(result.metrics.nonFinite!==0||result.metrics.densityIntegral<=0||result.visiblePixels===0)throw new Error('Actual CPU preview is empty/invalid');
  window.__VAPOR_CAPTURE__={status:'PASS',backend:'rust-cpu-wasm',scenario:$('scenario').value,...result};
}
function frame(now){
  try{if(!paused){sim.advance(Math.min(.15,(now-last)/1000));if(now-lastRender>=125){draw();lastRender=performance.now();}}last=performance.now();}
  catch(error){fail(error);return;}
  requestAnimationFrame(frame);
}
try{
  if(!ctx)throw new Error('Canvas 2D unavailable');module=await loadVapor();reset();
  $('apply').disabled=false;$('pause').disabled=false;
  $('apply').onclick=()=>{try{reset();paused=false;draw();}catch(e){fail(e);}};
  $('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'재개':'일시정지';$('status').textContent=paused?'CPU PREVIEW · PAUSED':'CPU PREVIEW · LIVE';last=performance.now();};
  if(capturing)await capture();else requestAnimationFrame(frame);
}catch(e){fail(e);}
addEventListener('pagehide',()=>sim?.dispose(),{once:true});
