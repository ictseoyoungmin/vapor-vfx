/** Three.js adapter. Pass your own THREE module; the SDK does not own your renderer. */
export function createVaporVolume(THREE,config,{colour=0xd9e8f5,extinction=16,steps=96,anisotropy=0,albedo=1,emission=0,thermalFade=0,ambient=.3}={}){
 const {nx,ny,nz,cellSize,densityCap}=config;
 const extent=new THREE.Vector3(nx*cellSize,ny*cellSize,nz*cellSize);
 const bytes=new Uint8Array(nx*ny*nz*4);
 const texture=new THREE.DataTexture(bytes,nx,ny*nz,THREE.RGBAFormat,THREE.UnsignedByteType);
 texture.minFilter=texture.magFilter=THREE.LinearFilter;texture.generateMipmaps=false;texture.flipY=false;texture.unpackAlignment=1;
 texture.colorSpace=THREE.NoColorSpace;texture.needsUpdate=true;
 const uniforms={uAtlas:{value:texture},uGrid:{value:new THREE.Vector3(nx,ny,nz)},uExtent:{value:extent},uCap:{value:densityCap},uExtinction:{value:extinction},uColour:{value:(Array.isArray(colour)?new THREE.Color(...colour):new THREE.Color(colour))},uAnisotropy:{value:anisotropy},uAlbedo:{value:albedo},uEmission:{value:emission},uThermalFade:{value:thermalFade},uAmbient:{value:ambient},uEye:{value:new THREE.Vector3()},uSteps:{value:Math.min(256,Math.max(8,steps))},uDepth:{value:null},uHasDepth:{value:false},uDepthSize:{value:new THREE.Vector2(1,1)},uInvVP:{value:new THREE.Matrix4()},uInvModel:{value:new THREE.Matrix4()}};
 const material=new THREE.ShaderMaterial({uniforms,transparent:true,side:THREE.BackSide,depthTest:false,depthWrite:false,premultipliedAlpha:true,blending:THREE.NormalBlending,
 vertexShader:`varying vec3 vPosition;void main(){vPosition=position+0.5;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
 fragmentShader:`precision highp float;
 varying vec3 vPosition;uniform sampler2D uAtlas,uDepth;uniform vec3 uGrid,uExtent,uEye,uColour;uniform float uCap,uExtinction,uAnisotropy,uAlbedo,uEmission,uThermalFade,uAmbient;uniform int uSteps;uniform bool uHasDepth;uniform vec2 uDepthSize;uniform mat4 uInvVP,uInvModel;
 vec2 sampleField(vec3 p){if(any(lessThan(p,vec3(0.)))||any(greaterThan(p,vec3(1.))))return vec2(0.);vec3 q=clamp(p*uGrid,vec3(.5),uGrid-.5);float z=q.z-.5;float z0=floor(z);float z1=min(z0+1.,uGrid.z-1.);vec2 uv0=vec2(q.x/uGrid.x,(z0*uGrid.y+q.y)/(uGrid.y*uGrid.z));vec2 uv1=vec2(uv0.x,(z1*uGrid.y+q.y)/(uGrid.y*uGrid.z));return mix(texture2D(uAtlas,uv0).rg,texture2D(uAtlas,uv1).rg,fract(z));}
 float density(vec3 p){vec2 f=sampleField(p);return f.r*uCap*(1.-uThermalFade*(1.-exp(-f.g*16.)));}
 bool hit(vec3 ro,vec3 rd,out float nearT,out float farT){nearT=0.;farT=1e8;for(int a=0;a<3;a++){if(abs(rd[a])<1e-7){if(ro[a]<0.||ro[a]>1.)return false;}else{float x=(0.-ro[a])/rd[a],y=(1.-ro[a])/rd[a];nearT=max(nearT,min(x,y));farT=min(farT,max(x,y));}}return farT>nearT;}
 void main(){vec3 rd=normalize(vPosition-uEye);float a,b;if(!hit(uEye,rd,a,b))discard;
 if(uHasDepth){vec2 uv=gl_FragCoord.xy/uDepthSize;float depth=texture2D(uDepth,uv).r;if(depth<.999999){vec4 world=uInvVP*vec4(uv*2.-1.,depth*2.-1.,1.);world/=world.w;vec3 scene=(uInvModel*world).xyz+.5;b=min(b,dot(scene-uEye,rd));}}
 if(b<=a)discard;float dt=(b-a)/float(uSteps);float metric=length(rd*uExtent);float alpha=0.;vec3 colour=vec3(0.);
 vec3 lightDir=normalize(vec3(-.45,.8,.35));float shadowStep=min(uExtent.x,min(uExtent.y,uExtent.z))/8.;float g=clamp(uAnisotropy,-.9,.9);float phase=min(4.,(1.-g*g)/pow(max(.001,1.+g*g-2.*g*dot(normalize(rd*uExtent),lightDir)),1.5));
 for(int i=0;i<256;i++){if(i>=uSteps||alpha>.995)break;vec3 p=uEye+rd*(a+(float(i)+.5)*dt);float d=density(p);if(d<.001)continue;float light=1.;for(int j=1;j<=8;j++){light*=exp(-density(p+lightDir*(float(j)*shadowStep)/uExtent)*uExtinction*shadowStep);}float opacity=1.-exp(-d*uExtinction*dt*metric);float w=(1.-alpha)*opacity;float heat=clamp(sampleField(p).g*16./5.,0.,1.);colour+=w*(uColour*uAlbedo*(uAmbient+(1.-uAmbient)*light*phase)+vec3(1.,.3,.045)*uEmission*heat*heat);alpha+=w;}
 gl_FragColor=vec4(colour,alpha);}`});
 const mesh=new THREE.Mesh(new THREE.BoxGeometry(1,1,1),material);
 mesh.scale.copy(extent);mesh.position.set(...(config.origin??[0,0,0])).addScaledVector(extent,.5);mesh.frustumCulled=false;mesh.renderOrder=10;
 let disposed=false;const worldEye=new THREE.Vector3();
 mesh.onBeforeRender=(renderer,scene,camera)=>{if(nx>renderer.capabilities.maxTextureSize||ny*nz>renderer.capabilities.maxTextureSize)throw new RangeError("Vapor atlas exceeds GPU maxTextureSize");if(!camera.isPerspectiveCamera)throw new Error("Vapor adapter currently requires a perspective camera");camera.getWorldPosition(worldEye);uniforms.uEye.value.copy(worldEye);mesh.worldToLocal(uniforms.uEye.value);uniforms.uEye.value.addScalar(.5);uniforms.uInvVP.value.multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse).invert();uniforms.uInvModel.value.copy(mesh.matrixWorld).invert();};
 return {mesh,texture,material,
  update(atlas){if(disposed)throw new Error('Vapor volume disposed');if(!(atlas instanceof Uint8Array)||atlas.length!==bytes.length)throw new RangeError('atlas byte count mismatch');bytes.set(atlas);texture.needsUpdate=true;},
  setSteps(steps){if(!Number.isFinite(steps))throw new RangeError("invalid steps");uniforms.uSteps.value=Math.round(Math.min(256,Math.max(8,steps)));},
  setSceneDepth(depthTexture,width,height){uniforms.uDepth.value=depthTexture;uniforms.uHasDepth.value=!!depthTexture;uniforms.uDepthSize.value.set(width,height);},
  dispose(){if(disposed)return;disposed=true;mesh.removeFromParent();mesh.geometry.dispose();material.dispose();texture.dispose();}
 };
}
