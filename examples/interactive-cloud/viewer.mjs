import {defaultOrbit,rotateOrbit,zoomOrbit,panOrbit} from './cloud-view.mjs';
const $=id=>document.getElementById(id),canvas=$('canvas'),status=$('status');
const DEG=180/Math.PI,context=canvas.getContext('2d');
let scene,orbit,worker,active=null,pending=null,serial=0,drag=null,wheelTimer;
let stopped=false;
function sync(){
  if(!orbit)return;
  $('azimuth').value=orbit.yaw*DEG;$('azimuthValue').value=Math.round(orbit.yaw*DEG)+'°';
  $('elevation').value=orbit.pitch*DEG;$('elevationValue').value=Math.round(orbit.pitch*DEG)+'°';
  const scale=orbit.distance/Math.max(...scene.extent);$('distance').value=scale;$('distanceValue').value=scale.toFixed(2)+'×';
}
function fail(e){stopped=true;active=pending=null;status.dataset.ready='error';status.textContent='Viewer error: '+(e?.message||e);worker?.terminate();}
function request(interactive=false){
  if(!worker||stopped)return;
  sync();pending={id:++serial,options:{orbit:{...orbit,target:orbit.target.slice()},quality:$('quality').value,light:$('light').value,interactive}};
  status.dataset.ready='false';$('save').disabled=true;send();
}
function send(){
  if(active||!pending||stopped)return;
  active=pending;pending=null;status.textContent=active.options.interactive?'Rendering orbit preview…':'Refining the current view…';
  worker.postMessage({...active,scene});
}
function receive({data}){
  if(stopped||!active||data.id!==active.id)return;
  const completed=active;active=null;
  if(data.error){fail(data.error);return;}
  if(completed.options.quality===$('quality').value&&completed.options.light===$('light').value){
    canvas.width=data.width;canvas.height=data.height;
    context.putImageData(new ImageData(new Uint8ClampedArray(data.rgba),data.width,data.height),0,0);
    $('grid').textContent=data.cells.join(' × ');
    $('timing').textContent=Math.round(data.ms)+' ms';
    $('cache').textContent=data.reused?'Reused':'Computed';
    status.dataset.fieldBuilds=String(data.fieldBuilds);status.dataset.cacheBuilds=String(data.cacheBuilds);
    status.textContent='JS CPU · '+data.width+' × '+data.height+' · '+data.steps+' steps · '+data.visible.toLocaleString()+' visible pixels';
    if(!pending){status.dataset.ready='true';$('save').disabled=false;}
  }
  send();
}
try{
  const r=await fetch(new URL('../../contracts/cloud-hero.json',import.meta.url));if(!r.ok)throw Error('Cloud scene could not be loaded ('+r.status+')');
  scene=await r.json();orbit=defaultOrbit(scene);
  worker=new Worker(new URL('./cloud-worker.mjs',import.meta.url),{type:'module'});
  worker.onmessage=receive;worker.onerror=e=>fail(e.message||'Worker unavailable. Serve the example over HTTP.');
  for(const id of ['quality','light'])$(id).addEventListener('change',()=>request(false));
  for(const [id,key] of [['azimuth','yaw'],['elevation','pitch'],['distance','distance']]){
    $(id).addEventListener('input',()=>{orbit[key]=Number($(id).value)*(key==='distance'?Math.max(...scene.extent):1/DEG);request(true);});
    $(id).addEventListener('change',()=>request(false));
  }
  $('reset').onclick=()=>{orbit=defaultOrbit(scene);request(false);};
  $('save').onclick=()=>canvas.toBlob(blob=>{if(!blob)return;const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='vapor-cloud.png';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},'image/png');
  if(!document.fullscreenEnabled)$('fullscreen').disabled=true;
  $('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('viewport').requestFullscreen();}catch(e){status.textContent='Fullscreen unavailable: '+e.message;}};
  canvas.addEventListener('contextmenu',e=>e.preventDefault());
  canvas.addEventListener('pointerdown',e=>{
    if(drag||![0,2].includes(e.button))return;canvas.focus({preventScroll:true});canvas.setPointerCapture(e.pointerId);
    drag={id:e.pointerId,x:e.clientX,y:e.clientY,pan:e.button===2||e.shiftKey};canvas.classList.add('dragging');e.preventDefault();
  });
  canvas.addEventListener('pointermove',e=>{
    if(!drag||e.pointerId!==drag.id)return;
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
    orbit=drag.pan?panOrbit(orbit,dx,dy,scene.extent,canvas.clientHeight,scene.camera.fov):rotateOrbit(orbit,dx,dy);
    request(true);
  });
  function finish(e){if(!drag||drag.id!==e.pointerId)return;drag=null;canvas.classList.remove('dragging');request(false);}
  for(const ev of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(ev,finish);
  canvas.addEventListener('wheel',e=>{e.preventDefault();orbit=zoomOrbit(orbit,e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?canvas.clientHeight:1),scene.extent);request(true);clearTimeout(wheelTimer);wheelTimer=setTimeout(()=>request(false),180);},{passive:false});
  canvas.addEventListener('keydown',e=>{
    const moves={ArrowLeft:[-12,0],ArrowRight:[12,0],ArrowUp:[0,-12],ArrowDown:[0,12]};
    if(moves[e.key])orbit=rotateOrbit(orbit,...moves[e.key]);else if(['+','=','-'].includes(e.key))orbit=zoomOrbit(orbit,e.key==='-'?100:-100,scene.extent);else if(e.key==='Home')orbit=defaultOrbit(scene);else return;
    e.preventDefault();request(false);
  });
  request(false);
}catch(e){fail(e);}
window.addEventListener('pagehide',()=>{clearTimeout(wheelTimer);worker?.terminate();});
