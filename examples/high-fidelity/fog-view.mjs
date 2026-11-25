/** Terrain-fog reference shared by the dedicated example and Fidelity Lab. */
import {generateFidelityVolume,getFidelityPreset,prepareFidelityVolume} from '../../bindings/web/fidelity.mjs';
import {valleyTerrain,createValleyScene} from './valley.mjs';

export function createTerrainFogSession(){
  const extent=[60,15,60];
  let volume,fieldKey,prepared,lightKey,fieldBuilds=0,cacheBuilds=0;
  return Object.freeze({
    render({quality='medium',view='valley',lighting='side',coverage=.42,width=480,height=300}={}){
      if(!['medium','high'].includes(quality)||!['valley','oblique'].includes(view)||!['side','back'].includes(lighting))throw new RangeError('Unknown terrain fog setting');
      if(!Number.isFinite(coverage)||coverage<0||coverage>1)throw new RangeError('Invalid fog coverage');
      if(!Number.isInteger(width)||!Number.isInteger(height)||width<32||height<32||width>960||height>600)throw new RangeError('Invalid render size');
      const start=performance.now(),cells=quality==='high'?[96,24,96]:[48,12,48];
      const nextFieldKey=JSON.stringify([quality,coverage]);
      if(!volume||fieldKey!==nextFieldKey){
        volume=generateFidelityVolume('ground_fog',{cells,extent,terrain:valleyTerrain(cells,extent),settings:{coverage,humidity:.64}});
        fieldKey=nextFieldKey;prepared=null;fieldBuilds++;
      }
      const camera={eye:view==='oblique'?[23,6.5,-6]:[29.8,6.5,-6],target:[30,3.9,34],fov:47,width,height};
      const light={direction:lighting==='back'?[.16,.56,.82]:[-.80,.56,.16],radiance:[.95,.80,.62]};
      const opaque=createValleyScene(camera,light.direction);
      const reused=Boolean(prepared&&lightKey===lighting);
      if(!reused){
        const style=getFidelityPreset('ground_fog',quality);
        style.material.extinction=.10;style.material.anisotropy=.25;
        prepared=prepareFidelityVolume({...volume,material:style.material,...style.lighting,light,sunVisibility:opaque.sunVisibility,shadowSteps:32,lightScale:.5});
        lightKey=lighting;cacheBuilds++;
      }
      const steps=quality==='high'?160:96;
      const frame=prepared.render({...camera,steps,scene:opaque.scene});
      return {rgba:frame.rgba,width,height,cells:volume.cells.slice(),steps,visiblePixels:frame.diagnostics.visiblePixels,fieldBuilds,cacheBuilds,reused,ms:performance.now()-start};
    }
  });
}
