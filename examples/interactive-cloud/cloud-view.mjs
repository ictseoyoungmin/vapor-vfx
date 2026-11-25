/** Canonical cloud, real camera rays and a bounded CPU optical cache. */
import {generateFidelityVolume,prepareFidelityVolume} from '../../bindings/web/fidelity.mjs';
const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
const finite=x=>typeof x==='number'&&Number.isFinite(x);
export function defaultOrbit(scene){
  const target=scene.camera.target.slice(), d=scene.camera.eye.map((v,i)=>v-target[i]), distance=Math.hypot(...d);
  return {yaw:Math.atan2(d[0],-d[2]),pitch:Math.asin(d[1]/distance),distance,target};
}
export function orbitCamera(orbit){
  const {yaw,pitch,distance,target}=orbit;
  if(![yaw,pitch,distance,...target].every(finite)||target.length!==3||distance<=0)throw Error('Invalid camera');
  const h=distance*Math.cos(pitch);
  return {target:target.slice(),eye:[target[0]+h*Math.sin(yaw),target[1]+distance*Math.sin(pitch),target[2]-h*Math.cos(yaw)]};
}
export function rotateOrbit(o,dx,dy){
  return {...o,yaw:((o.yaw-dx*.008+Math.PI)%(2*Math.PI)+2*Math.PI)%(2*Math.PI)-Math.PI,pitch:clamp(o.pitch+dy*.008,-1.39,1.39)};
}
export function zoomOrbit(o,delta,extent){
  const scale=Math.max(...extent);
  return {...o,distance:clamp(o.distance*Math.exp(clamp(delta,-1000,1000)*.001),scale*.60,scale*4)};
}
export function panOrbit(o,dx,dy,extent,height,fov){
  const k=2*o.distance*Math.tan(fov*Math.PI/360)/Math.max(1,height);
  const right=[-Math.cos(o.yaw),0,-Math.sin(o.yaw)],up=[-Math.sin(o.yaw)*Math.sin(o.pitch),Math.cos(o.pitch),Math.cos(o.yaw)*Math.sin(o.pitch)];
  return {...o,target:o.target.map((p,i)=>clamp(p-k*dx*right[i]+k*dy*up[i],-extent[i]*.5,extent[i]*1.5))};
}
export function createCloudSession(scene){
  let volume,prepared,qualityKey,lightKey,fieldBuilds=0,cacheBuilds=0;
  return {render({orbit,quality='preview',light='original',interactive=false}={}){
    if(!['preview','hero'].includes(quality)||!['original','side','back'].includes(light))throw Error('Unknown viewer setting');
    const profile=scene.profiles[quality],t=performance.now(),camera=orbitCamera(orbit);
    if(quality!==qualityKey){
      volume=generateFidelityVolume(scene.preset,{quality:scene.quality,cells:profile.cells,extent:scene.extent,settings:scene.settings,time:scene.time});
      qualityKey=quality;prepared=null;fieldBuilds++;
    }
    const reused=Boolean(prepared&&light===lightKey);
    if(!reused){
      const l=scene.lighting, direction=light==='side'?[-1,.35,.05]:light==='back'?[.22,.45,.86]:l.light.direction;
      prepared=prepareFidelityVolume({...volume,material:scene.material,...l,light:{direction,radiance:l.light.radiance}});
      lightKey=light;cacheBuilds++;
    }
    const width=interactive?240:profile.width,height=interactive?150:profile.height,steps=interactive?48:profile.steps;
    const frame=prepared.render({...scene.camera,...camera,width,height,steps});
    return {rgba:frame.rgba,width,height,steps,cells:volume.cells,fieldBuilds,cacheBuilds,reused,visible:frame.diagnostics.visiblePixels,ms:performance.now()-t};
  }};
}
