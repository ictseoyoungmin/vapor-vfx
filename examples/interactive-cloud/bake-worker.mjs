import {createCloudField} from './cloud-view.mjs';
import {encodeFieldAsset} from '../../bindings/web/field-asset.mjs';
import {bakeFieldGLBs} from '../../bindings/web/cloud-mesh.mjs';
self.onmessage=({data:{scene,quality,threshold,material,lod}})=>{
  try{
    self.postMessage({progress:'Baking source Float32 density…'});
    const vpf=encodeFieldAsset(createCloudField(scene,quality),scene.time);
    const outputs=bakeFieldGLBs(vpf,{resolution:128,threshold,material:material?scene.material:null,lod,
      onProgress:({level,resolution})=>self.postMessage({progress:'Extracting LOD'+level+' · '+resolution+'³…'})});
    self.postMessage({vpf,outputs,quality,threshold},[vpf.buffer,...outputs.map(o=>o.bytes.buffer)]);
  }catch(error){self.postMessage({error:error instanceof Error?error.message:String(error)});}
};
