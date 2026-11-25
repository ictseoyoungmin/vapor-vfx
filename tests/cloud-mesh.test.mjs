import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {encodeFieldAsset,decodeFieldAsset} from '../bindings/web/field-asset.mjs';
import {bakeFieldGLBs} from '../bindings/web/cloud-mesh.mjs';
import {createCloudField} from '../examples/interactive-cloud/cloud-view.mjs';
const scene=JSON.parse(readFileSync(new URL('../contracts/cloud-hero.json',import.meta.url),'utf8'));
function inspect(bytes){
  const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  assert.equal(v.getUint32(0,true),0x46546c67);assert.equal(v.getUint32(4,true),2);assert.equal(v.getUint32(8,true),bytes.length);
  const len=v.getUint32(12,true),base=28+len;
  assert.equal(len%4,0);assert.equal(v.getUint32(16,true),0x4e4f534a);assert.equal(v.getUint32(base-4,true),0x004e4942);
  const doc=JSON.parse(new TextDecoder().decode(bytes.subarray(20,20+len)));
  assert.equal(doc.asset.version,'2.0');assert.equal(doc.scenes[0].nodes[0],0);assert.equal(doc.nodes[0].mesh,0);
  const binlen=v.getUint32(base-8,true);assert.equal(base+binlen,bytes.length);assert.ok(binlen-doc.buffers[0].byteLength<4);assert.ok(binlen>=doc.buffers[0].byteLength);
  const [pos,norm,idx]=doc.accessors;assert.equal(pos.count,norm.count);assert.equal(pos.type,'VEC3');assert.equal(norm.type,'VEC3');assert.equal(idx.type,'SCALAR');assert.equal(idx.count%3,0);assert.equal(pos.componentType,5126);assert.equal(norm.componentType,5126);
  for(const bv of doc.bufferViews){assert.equal(bv.byteOffset%4,0);assert.ok(bv.byteOffset+bv.byteLength<=doc.buffers[0].byteLength);}
  const p=Array.from({length:pos.count*3},(_,i)=>v.getFloat32(base+doc.bufferViews[0].byteOffset+4*i,true));
  const normals=Array.from({length:norm.count*3},(_,i)=>v.getFloat32(base+doc.bufferViews[1].byteOffset+4*i,true));
  assert.ok([5123,5125].includes(idx.componentType));const width=idx.componentType===5123?2:4;
  const ids=Array.from({length:idx.count},(_,i)=>width===2?v.getUint16(base+doc.bufferViews[2].byteOffset+2*i,true):v.getUint32(base+doc.bufferViews[2].byteOffset+4*i,true));
  assert.ok(p.every(Number.isFinite));assert.ok(ids.every(i=>i<pos.count));
  const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
  for(let i=0;i<p.length;i+=3){assert.ok(Math.abs(Math.hypot(normals[i],normals[i+1],normals[i+2])-1)<1e-5);for(let k=0;k<3;k++){min[k]=Math.min(min[k],p[i+k]);max[k]=Math.max(max[k],p[i+k]);}}
  assert.deepEqual(min,pos.min);assert.deepEqual(max,pos.max);
  const edges=new Map();let volume=0;
  for(let i=0;i<ids.length;i+=3){
    const [a,b,c]=ids.slice(i,i+3);assert.ok(a!==b&&b!==c&&a!==c);
    for(const [x,y] of [[a,b],[b,c],[c,a]]){const key=Math.min(x,y)*pos.count+Math.max(x,y),entry=edges.get(key)||[0,0];entry[0]++;entry[1]+=x<y?1:-1;edges.set(key,entry);}
    const A=p.slice(3*a,3*a+3),B=p.slice(3*b,3*b+3),C=p.slice(3*c,3*c+3),u=B.map((x,j)=>x-A[j]),w=C.map((x,j)=>x-A[j]);
    assert.ok(Math.hypot(u[1]*w[2]-u[2]*w[1],u[2]*w[0]-u[0]*w[2],u[0]*w[1]-u[1]*w[0])>0);
    volume+=(A[0]*(B[1]*C[2]-B[2]*C[1])+A[1]*(B[2]*C[0]-B[0]*C[2])+A[2]*(B[0]*C[1]-B[1]*C[0]))/6;
  }
  for(const e of edges.values())assert.deepEqual(e,[2,0],'non-manifold or inconsistent edge winding');
  assert.ok(volume>0);
  return {doc,volume,min,max,triangles:ids.length/3};
}
function sphere(){
  const n=32,density=new Float32Array(n**3);
  for(let z=0;z<n;z++)for(let y=0;y<n;y++)for(let x=0;x<n;x++)density[x+n*(y+n*z)]=Math.max(0,1-Math.hypot((x+.5)/n-.5,(y+.5)/n-.5,(z+.5)/n-.5)*2.5);
  return encodeFieldAsset({cells:[n,n,n],extent:[10,10,10],densityCap:1,fields:{density,temperature:new Float32Array(n**3)}});
}
test('analytic sphere: closed outward indexed surfaces, real 128/64/32 LOD and volume agreement',()=>{
  const output=bakeFieldGLBs(sphere()),expected=4*Math.PI*(10*(1-.18)/2.5)**3/3;
  assert.deepEqual(output.map(o=>o.resolution),[128,64,32]);
  const stats=output.map(o=>inspect(o.bytes));
  for(const [i,s] of stats.entries()){assert.ok(Math.abs(s.volume/expected-1)<.03);assert.equal(s.triangles,output[i].triangles);assert.equal(s.doc.materials,undefined);}
  assert.ok(stats[1].triangles<stats[0].triangles*.4);assert.ok(stats[2].triangles<stats[1].triangles*.4);
});
test('actual canonical cloud from VPF1: GLB material, consistent coordinates, shrinking LOD geometry',()=>{
  const field=createCloudField(scene,'preview'),vpf=encodeFieldAsset(field,scene.time),decoded=decodeFieldAsset(vpf);
  assert.deepEqual(decoded.fields.density,field.fields.density);
  const output=bakeFieldGLBs(vpf,{material:scene.material}),stats=output.map(o=>inspect(o.bytes));
  assert.deepEqual(output.map(o=>o.resolution),[128,64,32]);
  for(let i=0;i<3;i++){const s=stats[i],metadata=s.doc.meshes[0].extras.vapor;assert.equal(metadata.level,i);assert.equal(metadata.resolution,output[i].resolution);assert.deepEqual(metadata.sourceCells,field.cells);assert.deepEqual(metadata.extent,field.extent);assert.equal(metadata.pivot,'domain-center');
    assert.deepEqual(s.doc.materials[0].extras.vaporVolumeMaterial,scene.material);assert.deepEqual(s.doc.materials[0].pbrMetallicRoughness.baseColorFactor,[...scene.material.colour,1]);assert.equal(s.doc.meshes[0].primitives[0].material,0);
    for(let j=0;j<3;j++){assert.ok(Math.abs(s.min[j]-stats[0].min[j])<field.extent[j]*.08);assert.ok(Math.abs(s.max[j]-stats[0].max[j])<field.extent[j]*.08);}
    assert.ok(Math.abs(s.volume/stats[0].volume-1)<.15);
  }
  assert.ok(stats[0].triangles>stats[1].triangles&&stats[1].triangles>stats[2].triangles);
  console.log('Canonical cloud:',JSON.stringify(output.map(({resolution,vertices,triangles,bytes},i)=>({resolution,vertices,triangles,bytes:bytes.length,volume:stats[i].volume}))));
});
test('no LOD, optional material, corrupt VPF and invalid threshold are handled',()=>{
  const vpf=sphere(),outputs=bakeFieldGLBs(vpf,{resolution:32,lod:false});assert.equal(outputs.length,1);assert.equal(inspect(outputs[0].bytes).doc.materials,undefined);
  assert.throws(()=>bakeFieldGLBs(vpf,{threshold:0}),/threshold/);
  const broken=vpf.slice();broken[broken.length-1]^=1;assert.throws(()=>bakeFieldGLBs(broken),/CRC/);
});
