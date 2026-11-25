/** Static, indexed density isosurfaces and portable GLB 2.0. No render lighting baked. */
import {decodeFieldAsset} from './field-asset.mjs';

export function extractDensitySurface(field,resolution=128,iso=.18){
  if(![32,64,128].includes(resolution)||!Number.isFinite(iso)||iso<.01||iso>.95)throw new RangeError('Invalid resolution or density threshold');
  const {cells,extent,densityCap,fields:{density}}=field;
  const [nx,ny,nz]=cells, n=resolution, d=n+2, plane=d*d, total=d**3;
  const scalar=new Float32Array(total);
  const lerp=(a,b,t)=>a+(b-a)*t;
  function axis(i,count){
    const x=Math.max(0,Math.min(count-1,(i-.5)*count/n-.5)), lo=Math.floor(x);
    return [lo,Math.min(lo+1,count-1),x-lo];
  }
  const ax=Array.from({length:n+1},(_,i)=>axis(i,nx)),ay=Array.from({length:n+1},(_,i)=>axis(i,ny)),az=Array.from({length:n+1},(_,i)=>axis(i,nz));
  scalar.fill(-iso);
  // Cell-centered source samples, trilinear reconstruction, zero density on the domain boundary.
  for(let z=1;z<=n;z++){const [z0,z1,w]=az[z];
    for(let y=1;y<=n;y++){const [y0,y1,v]=ay[y];
      for(let x=1;x<=n;x++){const [x0,x1,u]=ax[x];
        const a=nx*(y0+ny*z0),b=nx*(y1+ny*z0),c=nx*(y0+ny*z1),e=nx*(y1+ny*z1);
        const s=lerp(lerp(lerp(density[a+x0],density[a+x1],u),lerp(density[b+x0],density[b+x1],u),v),lerp(lerp(density[c+x0],density[c+x1],u),lerp(density[e+x0],density[e+x1],u),v),w)/densityCap-iso;
        // Keep exact/near-threshold samples away from grid corners to avoid zero-area faces.
        scalar[x+d*y+plane*z]=Math.abs(s)<.0001?(s>0?.0001:-.0001):s;
      }
    }
  }
  const positions=[],indices=[],edgeVertices=new Map();
  const coord=i=>i===0?0:i===n+1?1:(i-.5)/n;
  function point(id){
    return [coord(id%d),coord(Math.floor(id/d)%d),coord(Math.floor(id/plane))].map((v,i)=>(v-.5)*extent[i]);
  }
  function edge(a,b){
    const key=Math.min(a,b)*total+Math.max(a,b);
    let i=edgeVertices.get(key);if(i!==undefined)return i;
    const p=point(a),q=point(b),t=scalar[a]/(scalar[a]-scalar[b]);
    i=positions.length/3;for(let k=0;k<3;k++)positions.push(Math.fround(lerp(p[k],q[k],t)));
    edgeVertices.set(key,i);return i;
  }
  function tri(a,b,c,out){
    const ax=positions[3*b]-positions[3*a],ay=positions[3*b+1]-positions[3*a+1],az=positions[3*b+2]-positions[3*a+2];
    const bx=positions[3*c]-positions[3*a],by=positions[3*c+1]-positions[3*a+1],bz=positions[3*c+2]-positions[3*a+2];
    const x=ay*bz-az*by,y=az*bx-ax*bz,z=ax*by-ay*bx;
    if(!(Math.hypot(x,y,z)>0))throw new Error('Degenerate surface triangle');
    if(x*out[0]+y*out[1]+z*out[2]<0)[b,c]=[c,b];
    if(indices.length>=1_800_000)throw new RangeError('Surface exceeds 600,000 triangle budget; increase threshold or lower resolution');
    indices.push(a,b,c);
  }
  const tetra=[[0,1,2,6],[0,2,3,6],[0,3,7,6],[0,7,4,6],[0,4,5,6],[0,5,1,6]];
  const offsets=[0,1,d+1,d,plane,plane+1,plane+d+1,plane+d];
  const ids=new Array(8);
  for(let z=0;z<d-1;z++)for(let y=0;y<d-1;y++)for(let x=0;x<d-1;x++){
    const base=x+y*d+z*plane;let mask=0;
    for(let k=0;k<8;k++){ids[k]=base+offsets[k];if(scalar[ids[k]]>0)mask|=1<<k;}
    if(mask===0||mask===255)continue;
    // Fixed conforming six-tet subdivision; adjacent cubes share the same face diagonals.
    for(const tet of tetra){
      const inside=[],outside=[];
      for(const k of tet){const id=ids[k];(scalar[id]>0?inside:outside).push(id);}
      if(!inside.length||!outside.length)continue;
      const out=[0,0,0];
      for(const id of outside){const p=point(id);for(let k=0;k<3;k++)out[k]+=p[k]/outside.length;}
      for(const id of inside){const p=point(id);for(let k=0;k<3;k++)out[k]-=p[k]/inside.length;}
      if(inside.length===1){const [a]=inside;tri(...outside.map(b=>edge(a,b)),out);}
      else if(outside.length===1){const [a]=outside;tri(...inside.map(b=>edge(a,b)),out);}
      else{
        const [a,b]=inside,[c,e]=outside;
        const ac=edge(a,c),ae=edge(a,e),be=edge(b,e),bc=edge(b,c);
        tri(ac,ae,be,out);tri(ac,be,bc,out);
      }
    }
  }
  if(!indices.length)throw new RangeError('No surface at this density threshold');
  const p=new Float32Array(positions),idx=new Uint32Array(indices),sums=new Float64Array(p.length);
  for(let i=0;i<idx.length;i+=3){
    const a=3*idx[i],b=3*idx[i+1],c=3*idx[i+2];
    const ux=p[b]-p[a],uy=p[b+1]-p[a+1],uz=p[b+2]-p[a+2],vx=p[c]-p[a],vy=p[c+1]-p[a+1],vz=p[c+2]-p[a+2];
    const normal=[uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx];
    for(const k of [a,b,c])for(let j=0;j<3;j++)sums[k+j]+=normal[j];
  }
  const normals=new Float32Array(p.length);
  for(let i=0;i<p.length;i+=3){const len=Math.hypot(sums[i],sums[i+1],sums[i+2]);if(!(len>0))throw Error('Invalid vertex normal');for(let j=0;j<3;j++)normals[i+j]=sums[i+j]/len;}
  return {positions:p,normals,indices:idx,resolution,iso};
}

