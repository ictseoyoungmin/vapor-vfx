import type {GpuSimulation} from './gpu.mjs';
import type {VolumeView} from './gpu-render.mjs';
export type HistoryMode='off'|'static'|'dynamic';
export interface TemporalView extends VolumeView {width:number;height:number;historyMode?:HistoryMode;historyWeight?:number;sceneDepth?:never;}
export interface TemporalDiagnostics {readonly historyEligible:boolean;readonly historyWeight:number;readonly reason:string;readonly historyBytes:number;readonly passes:3;}
export interface TemporalPolicyInput {epoch?:object;tick?:number;packet:ArrayBuffer;width:number;height:number;mode:HistoryMode;weight:number;}
export declare function temporalPolicy(previous:TemporalPolicyInput|null,current:TemporalPolicyInput):{eligible:boolean;weight:number;reason:string};
export declare class GpuTemporalVolumeRenderer {private constructor();static create(simulation:GpuSimulation,options?:{format?:string;maxHistoryBytes?:number;shaderURL?:URL|string;temporalShaderURL?:URL|string}):Promise<GpuTemporalVolumeRenderer>;readonly closed:boolean;readonly draws:number;readonly historyBytes:number;readonly format:string;readonly device:unknown;render(view:unknown,options:TemporalView):TemporalDiagnostics;resetHistory():void;dispose():void;}
