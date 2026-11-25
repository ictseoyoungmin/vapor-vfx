import type {FloatVolume} from './gpu-field.mjs';
export interface BakedField extends FloatVolume {time:number;model:'baked-float32-vpf1'}
export function fieldCRC32(bytes:Uint8Array):number;
export function encodeFieldAsset(volume:FloatVolume,time?:number):Uint8Array;
export function decodeFieldAsset(input:ArrayBuffer|Uint8Array):BakedField;
