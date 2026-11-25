/** Small opaque-scene reference for the game composition demo. Analytic boxes
 * and floor, perspective camera identical to the CPU preview (40-degree FOV).
 * This is a test scene, not a replacement for a game renderer. */
const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0),sub=(a,b)=>a.map((x,i)=>x-b[i]),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]],unit=v=>v.map(x=>x/Math.hypot(...v)),clamp=x=>Math.max(0,Math.min(1,x));
const srgb=x=>Math.round(255*clamp(x<=.0031308?12.92*x:1.055*x**(1/2.4)-.055));
const light=unit([-.45,.8,.35]);
const box=(lo,hi,colour)=>({lo,hi,colour});
// Concrete structures and markers in a 60 m × 60 m fog volume.
const objects=[
 box([23,0,-9],[25.8,9,-6],[.22,.25,.28]),box([36,0,-5],[38,7,-3],[.27,.30,.33]),
 box([7,0,3],[14,10,13],[.22,.25,.28]),box([46,0,5],[53,14,15],[.25,.28,.31]),
 box([17,0,19],[22,8,28],[.22,.27,.31]),box([38,0,20],[43,9,29],[.23,.28,.32]),
 box([17,8,19],[43,9.4,22],[.26,.29,.32]),box([21,0,36],[27,12,45],[.19,.23,.27]),box([34,0,37],[41,17,46],[.23,.27,.30]),
 box([3,0,44],[15,19,54],[.19,.23,.27]),box([47,0,42],[58,23,55],[.24,.26,.28]),
 box([8,0,19],[9.6,3.5,20.6],[.57,.32,.08]),box([49,0,24],[50.6,3.5,25.6],[.57,.32,.08]),
 box([24,0,9],[25,1.3,10],[.50,.27,.075]),box([35,0,9],[36,1.3,10],[.50,.27,.075])];
function hitBox(o,d,b,limit=Infinity){let near=0,far=limit,axis=0,sign=0;for(let a=0;a<3;a++){if(Math.abs(d[a])<1e-10){if(o[a]<b.lo[a]||o[a]>b.hi[a])return null;continue;}const l=(b.lo[a]-o[a])/d[a],h=(b.hi[a]-o[a])/d[a],t=Math.min(l,h);if(t>near){near=t;axis=a;sign=l<h?-1:1;}far=Math.min(far,Math.max(l,h));if(far<=near)return null;}if(near<=0)return null;const n=[0,0,0];n[axis]=sign;return {t:near,n,colour:b.colour};}
export const demoCamera=Object.freeze({eye:[30,7,-28],target:[30,5,34],width:640,height:400,steps:112});
export function renderOpaqueScene({eye,target,width,height}){
 const f=unit(sub(target,eye)),r=unit(cross(f,[0,1,0])),u=cross(r,f),half=Math.tan(20*Math.PI/180),depth=new Float32Array(width*height),colour=new Uint8Array(width*height*4),objectMask=new Uint8Array(width*height);
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){const i=y*width+x,d=unit(f.map((v,a)=>v+r[a]*(2*(x+.5)/width-1)*half*width/height+u[a]*(1-2*(y+.5)/height)*half));let hit=null;
  if(d[1]<-1e-7){const t=-eye[1]/d[1];if(t>0){const p=eye.map((v,a)=>v+d[a]*t),line=Math.min(Math.abs(p[0]/4-Math.round(p[0]/4)),Math.abs(p[2]/4-Math.round(p[2]/4)))<.013;const road=Math.abs(p[0]-30)<5,mark=road&&Math.abs(p[0]-30)<.13&&((p[2]%7+7)%7)<3;const base=mark?[.46,.39,.23]:road?[.082,.095,.111]:line?[.145,.161,.174]:[.115,.13,.15];hit={t,n:[0,1,0],colour:base};}}
  for(const b of objects){const h=hitBox(eye,d,b,hit?.t??Infinity);if(h){hit=h;objectMask[i]=1;}}
  let rgb;if(hit){depth[i]=hit.t;const p=eye.map((v,a)=>v+d[a]*hit.t+hit.n[a]*.002);const shadow=objects.some(b=>hitBox(p,light,b));const lit=.42+.58*Math.max(0,dot(hit.n,light))*(shadow?.16:1);const haze=1-Math.exp(-hit.t*.002);rgb=hit.colour.map((v,a)=>v*lit*(1-haze)+[.17,.24,.32][a]*haze);}
  else rgb=[.19+.09*clamp(d[1]),.30+.12*clamp(d[1]),.43+.15*clamp(d[1])];
  colour.set([...rgb.map(srgb),255],i*4);
 }return {depth,colour,objectMask};
}
