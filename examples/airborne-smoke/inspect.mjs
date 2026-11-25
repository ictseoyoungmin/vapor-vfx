const $=id=>document.getElementById(id),canvas=$('canvas'),status=$('status'),button=$('render');let worker=null,request=0,busy=false;
function labels(){ $('yawValue').value=$('yaw').value+'°';$('pitchValue').value=$('pitch').value+'°';$('zoomValue').value=Number($('zoom').value).toFixed(2)+'×';}
for(const name of ['yaw','pitch','zoom'])$(name).addEventListener('input',labels);labels();
function unlock(){busy=false;button.disabled=false;button.textContent='볼륨 렌더링';}
function fail(message){status.textContent=String(message);unlock();}
try{worker=new Worker(new URL('./inspect-worker.mjs',import.meta.url),{type:'module'});worker.onerror=e=>{worker?.terminate();worker=null;fail(e.message||'Worker를 시작할 수 없습니다. 프로젝트 루트에서 로컬 HTTP 서버를 실행하세요.');button.disabled=true;};worker.onmessage=({data})=>{if(data.id!==request)return;if(data.error){fail(data.error);return;}canvas.width=data.width;canvas.height=data.height;canvas.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(data.rgba),data.width,data.height),0,0);$('fieldStat').textContent=`${data.cells.join(' × ')} · ${data.time.toFixed(2)} s`;$('renderStat').textContent=`${Math.round(data.ms)} ms · ${data.reused?'광학 캐시 재사용':'광학 캐시 생성'}`;status.textContent=`렌더링 완료 · 가시 픽셀 ${data.visiblePixels.toLocaleString()}`;unlock();};
 function render(){if(!worker||busy)return;busy=true;button.disabled=true;button.textContent='렌더링 중…';status.textContent='실제 밀도장을 읽고 볼륨을 적분하고 있습니다.';try{worker.postMessage({id:++request,options:{frame:Number($('frame').value),yaw:Number($('yaw').value),pitch:Number($('pitch').value),zoom:Number($('zoom').value),light:$('light').value,quality:$('quality').value}});}catch(e){fail(e.message);}}
 button.onclick=render;button.disabled=false;render();
}catch(e){fail(e.message);button.disabled=true;}
window.addEventListener('pagehide',()=>worker?.terminate());
