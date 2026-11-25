import type {GpuSimulation} from './gpu.mjs';
import type {VolumeView,SceneDepthView,RenderSource} from './gpu-render.mjs';
import type {Vec3} from './vapor.mjs';
export interface FidelityLightOptions {lightScale?:number;lightSteps?:number;sunRadiance?:Vec3;sky?:Vec3;ground?:Vec3;multiScatter?:number;exposure?:number;}
export interface FidelityGpuDiagnostics {readonly cacheReused:boolean;readonly cacheBuilds:number;readonly cacheBytes:number;readonly lightCells:number[];readonly passes:number;}
export declare function packFidelityLighting(source:RenderSource,options?:FidelityLightOptions):{bytes:ArrayBuffer;cells:number[];count:number;cacheBytes:number};
/** Direct opt-in fidelity renderer. Transparent mode outputs linear HDR premultiplied; opaque standalone preview is tone mapped. */
export declare class GpuFidelityVolumeRenderer {private constructor();static create(simulation:GpuSimulation|{renderSource():RenderSource},options?:{format?:string;enableSceneDepth?:boolean;shaderURL?:string|URL;fidelityURL?:string|URL}):Promise<GpuFidelityVolumeRenderer>;readonly format:string;readonly closed:boolean;readonly draws:number;readonly cacheBuilds:number;readonly cacheBytes:number;render(view:unknown,options:(VolumeView|SceneDepthView)&FidelityLightOptions):FidelityGpuDiagnostics;dispose():void;}
