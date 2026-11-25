import type {ExecutionOptions,BackendInfo} from './gpu.mjs';
import type {ConfigOptions,AdvanceReport,Metrics,EmitterOptions,Vec3} from './vapor.mjs';
export interface WorkerOptions {maxPendingRequests?:number;requestTimeoutMs?:number;shutdownTimeoutMs?:number;}
export interface WorkerDiagnostics {readonly pendingRequests:number;readonly tickPending:boolean;readonly queuedSeconds:number;readonly clientDiscardedSeconds:number;readonly ready:boolean;readonly closing:boolean;readonly closed:boolean;}
export declare class VaporWorkerClient {
 constructor(url?:string|URL,options?:WorkerOptions);
 readonly closed:boolean;readonly diagnostics:WorkerDiagnostics;
 discardPendingTime():void;
 init(wasmURL?:string|URL,config?:ConfigOptions,execution?:Omit<ExecutionOptions,'device'|'module'|'wasmURL'>):Promise<Readonly<Required<ConfigOptions>> & {backendInfo:BackendInfo}>;
 tick(seconds:number):Promise<{timing:AdvanceReport;atlas:Uint8Array}|null>;
 call(method:'metrics'):Promise<Metrics>;
 call(method:'diagnostics'):Promise<{backendInfo:BackendInfo;readback:import('./gpu.mjs').ReadbackStats|null}>;
 call(method:'setEmitter',id:number,options:EmitterOptions):Promise<void>;
 call(method:'setSphere',id:number,center:Vec3,radius:number,velocity?:Vec3):Promise<void>;
 call(method:'setCapsule',id:number,a:Vec3,b:Vec3,radius:number,velocity?:Vec3):Promise<void>;
 call(method:'setBox',id:number,min:Vec3,max:Vec3,velocity?:Vec3):Promise<void>;
 call(method:'removeEmitter'|'removeObstacle',id:number):Promise<void>;
 call(method:'reset'):Promise<void>;
 call(method:'step',steps?:number):Promise<void>;
 call(method:'advance',seconds:number):Promise<AdvanceReport>;
 call(method:'setProfile',id:number,points:readonly (readonly [number,number,number,number])[]|null,options?:{duration?:number;startTime?:number;repeat?:boolean}):Promise<void>;
 dispose():Promise<void>;
}