export function encodeSurfaceGLB(mesh,{material=null,metadata={},name='Vapor cloud'}={}){
  const {positions,normals,indices}=mesh;
  const vertexCount=positions.length/3,short=vertexCount<=65536, indexBytes=indices.length*(short?2:4);
  const binaryLength=positions.byteLength+normals.byteLength+indexBytes,aligned=(n)=>Math.ceil(n/4)*4;
  const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
  for(let i=0;i<positions.length;i++){const k=i%3;min[k]=Math.min(min[k],positions[i]);max[k]=Math.max(max[k],positions[i]);}
  const primitive={attributes:{POSITION:0,NORMAL:1},indices:2,mode:4};
  const document={asset:{version:'2.0',generator:'Vapor VFX density surface exporter'},scene:0,scenes:[{nodes:[0]}],nodes:[{name,mesh:0}],meshes:[{name,primitives:[primitive],extras:{vapor:{...metadata,resolution:mesh.resolution,threshold:mesh.iso,representation:'density-isosurface'}}}],buffers:[{byteLength:binaryLength}],bufferViews:[
    {buffer:0,byteOffset:0,byteLength:positions.byteLength,target:34962},
    {buffer:0,byteOffset:positions.byteLength,byteLength:normals.byteLength,target:34962},
    {buffer:0,byteOffset:positions.byteLength+normals.byteLength,byteLength:indexBytes,target:34963}
  ],accessors:[
    {bufferView:0,componentType:5126,count:vertexCount,type:'VEC3',min,max},
    {bufferView:1,componentType:5126,count:vertexCount,type:'VEC3'},
    {bufferView:2,componentType:short?5123:5125,count:indices.length,type:'SCALAR'}
  ]};
  if(material){
    const colour=material.colour;
    if(!Array.isArray(colour)||colour.length!==3||!colour.every(c=>Number.isFinite(c)&&c>=0&&c<=1))throw new RangeError('Invalid material colour');
    document.materials=[{name:'Cloud surface approximation',pbrMetallicRoughness:{baseColorFactor:[...colour,1],metallicFactor:0,roughnessFactor:1},extras:{vaporVolumeMaterial:material}}];primitive.material=0;
  }
  const json=new TextEncoder().encode(JSON.stringify(document)),jlen=aligned(json.length),blen=aligned(binaryLength);
  const bytes=new Uint8Array(28+jlen+blen),v=new DataView(bytes.buffer);
  v.setUint32(0,0x46546c67,true);v.setUint32(4,2,true);v.setUint32(8,bytes.length,true);
  v.setUint32(12,jlen,true);v.setUint32(16,0x4e4f534a,true);bytes.fill(32,20,20+jlen);bytes.set(json,20);
  v.setUint32(20+jlen,blen,true);v.setUint32(24+jlen,0x004e4942,true);
  let offset=28+jlen;
  for(const arr of [positions,normals])for(const value of arr){v.setFloat32(offset,value,true);offset+=4;}
  for(const value of indices){if(short)v.setUint16(offset,value,true);else v.setUint32(offset,value,true);offset+=short?2:4;}
  return bytes;
}

export function bakeFieldGLBs(vpf,{resolution=128,threshold=.18,material=null,lod=true,onProgress=()=>{}}={}){
  const field=decodeFieldAsset(vpf);
  if(![32,64,128].includes(resolution))throw new RangeError('Invalid bake resolution');
  const levels=lod?[resolution,resolution/2,resolution/4].filter(n=>n>=32):[resolution];
  const outputs=[];
  for(const [level,n] of levels.entries()){
    onProgress({level,resolution:n});
    const mesh=extractDensitySurface(field,n,threshold);
    const name='vapor-cloud-lod'+level;
    const bytes=encodeSurfaceGLB(mesh,{name,material,metadata:{level,sourceFormat:'VPF1',sourceCells:field.cells,extent:field.extent,densityCap:field.densityCap,time:field.time,pivot:'domain-center',axis:'right-handed Y-up',sourceCrc32:new DataView(vpf instanceof ArrayBuffer?vpf:vpf.buffer,vpf instanceof ArrayBuffer?0:vpf.byteOffset).getUint32(64,true)}});
    outputs.push({name:name+'.glb',level,resolution:n,vertices:mesh.positions.length/3,triangles:mesh.indices.length/3,bytes});
  }
  return outputs;
}
