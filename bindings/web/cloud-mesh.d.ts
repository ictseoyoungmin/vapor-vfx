import type {BakedField} from './field-asset.mjs';
import type {Material} from './effects.mjs';
export type SurfaceMesh={positions:Float32Array;normals:Float32Array;indices:Uint32Array;resolution:number;iso:number};
export type BakedGLB={name:string;level:number;resolution:number;vertices:number;triangles:number;bytes:Uint8Array};
export function extractDensitySurface(field:BakedField,resolution?:32|64|128,iso?:number):SurfaceMesh;
export function encodeSurfaceGLB(mesh:SurfaceMesh,options?:{material?:Material|null;metadata?:Record<string,unknown>;name?:string}):Uint8Array;
export function bakeFieldGLBs(vpf:ArrayBuffer|Uint8Array,options?:{resolution?:32|64|128;threshold?:number;material?:Material|null;lod?:boolean;onProgress?:(info:{level:number;resolution:number})=>void}):BakedGLB[];
