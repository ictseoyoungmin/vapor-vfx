import {createCloudSession} from './cloud-view.mjs';
let session;
self.onmessage=({data})=>{
  const {id,scene,options}=data;
  try {
    if(!session)session=createCloudSession(scene);
    const frame=session.render(options);
    self.postMessage({id,...frame},[frame.rgba.buffer]);
  } catch(error) {self.postMessage({id,error:error instanceof Error?error.message:String(error)});}
};
