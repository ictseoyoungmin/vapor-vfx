import type {ConfigOptions,EmitterOptions,Vec3,AdvanceReport} from './vapor.mjs';
import type {ExecutionOptions,CpuSimulation,GpuSimulation} from './gpu.mjs';
export type EffectKey='cigarette_smoke'|'exhaled_aerosol'|'cumulus_cloud'|'ground_fog'|'steam'|'smoke'|'dust'|'flame';
export type Quality='low'|'medium'|'high';
export interface Material {colour:Vec3;extinction:number;anisotropy:number;albedo:number;emission:number;thermalFade:number;ambient:number;}
export interface ProceduralSettings {seed:number;coverage:number;humidity:number;erosion:number;wind:Vec3;}
export interface EffectDefinition {id:number;key:EffectKey;label:string;kind:'fluid'|'cloud'|'fog';config:ConfigOptions & {cells:Vec3;cellSize:number;densityCap:number};emitter:EmitterOptions;material:Material;procedural:ProceduralSettings|null;profile:{duration:number;points:readonly (readonly [number,number,number,number])[]}|null;ember:boolean;quality:Quality;raySteps:number;uploadHz:number;}
export interface EffectOptions {quality?:Quality;execution?:ExecutionOptions;config?:ConfigOptions;procedural?:Partial<ProceduralSettings>;emitter?:EmitterOptions;material?:Partial<Material>;}
export declare const effectCatalog:Readonly<{schema:string;presets:readonly Omit<EffectDefinition,'quality'|'raySteps'|'uploadHz'>[];quality:Readonly<Record<Quality,{scale:number;pressureIterations:number;steps:number;uploadHz:number;proceduralUploadHz:number}>>}>;
export declare function getPreset(key:EffectKey|number,quality?:Quality):EffectDefinition;
/** Opt-in experimental 0.15 fine-curl settings; backend must be GPU or Hybrid. */
export declare function getDetailExecution(key:EffectKey|number,quality?:Quality,backend?:'gpu'|'hybrid'):Readonly<Required<Pick<ExecutionOptions,'backend'|'detailScale'|'detailTurbulence'|'detailFrequency'>>>;
export declare function lodFor(distance:number,extent:Vec3,quality?:Quality,procedural?:boolean):Readonly<{visible:boolean;steps:number;uploadHz:number}>;
export declare function emberVisual(time:number,lit?:boolean,progress?:number):{heat:number;colour:number[];intensity:number;ashFraction:number};
export declare class Effect {
 private constructor();readonly definition:EffectDefinition;readonly simulation:CpuSimulation|GpuSimulation|null;readonly config:Readonly<Required<ConfigOptions>>;readonly backend:'cpu'|'gpu'|'hybrid'|'procedural-cpu';readonly renderCells:readonly number[];readonly extent:number[];readonly playing:boolean;readonly time:number;readonly closed:boolean;readonly revision:number;paused:boolean;
 setPose(position:Vec3,direction?:Vec3):void;play():this;stop():void;reset():void;setWind(wind:Vec3):void;advance(seconds:number):AdvanceReport|null;atlasRGBA8():Promise<Uint8Array>;dispose():void;
}
export declare function createEffect(key:EffectKey|number,options?:EffectOptions):Promise<Effect>;
export declare function createEffectFromRecipe(recipe:string|object,execution?:ExecutionOptions):Promise<Effect>;
export declare class EffectsWorld {constructor(options?:{maxEffects?:number;maxBytes?:number;execution?:ExecutionOptions});readonly bytes:number;readonly closed:boolean;createEffect(key:EffectKey|number,options?:EffectOptions):Promise<Effect>;remove(effect:Effect):void;advance(seconds:number):void;dispose():void;}
