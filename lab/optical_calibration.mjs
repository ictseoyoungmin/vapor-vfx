/** Authoring calibration, not measured aerosol microphysics. A fixed opacity target
 * on an explicitly chosen anchor field determines extinction using Beer-Lambert.
 * Never changes the density field or automatically retunes on subsequent frames. */
export function extinctionForTransmission(pathDensity,transmission){
 if(!Number.isFinite(pathDensity)||pathDensity<=0||!Number.isFinite(transmission)||transmission<=0||transmission>=1)throw new RangeError('positive path density and transmission in (0,1) required');
 const value=-Math.log(transmission)/pathDensity;if(!Number.isFinite(value)||value>1000)throw new RangeError('calibration outside material extinction budget');return value;
}
export function fitOpacityFromProbe(alpha,{probeExtinction=1,quantile=.95,targetOpacity=.55,minAlpha=1e-7}={}){
 if(!(alpha instanceof Float32Array)||!Number.isFinite(probeExtinction)||probeExtinction<=0||!Number.isFinite(quantile)||quantile<0||quantile>1||!Number.isFinite(targetOpacity)||targetOpacity<=0||targetOpacity>=1||!Number.isFinite(minAlpha)||minAlpha<=0||minAlpha>=1)throw new RangeError('invalid opacity calibration');
 const samples=[];for(const a of alpha){if(!Number.isFinite(a)||a<0||a>1)throw new RangeError('invalid probe alpha');if(a>=minAlpha)samples.push(a);}
 if(!samples.length)throw new RangeError('empty opacity probe');samples.sort((a,b)=>a-b);const a=samples[Math.floor(quantile*(samples.length-1))];
 // Near-opaque probes may be truncated by ray termination, so do not fit them.
 if(a>=.99)throw new RangeError('saturated probe; reduce probe extinction');
 const path=-Math.log1p(-a)/probeExtinction;return {extinction:extinctionForTransmission(path,1-targetOpacity),probeExtinction,quantile,targetOpacity,minAlpha,pathDensity:path,probeAlpha:a,sampleCount:samples.length};
}
