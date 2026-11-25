import type {RenderSource} from './gpu-render.mjs';
import type {FidelityFields} from './fidelity.mjs';
export interface FloatVolume {cells:readonly number[];extent:readonly number[];densityCap:number;fields:FidelityFields;model?:string;}
export declare function packFloatField(volume:FloatVolume):{packed:Float32Array;cells:readonly number[];extent:readonly number[];densityCap:number};
export declare class GpuFieldVolume {private constructor();static create(device:unknown,volume:FloatVolume,options?:{origin?:readonly number[];reuseBuffers?:boolean}):Promise<GpuFieldVolume>;readonly bytes:number;readonly sourceModel:string|null;readonly closed:boolean;replace(volume:FloatVolume):Promise<this>;setOrigin(origin:readonly number[]):void;renderSource():RenderSource;dispose():void;}
