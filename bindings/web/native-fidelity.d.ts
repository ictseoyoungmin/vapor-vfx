import type {VaporModule,Vec3} from './vapor.mjs';
import type {FidelityFields,FidelityCamera} from './fidelity.mjs';
export type NativeFidelityVolume={cells:Vec3;extent:Vec3;densityCap:number;fields:FidelityFields;key?:string;model?:'rust-wasm-fidelity'};
export type NativeFidelitySettings=Partial<{colour:Vec3;extinction:number;anisotropy:number;albedo:number;emission:number;thermalFade:number;ambient:number;direction:Vec3;radiance:Vec3;sky:Vec3;ground:Vec3;multiScatter:number;shadowSteps:number;lightScale:number}>;
export class NativeFidelityCPU {
 constructor(module:VaporModule);
 generate(key:'cumulus_cloud'|'ground_fog'|'dust',options?:{quality?:'low'|'medium'|'high';cells?:Vec3;extent?:Vec3;settings?:Partial<{seed:number;coverage:number;humidity:number;erosion:number;wind:Vec3}>;time?:number;terrain?:Float32Array}):NativeFidelityVolume;
 render(volume:NativeFidelityVolume,camera:Omit<FidelityCamera,'skipEmpty'>,settings?:NativeFidelitySettings):{rgba:Uint8Array;alpha:Float32Array;width:number;height:number;model:'rust-wasm-fidelity'};
}
