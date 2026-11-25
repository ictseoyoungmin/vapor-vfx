import type {Material} from './effects.mjs';
export type PreviewVector=readonly [number,number,number]|readonly number[];
export interface FloatVolumeFields {density:Float32Array;temperature:Float32Array;}
export type VolumeOptions = ({atlas:Uint8Array;fields?:never}|{fields:FloatVolumeFields;atlas?:never}) & {cells:PreviewVector;extent:PreviewVector;densityCap:number;material:Material;light?:PreviewVector;shadowSteps?:number;};
/** Top-left, x-fastest pixels. Depth is distance along the normalized camera ray in metres; zero means no hit. Colour is opaque sRGB. */
export interface PreviewScene {depth:Float32Array;colour:Uint8Array;}
export interface PreviewCamera {eye:PreviewVector;target:PreviewVector;width?:number;height?:number;steps?:number;background?:'sky'|'ground'|'dark';jitter?:number;scene?:PreviewScene;}
export interface TemporalCamera extends Omit<PreviewCamera,'scene'> {volumeOrigin?:PreviewVector;scene?:never;}
/** Opaque immutable frame; rgba getter returns a detached image copy. */
export interface PreviewFrame {readonly width:number;readonly height:number;readonly rgba:Uint8Array;}
export interface PreparedVolume {render(options:PreviewCamera):Uint8Array;renderFrame(options:TemporalCamera):PreviewFrame;transmittanceAt(position:PreviewVector):number;}
export interface ReprojectionDiagnostics {readonly resetReason:'initial'|'identity'|'snapshot'|'resolution'|'background'|'camera-cut'|'disabled'|null;readonly visiblePixels:number;readonly acceptedPixels:number;readonly rejectedPixels:number;readonly historyFraction:number;readonly meanHistoryWeight:number;readonly maxHistorySamples:number;}
export declare function hgPhase(g:number,cosTheta:number):number;
export declare function prepareVolume(options:VolumeOptions):PreparedVolume;
export declare function renderVolume(options:VolumeOptions & PreviewCamera):Uint8Array;
export declare class TemporalPreview {constructor(maxFrames?:number);readonly frames:number;reset():void;accumulate(key:string,rgba:Uint8Array):Uint8Array;}
export declare class ReprojectedPreview {constructor(maxFrames?:number);readonly maxFrames:number;reset():void;accumulate(key:string,frame:PreviewFrame):{rgba:Uint8Array;diagnostics:ReprojectionDiagnostics};}
