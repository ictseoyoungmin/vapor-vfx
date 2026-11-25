const $=id=>document.getElementById(id),canvas=$('canvas'),status=$('status'),ctx=canvas.getContext('2d');
let worker,active=0,serial=0,failed=false;
const controls=['quality','view','light','coverage','render','reset'];
function enable(on){for(const id of controls)$(id).disabled=!on;}
function fail(error){failed=true;active=0;status.dataset.ready='error';status.textContent='Viewer error: '+(error?.message||error);$('save').disabled=true;enable(false);worker?.terminate();}
function sync(){ $('coverageValue').value=Math.round(Number($('coverage').value)*100)+'%'; }
function render(){
  if(!worker||active||failed)return;
  sync();active=++serial;enable(false);$('save').disabled=true;status.dataset.ready='false';status.textContent='Rendering terrain and fog…';
  const quality=$('quality').value;
  worker.postMessage({id:active,options:{quality,view:$('view').value,lighting:$('light').value,coverage:Number($('coverage').value),width:quality==='high'?640:480,height:quality==='high'?400:300}});
}
try{
  worker=new Worker(new URL('./worker.mjs',import.meta.url),{type:'module'});
  worker.onmessage=({data})=>{
    if(failed||!active||data.id!==active)return;
    active=0;
    if(data.error){status.textContent='Render error: '+data.error;status.dataset.ready='error';enable(true);return;}
    canvas.width=data.width;canvas.height=data.height;
    ctx.putImageData(new ImageData(new Uint8ClampedArray(data.rgba),data.width,data.height),0,0);
    $('grid').textContent=data.cells.join(' × ');$('timing').textContent=Math.round(data.ms)+' ms';$('cache').textContent=data.reused?'Reused':'Computed';
    status.dataset.fieldBuilds=String(data.fieldBuilds);status.dataset.cacheBuilds=String(data.cacheBuilds);status.dataset.visiblePixels=String(data.visiblePixels);
    status.textContent='JS CPU · '+data.width+' × '+data.height+' · '+data.steps+' steps · '+data.visiblePixels.toLocaleString()+' visible fog pixels';
    status.dataset.ready='true';enable(true);$('save').disabled=false;
  };
  worker.onerror=e=>fail(e.message||'Worker unavailable. Serve this example over HTTP.');
  $('coverage').addEventListener('input',sync);
  $('render').onclick=render;
  $('reset').onclick=()=>{$('quality').value='medium';$('view').value='valley';$('light').value='side';$('coverage').value='.42';render();};
  $('save').onclick=()=>canvas.toBlob(blob=>{if(!blob)return;const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='vapor-terrain-fog.png';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},'image/png');
  render();
}catch(error){fail(error);}
window.addEventListener('pagehide',()=>worker?.terminate());
