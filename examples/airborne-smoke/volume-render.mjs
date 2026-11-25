/** Actual Lab optics on a portable field. No game-runtime fallback or blast solver. */
import {decodeFieldAsset} from '../../bindings/web/field-asset.mjs';
import {prepareFidelityVolume} from '../../bindings/web/fidelity.mjs';
const resolutions=Object.freeze({preview:[480,270,80,.5],high:[640,360,144,.625]});
const dirs=Object.freeze({side:[1,.18,.04],back:[-.28,.65,1]});
export function createInspector(scene,load){
 let index=-1,field=null,prepared=null,key='',cacheBuilds=0;
 return async function render({frame=1,yaw=0,pitch=0,zoom=1,light='original',quality='preview'}={}){
  if(!Number.isInteger(frame)||!scene.frames[frame]||!Number.isFinite(yaw)||Math.abs(yaw)>180||!Number.isFinite(pitch)||pitch< -45||pitch>65||!Number.isFinite(zoom)||zoom<.75||zoom>1.75||!['original','side','back'].includes(light)||!Object.hasOwn(resolutions,quality))throw new RangeError('Invalid inspector controls');
  const start=performance.now();let candidate=field;if(frame!==index){candidate=decodeFieldAsset(await load(scene.frames[frame].file));if(candidate.cells.some((x,i)=>x!==scene.cells[i])||candidate.extent.some((x,i)=>x!==scene.extent[i])||candidate.time!==scene.frames[frame].time||candidate.densityCap!==scene.densityCap)throw new Error('Field does not match the scene contract');}
  const [width,height,steps,lightScale]=resolutions[quality];const nextKey=`${frame}:${light}:${quality}`;const reused=nextKey===key&&!!prepared;
  if(!reused){const lighting={...scene.lighting,light:{...scene.lighting.light,direction:light==='original'?scene.lighting.light.direction:dirs[light]},lightScale};const next=prepareFidelityVolume({...candidate,material:scene.material,...lighting});prepared=next;field=candidate;index=frame;key=nextKey;cacheBuilds++;}
  const rad=Math.PI/180,az=yaw*rad,el=pitch*rad;const target=scene.camera.target;const r=Math.hypot(...scene.camera.eye.map((x,i)=>x-target[i]))*zoom;const eye=[target[0]+r*Math.sin(az)*Math.cos(el),target[1]+r*Math.sin(el),target[2]-r*Math.cos(az)*Math.cos(el)];
  const result=prepared.render({width,height,steps,eye,target,fov:scene.camera.fov,exposure:scene.camera.exposure,background:'sky'});
  return {rgba:result.rgba,width,height,cells:field.cells,time:field.time,ms:performance.now()-start,reused,cacheBuilds,visiblePixels:result.diagnostics.visiblePixels};
 };
}
