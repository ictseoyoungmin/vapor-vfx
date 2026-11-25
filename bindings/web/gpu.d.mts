import type {RenderSource} from './gpu-render.mjs';
import type {ConfigOptions,EmitterOptions,Vec3,AdvanceReport,Metrics,FieldName,VaporModule,Simulation} from './vapor.mjs';
export type BackendMode='cpu'|'gpu'|'hybrid'|'auto';
export interface ExecutionOptions {
 /** Defaults: CPU, scale 1; fallback disabled. Auto fallback requires explicit allowance. */
 backend?:BackendMode; detailScale?:number; allowCpuFallback?:boolean; allowSoftwareGpu?:boolean;
 /** Fine kinematic curl amplitude in m/s (0 disables); base wave number in rad/m. */
 detailTurbulence?:number; detailFrequency?:number;
 /** Fail-stop deadline for an explicit GPU snapshot; default 15000 ms. */
 readbackTimeoutMs?:number;
 wasmURL?:string|URL|BufferSource; shaderURL?:string|URL; module?:VaporModule;
 /** Optional host-owned WebGPU GPUDevice. Kept structural to avoid a @webgpu/types dependency. */
 device?:unknown;
}
export interface ReadbackStats {
 readonly allocations:number;readonly reuses:number;readonly completed:number;readonly failures:number;
 readonly bytesCopied:number;readonly peakPending:number;readonly peakAllocatedBytes:number;
 readonly pending:number;readonly allocatedBytes:number;readonly buffers:number;readonly capacity:number;
}
export interface BackendInfo {
 readonly requested:BackendMode;readonly active:'cpu'|'gpu'|'hybrid';readonly detailScale:number;
 readonly flags:number;readonly renderCells:readonly number[];readonly initFallback:boolean;
 readonly softwareGpu:boolean|null;readonly adapter?:string;readonly gpuBytes?:number;readonly hybridUploadBytes?:number;
}
/** GPU snapshots return Promises; `await` also works on CPU synchronous snapshots. */
export declare class GpuSimulation {
 readonly config:Readonly<Required<ConfigOptions>>;readonly backendInfo:BackendInfo;readonly closed:boolean;readonly readbackStats:ReadbackStats|null;
 step(steps?:number):void;advance(seconds:number):AdvanceReport;reset():void;dispose():void;
 setEmitter(id:number,options?:EmitterOptions):void;removeEmitter(id:number):void;
 setCapsule(id:number,a:Vec3,b:Vec3,radius:number,velocity?:Vec3):void;setSphere(id:number,center:Vec3,radius:number,velocity?:Vec3):void;
 setBox(id:number,min:Vec3,max:Vec3,velocity?:Vec3):void;removeObstacle(id:number):void;
 setProfile(id:number,points:readonly (readonly [number,number,number,number])[]|null,options?:{duration?:number;startTime?:number;repeat?:boolean}):void;
 /** Borrowed read-only GPU source; consume synchronously before next step/reset/dispose. */
 renderSource():RenderSource;
 macCells():Promise<Float32Array>;metrics():Promise<Metrics>;field(name?:FieldName):Promise<Float32Array>;atlasRGBA8():Promise<Uint8Array>;
}
export type CpuSimulation=Simulation & {readonly backendInfo:BackendInfo};
export declare function createVaporSimulation(config?:ConfigOptions,execution?:ExecutionOptions):Promise<CpuSimulation|GpuSimulation>;
