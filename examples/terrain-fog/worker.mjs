import {createTerrainFogSession} from '../high-fidelity/fog-view.mjs';
const session=createTerrainFogSession();
self.onmessage=({data})=>{
  try {
    const frame=session.render(data.options);
    self.postMessage({id:data.id,...frame},[frame.rgba.buffer]);
  } catch(error){self.postMessage({id:data.id,error:error instanceof Error?error.message:String(error)});}
};
