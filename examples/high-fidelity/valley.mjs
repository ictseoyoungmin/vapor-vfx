/** Small deterministic CPU opaque scene for testing terrain fog and sun visibility.
 * Analytic terrain + tree geometry; no generated/stock imagery. */
import {cameraFrame} from '../../bindings/web/fidelity.mjs';
const sat=x=>Math.max(0,Math.min(1,x)),mix=(a,b,t)=>a+(b-a)*t,dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0),unit=v=>{const n=Math.hypot(...v);return v.map(x=>x/n);};
const random=(x,z)=>{const a=Math.sin(x*127.1+z*311.7)*43758.5453;return a-Math.floor(a);};
export function valleyHeight(x,z){const valley=2.9*(1-Math.exp(-((x-30)*(x-30))/280));return .65+valley+.5*Math.sin(z*.11+x*.08)+.35*Math.sin(x*.29-z*.12)+.18*Math.sin(z*.31+x*.21);}
export function valleyTerrain(cells,extent){const [nx,,nz]=cells;return Float32Array.from({length:nx*nz},(_,i)=>Math.max(0,valleyHeight((i%nx+.5)/nx*extent[0],(Math.floor(i/nx)+.5)/nz*extent[2])));}
function treeSet(){const a=[];for(let i=0;i<64;i++){const side=i%2,ix=Math.floor(i/2),z=5+random(ix,9)*75,x=side?38+random(ix,3)*32:22-random(ix,6)*32;const h=4.7+random(i,1)*7.2,r=h*(.14+.055*random(i,2));a.push({x,z,y:valleyHeight(x,z),h,r,tint:random(i,4)});}return a;}
function boxHit(o,d,min,max,limit){let lo=.001,hi=limit;for(let i=0;i<3;i++){if(Math.abs(d[i])<1e-10){if(o[i]<min[i]||o[i]>max[i])return false;}else{const t0=(min[i]-o[i])/d[i],t1=(max[i]-o[i])/d[i];lo=Math.max(lo,Math.min(t0,t1));hi=Math.min(hi,Math.max(t0,t1));if(lo>hi)return false;}}return true;}
function root(a,b,c){if(Math.abs(a)<1e-9)return Math.abs(b)<1e-9?[]:[-c/b];const det=b*b-4*a*c;if(det<0)return [];const r=Math.sqrt(det),u=(-b-r)/(2*a),v=(-b+r)/(2*a);return u<v?[u,v]:[v,u];}
function treeHit(tree,o,d,limit,any=false){const {x,y,z,h,r}=tree;if(!boxHit(o,d,[x-r,y,z-r],[x+r,y+h,z+r],limit))return null;let best=null,t=limit;const ox=o[0]-x,oz=o[2]-z,dx=d[0],dz=d[2];
 const trunk=r*.12;for(const k of root(dx*dx+dz*dz,2*(ox*dx+oz*dz),ox*ox+oz*oz-trunk*trunk)){if(k>.005&&k<t&&o[1]+k*d[1]>=y&&o[1]+k*d[1]<=y+h*.83){t=k;best={t,normal:unit([ox+k*dx,0,oz+k*dz]),trunk:true,tree};if(any)return best;}}
 for(let i=0;i<5;i++){const base=y+h*(.14+.14*i),top=y+h*Math.min(1,.56+.12*i),rr=r*(1-.135*i),s=rr/(top-base),oy=top-o[1],dy=d[1];const k2=s*s;
  for(const k of root(dx*dx+dz*dz-k2*dy*dy,2*(ox*dx+oz*dz+k2*oy*dy),ox*ox+oz*oz-k2*oy*oy)){const py=o[1]+k*dy;if(k>.005&&k<t&&py>=base&&py<=top){t=k;best={t,normal:unit([ox+k*dx,k2*(top-py),oz+k*dz]),trunk:false,tree};if(any)return best;}}
 }return best;
}
function terrainHit(o,d,maxT){let prev=.01;let pv=o[1]+prev*d[1]-valleyHeight(o[0]+prev*d[0],o[2]+prev*d[2]);if(pv<0)return prev;for(let t=.25;t<maxT;t+=.35+t*.009){const x=o[0]+d[0]*t,y=o[1]+d[1]*t,z=o[2]+d[2]*t,v=y-valleyHeight(x,z);if(v<0){let a=prev,b=t;for(let j=0;j<7;j++){const m=(a+b)*.5;if(o[1]+d[1]*m<valleyHeight(o[0]+d[0]*m,o[2]+d[2]*m))b=m;else a=m;}return (a+b)*.5;}prev=t;pv=v;}return maxT;}
export function createValleyScene(camera,light){const {width,height}=camera,cam=cameraFrame(camera),trees=treeSet(),sun=unit(light),depth=new Float32Array(width*height),radiance=new Float32Array(width*height*3);const shadow=(o,d=sun)=>{const origin=[o[0]+d[0]*.06,o[1]+d[1]*.06,o[2]+d[2]*.06];for(const tree of trees)if(treeHit(tree,origin,d,100,true))return 0;return 1;};
 for(let y=0,i=0;y<height;y++)for(let x=0;x<width;x++,i++){
  const d=cam.ray(x,y),eye=cam.eye;let t=terrainHit(eye,d,180),hit=null;for(const tree of trees){const h=treeHit(tree,eye,d,t);if(h){hit=h;t=h.t;}}
  const h=sat(1-d[1]*3.2),solar=Math.pow(Math.max(0,dot(d,sun)),30);let sky=[mix(.035,.23,h)+.28*solar,mix(.09,.21,h)+.17*solar,mix(.18,.23,h)+.055*solar],col=sky;
  if(t<180){const p=eye.map((v,j)=>v+t*d[j]);let n,base;
    if(hit){n=hit.normal;const detail=.78+.22*random(Math.floor(p[0]*15),Math.floor(p[1]*15+p[2]*17));base=hit.trunk?[.068,.040,.022]:[.018+hit.tree.tint*.015,.040+hit.tree.tint*.024,.030+hit.tree.tint*.014].map(v=>v*detail);}
    else{const dd=.08;n=unit([(valleyHeight(p[0]-dd,p[2])-valleyHeight(p[0]+dd,p[2]))/(2*dd),1,(valleyHeight(p[0],p[2]-dd)-valleyHeight(p[0],p[2]+dd))/(2*dd)]);const trail=Math.exp(-((p[0]-30-2.2*Math.sin(p[2]*.085))**2)/2.2),noise=.72+.28*random(Math.floor(p[0]*12),Math.floor(p[2]*12));base=[mix(.040,.105,trail)*noise,mix(.068,.085,trail)*noise,mix(.035,.060,trail)*noise];}
    const lit=Math.max(0,dot(n,sun))*shadow(p),fade=1-Math.exp(-t/135);col=base.map((v,j)=>mix(v*(.38+lit*[1.8,1.2,.8][j])+[.006,.009,.015][j],sky[j],fade*.68));depth[i]=t;
  }
  radiance.set(col,i*3);
 }return {scene:{depth,radiance},sunVisibility:shadow,trees:trees.length};}
