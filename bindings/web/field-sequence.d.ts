import type {FloatVolume,GpuFieldVolume} from './gpu-field.mjs';
export interface SequenceIndex {readonly cells:readonly number[];readonly extent:readonly number[];readonly densityCap:number;readonly records:readonly {readonly time:number;readonly byteLength:number;readonly crc:number}[]}
export interface SequenceField extends FloatVolume {time:number;model:'baked-float32-vpa1'}
export function frameFilename(i:number):string;
export function decodeSequenceIndex(input:ArrayBuffer|Uint8Array):SequenceIndex;
export class FieldSequence {constructor(index:ArrayBuffer|Uint8Array,loadFrame:(i:number,n:number)=>Promise<ArrayBuffer|Uint8Array>|ArrayBuffer|Uint8Array);readonly index:SequenceIndex;readonly cachedFrames:number;readonly closed:boolean;readonly startTime:number;readonly endTime:number;sample(time:number):Promise<SequenceField>;clear():void;dispose():void;}
export function openFieldSequence(indexUrl:string|URL,options?:{signal?:AbortSignal}):Promise<FieldSequence>;
export class GpuSequencePlayer {constructor(device:unknown,sequence:FieldSequence,options?:{origin?:readonly number[]});readonly time:number|null;readonly source:GpuFieldVolume|null;seek(time:number):Promise<GpuFieldVolume>;dispose():void;}
