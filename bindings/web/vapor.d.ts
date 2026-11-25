export type Vec3 = readonly [number,number,number];
export interface ConfigOptions {cells?:Vec3;nx?:number;ny?:number;nz?:number;cellSize?:number;origin?:Vec3;fixedDt?:number;maxSubsteps?:number;pressureIterations?:number;sorOmega?:number;densityDecay?:number;cooling?:number;buoyancy?:number;densityWeight?:number;drag?:number;vorticity?:number;wind?:Vec3;maxVelocity?:number;densityCap?:number;boundary?:0|1;}
export interface EmitterOptions {position?:Vec3;direction?:Vec3;radius?:number;length?:number;speed?:number;densityRate?:number;temperature?:number;enabled?:boolean;}
export interface RenderOptions {eye:Vec3;target:Vec3;up?:Vec3;width?:number;height?:number;steps?:number;extinction?:number;colour?:Vec3;verticalFovDegrees?:number;}
export interface AdvanceReport {steps:number;alpha:number;droppedSeconds:number;simulatedSeconds:number;}
export interface Metrics {ticks:number;time:number;densityIntegral:number;maxDensity:number;maxSpeed:number;divergenceRms:number;pressureResidualRms:number;centroid:number[];nonFinite:number;clampedVelocities:number;droppedSeconds:number;cpuBytes:number;}
export type FieldName='density'|'temperature'|'pressure'|'solid'|'velocity';
export declare const Fields:Readonly<Record<FieldName,number>>;
export declare class VaporError extends Error{code:number;constructor(code:number,message?:string);}
export declare class VaporModule{constructor(exports:WebAssembly.Exports);createSimulation(options?:ConfigOptions):Simulation;}
export declare function loadVapor(source?:string|URL|BufferSource):Promise<VaporModule>;
export declare class Simulation{
 constructor(module:VaporModule,options?:ConfigOptions);
 readonly config:Readonly<Required<ConfigOptions>>;readonly closed:boolean;
 step(steps?:number):void;advance(seconds:number):AdvanceReport;reset():void;dispose():void;
 setEmitter(id:number,options?:EmitterOptions):void;removeEmitter(id:number):void;
 setCapsule(id:number,a:Vec3,b:Vec3,radius:number,velocity?:Vec3):void;
 setSphere(id:number,center:Vec3,radius:number,velocity?:Vec3):void;
 setBox(id:number,minimum:Vec3,maximum:Vec3,velocity?:Vec3):void;removeObstacle(id:number):void;
 setProfile(id:number,points:readonly (readonly [number,number,number,number])[]|null,options?:{duration?:number;startTime?:number;repeat?:boolean}):void;
 renderRGBA8(options:RenderOptions):Uint8Array;
 macCells():Float32Array;metrics():Metrics;field(name?:FieldName):Float32Array;atlasRGBA8():Uint8Array;
}
