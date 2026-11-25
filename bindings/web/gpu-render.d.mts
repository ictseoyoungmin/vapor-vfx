import type {GpuSimulation} from './gpu.mjs';
import type {Vec3} from './vapor.mjs';
import type {Material} from './effects.mjs';
export interface VolumeView {eye:Vec3;target:Vec3;up?:Vec3;aspect?:number;fov?:number;material:Material;light?:Vec3;steps?:number;shadowSteps?:number;background?:'transparent'|'dark'|'sky';load?:boolean;}
/** Same-device host texture: top-left pixel, ray distance in metres, 0 = no hit. */
export interface SceneDepthView extends VolumeView {sceneDepth:unknown;width:number;height:number;load:true;background?:'transparent';}
export interface RenderSource {readonly device:unknown;readonly buffer:unknown;readonly layout:'mac'|'detail';readonly cells:readonly number[];readonly extent:readonly number[];readonly origin:readonly number[];readonly epoch?:object;readonly tick?:number;}
export declare function packVolumeView(source:RenderSource,view:VolumeView):ArrayBuffer;
export declare class GpuVolumeRenderer {private constructor();static create(simulation:GpuSimulation,options?:{format?:string;shaderURL?:URL|string;enableSceneDepth?:boolean}):Promise<GpuVolumeRenderer>;readonly format:string;readonly closed:boolean;readonly draws:number;render(view:unknown,options:VolumeView|SceneDepthView):void;dispose():void;}
