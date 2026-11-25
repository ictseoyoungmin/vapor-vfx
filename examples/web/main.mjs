import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {createVaporVolume} from '../../adapters/three/volume.mjs';
import {VaporWorkerClient} from '../../bindings/web/worker-client.mjs';
const $=id=>document.getElementById(id),info=$('stats'),error=$('error');
const renderer=new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setSize(innerWidth,innerHeight);
document.body.append(renderer.domElement);
const scene=new THREE.Scene();scene.background=new THREE.Color(0x10141c);
const camera=new THREE.PerspectiveCamera(43,innerWidth/innerHeight,.01,20);
camera.position.set(1.1,.75,1.3);
const controls=new OrbitControls(camera,renderer.domElement);
controls.target.set(.3,.38,.3);controls.update();
const grid=new THREE.GridHelper(2,20,0x324154,0x1b2838);grid.position.set(.3,0,.3);scene.add(grid);
const query=new URLSearchParams(location.search),backend=query.get('backend')??'cpu';
const detailScale=Number(query.get('scale')??1);
$('backend').value=backend;$('scale').value=String(detailScale);
$('apply').onclick=()=>{location.search=new URLSearchParams({backend:$('backend').value,scale:$('scale').value}).toString();};
const client=new VaporWorkerClient();
let volume,paused=false,last=performance.now(),lastInfo=0,closed=false,ready=false;
let pendingElapsed=0,appDiscarded=0,metricsPending=false,pendingDensity=null,densityPending=false;
let uploadHz=20,backendInfo;
const emitter=densityRate=>({position:[.32,.10,.32],direction:[.12,1,.08],radius:.05,densityRate});
function discardTime(){appDiscarded+=pendingElapsed;pendingElapsed=0;client.discardPendingTime();last=performance.now();}
function showError(e){if(closed)return;error.textContent=e.message;paused=true;$('pause').textContent='재개';discardTime();}
try {
    const config=await client.init(new URL('../../bindings/web/vapor.wasm',location.href),
        {cells:[16,20,16],cellSize:.04,pressureIterations:24},
        {backend,detailScale,allowCpuFallback:true,readbackTimeoutMs:15000});
    backendInfo=config.backendInfo;
    const fine=backendInfo.renderCells;
    volume=createVaporVolume(THREE,{...config,cells:fine,nx:fine[0],ny:fine[1],nz:fine[2],cellSize:config.cellSize/backendInfo.detailScale});
    scene.add(volume.mesh);await client.call('setEmitter',0,emitter(8));
    ready=true;last=performance.now();
    info.textContent=`실행 모드: ${backendInfo.active}, 배율 ${backendInfo.detailScale}`;
} catch(e) {
    error.textContent=`${e.message}\nCPU/Hybrid는 실제 Rust WASM 빌드가 필요합니다. GPU는 WebGPU 보안 컨텍스트가 필요합니다. 실패를 다른 솔버의 성공으로 표시하지 않습니다.`;
    info.textContent='로드 실패';
}
$('uploadHz').onchange=e=>{uploadHz=Number(e.target.value);};
$('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'재개':'일시정지';discardTime();};
$('reset').onclick=()=>{discardTime();if(ready)client.call('reset').catch(showError);};
$('density').oninput=e=>{pendingDensity=Number(e.target.value);};
// Latest-value coalescing: dragging the slider never fills the worker RPC queue.
async function updateEmitter(){
    if(!ready||closed||densityPending||pendingDensity===null)return;
    const value=pendingDensity;pendingDensity=null;densityPending=true;
    try{await client.call('setEmitter',0,emitter(value));}catch(e){showError(e);}finally{densityPending=false;}
}
async function updateMetrics(now){
    if(metricsPending||now-lastInfo<1000||closed)return;
    metricsPending=true;lastInfo=now;
    try {
        const [m,d]=await Promise.all([client.call('metrics'),client.call('diagnostics')]);
        if(closed)return;
        const reads=d.readback;
        info.textContent=`mode ${backendInfo.active} / scale ${backendInfo.detailScale}\n`+
            `time ${m.time.toFixed(2)} s\ndensity integral ${m.densityIntegral.toExponential(3)}\n`+
            `max speed ${m.maxSpeed.toFixed(2)} m/s\nnon-finite ${m.nonFinite}\n`+
            `solver dropped ${m.droppedSeconds.toFixed(3)} s\n`+
            `pause/reset discarded ${(appDiscarded+client.diagnostics.clientDiscardedSeconds).toFixed(3)} s\n`+
            `snapshot target ${uploadHz} Hz (not measured FPS)\n`+
            (reads?`staging alloc/reuse ${reads.allocations}/${reads.reuses}\nstaging ${(reads.allocatedBytes/1048576).toFixed(2)} MiB`:'CPU WASM path');
    }catch(e){showError(e);}finally{metricsPending=false;}
}
window.addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
document.addEventListener('visibilitychange',discardTime);
async function frame(now){
    if(closed)return;
    requestAnimationFrame(frame);
    const elapsed=Math.max(0,(now-last)/1000);last=now;
    controls.update();renderer.render(scene,camera);void updateEmitter();
    if(!ready||paused||document.hidden)return;
    // Fixed-step physics advances by accumulated elapsed time; transfer rate is independent.
    // A slow solver still reports its own max-substep time drops; no performance promise.
    pendingElapsed+=elapsed;
    if(pendingElapsed<1/uploadHz)return;
    const seconds=Math.min(pendingElapsed,3600);
    appDiscarded+=Math.max(0,pendingElapsed-seconds);pendingElapsed=0;
    try {
        const result=await client.tick(seconds);
        if(result&&!closed&&!paused&&!document.hidden){volume.update(result.atlas);void updateMetrics(now);}
    }catch(e){showError(e);}
}
requestAnimationFrame(frame);
window.addEventListener('pagehide',()=>{
    closed=true;void client.dispose();volume?.dispose();controls.dispose();renderer.dispose();
    grid.geometry.dispose();grid.material.dispose();
});
