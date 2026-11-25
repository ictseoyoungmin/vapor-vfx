/** Shared GPU wire contract, not a JavaScript fluid solver. */
export const MODES=Object.freeze({auto:0,cpu:1,gpu:2,hybrid:3});
export class BackendError extends Error {constructor(code,message){super(message);this.name='VaporBackendError';this.code=code;}}
const defaults={cells:[24,32,24],cellSize:.025,origin:[0,0,0],fixedDt:1/60,maxSubsteps:4,pressureIterations:32,sorOmega:1.7,densityDecay:.35,cooling:1,buoyancy:.8,densityWeight:.02,drag:.08,vorticity:.15,wind:[0,0,0],maxVelocity:12,densityCap:8,boundary:0};
function fail(message){throw new BackendError(-1,message);}
function finite(v,key){if(typeof v!=='number'||!Number.isFinite(v))fail(`${key} must be finite`);return v;}
function range(v,lo,hi,key){finite(v,key);if(v<lo||v>hi)fail(`${key} must be ${lo}..${hi}`);return v;}
function vec(v,key){if(!v||v.length!==3)fail(`${key} must contain 3 numbers`);return Array.from(v,x=>Math.fround(finite(x,key)));}
function id(v){if(!Number.isInteger(v)||v<0||v>=32)fail('id must be 0..31');return v;}
export function normalizeConfig(options={}){
    const c={...defaults,...options};
    for(const k of Object.keys(options))if(!Object.hasOwn(defaults,k)&&!['nx','ny','nz'].includes(k))fail(`Unknown option: ${k}`);
    c.cells=[...c.cells];for(const [i,key]of ['nx','ny','nz'].entries())if(options[key]!==undefined)c.cells[i]=options[key];
    if(c.cells.length!==3||c.cells.some(n=>!Number.isInteger(n)||n<4||n>192))fail('grid axes must be integers in 4..192');
    c.paddedCount=c.cells.reduce((a,n)=>a*(n+1),1);c.voxelCount=c.cells.reduce((a,n)=>a*n,1);
    if(c.paddedCount>2097152)throw new BackendError(-4,'MAC grid exceeds cell budget');
    for(const k of Object.keys(defaults))if(typeof defaults[k]==='number'&&!['maxSubsteps','pressureIterations','boundary'].includes(k))c[k]=Math.fround(finite(c[k],k));
    c.origin=vec(c.origin,'origin');c.wind=vec(c.wind,'wind');if(c.origin.some(x=>Math.abs(x)>1e6))fail('origin out of range');
    range(c.cellSize,Math.fround(.001),10,'cellSize');range(c.fixedDt,Math.fround(.001),Math.fround(.1),'fixedDt');
    for(const [key,lo,hi]of [['maxSubsteps',1,64],['pressureIterations',1,256],['boundary',0,1]]){range(c[key],lo,hi,key);if(!Number.isInteger(c[key]))fail(`${key} must be integer`);}
    range(c.sorOmega,Math.fround(.1),Math.fround(1.99),'sorOmega');if(c.sorOmega>=Math.fround(1.99))fail('sorOmega must be <1.99');
    for(const k of ['densityDecay','cooling','densityWeight','drag','vorticity'])range(c[k],0,100,k);
    range(c.buoyancy,-100,100,'buoyancy');range(c.maxVelocity,Math.fround(.01),100,'maxVelocity');range(c.densityCap,Math.fround(.01),100,'densityCap');
    if(Math.hypot(...c.wind)>c.maxVelocity)fail('wind exceeds maxVelocity');
    if(c.maxVelocity*Math.sqrt(3)*c.fixedDt/c.cellSize>32)fail('maximum vector CFL exceeds 32');
    [c.nx,c.ny,c.nz]=c.cells;
    Object.freeze(c.cells);Object.freeze(c.origin);Object.freeze(c.wind);return Object.freeze(c);
}
export function normalizeExecution(c,options={}){
    const allowed=new Set(['backend','detailScale','allowCpuFallback','allowSoftwareGpu',
        'detailTurbulence','detailFrequency','readbackTimeoutMs','wasmURL','shaderURL','module','device']);
    for(const key of Object.keys(options))if(!allowed.has(key))fail(`Unknown execution option: ${key}`);
    const o={backend:'cpu',detailScale:1,allowCpuFallback:false,allowSoftwareGpu:false,detailTurbulence:0,detailFrequency:8,readbackTimeoutMs:15000,...options};
    if(!Object.hasOwn(MODES,o.backend))fail('unknown backend');
    range(o.readbackTimeoutMs,1,120000,'readbackTimeoutMs');
    if(!Number.isInteger(o.detailScale)||o.detailScale<1||o.detailScale>4)fail('detailScale must be 1..4');
    for(const k of ['allowCpuFallback','allowSoftwareGpu'])if(typeof o[k]!=='boolean')fail(`${k} must be boolean`);
    range(o.detailTurbulence,0,2,'detailTurbulence');range(o.detailFrequency,.1,100,'detailFrequency');
    if(o.backend==='cpu'&&(o.detailScale!==1||o.detailTurbulence!==0))fail('CPU mode cannot apply GPU detail');
    if(['gpu','auto'].includes(o.backend)&&o.detailScale===1&&o.detailTurbulence!==0)fail('GPU detail turbulence needs detailScale > 1');
    if(c.voxelCount*o.detailScale**3>2097152)throw new BackendError(-4,'detail grid exceeds cell budget');
    if(Math.sqrt(3)*(c.maxVelocity+2*o.detailTurbulence)*c.fixedDt/c.cellSize*o.detailScale>128)fail('detail collision traversal budget exceeded');
    if((o.backend==='cpu'?c.paddedCount*112:c.paddedCount*336+c.voxelCount*o.detailScale**3*60+8192)>512*1024*1024)throw new BackendError(-4,'backend memory budget exceeded');
    return Object.freeze(o);
}
export function packParameters(c,o,time=0){
    const b=new ArrayBuffer(128),v=new DataView(b);let off=0;
    const u=n=>{v.setUint32(off,n,true);off+=4;},f=n=>{v.setFloat32(off,n,true);off+=4;};
    [...c.cells,c.paddedCount].forEach(u);[...c.origin,c.cellSize,c.fixedDt,c.densityDecay,c.cooling,c.buoyancy,c.densityWeight,c.drag,c.vorticity,c.maxVelocity,...c.wind,c.densityCap,c.sorOmega,o.detailTurbulence,time%16,o.detailFrequency].forEach(f);
    [32,32,c.boundary,0,o.detailScale,...c.cells.map(n=>n*o.detailScale)].forEach(u);return b;
}
function curve(points){
    const d=points.slice(1).map((p,i)=>(p[1]-points[i][1])/Math.max(p[0]-points[i][0],1e-6));const n=points.length,m=new Array(n).fill(0);m[0]=d[0];m[n-1]=d[n-2];
    for(let i=1;i<n-1;i++)m[i]=d[i-1]*d[i]<=0?0:(d[i-1]+d[i])/2;
    for(let i=0;i<n-1;i++){if(Math.abs(d[i])<1e-9){m[i]=m[i+1]=0;continue;}const a=m[i]/d[i],b=m[i+1]/d[i],s=a*a+b*b;if(s>9){const t=3/Math.sqrt(s);m[i]=t*a*d[i];m[i+1]=t*b*d[i];}}
    return x=>{if(x<=0)return points[0][1];if(x>=1)return points[n-1][1];let i=0;while(i<n-2&&x>points[i+1][0])i++;const h=Math.max(points[i+1][0]-points[i][0],1e-6),t=(x-points[i][0])/h,t2=t*t,t3=t2*t;return (2*t3-3*t2+1)*points[i][1]+(t3-2*t2+t)*h*m[i]+(-2*t3+3*t2)*points[i+1][1]+(t3-t2)*h*m[i+1];};
}
export class Scene {
    constructor(config){this.config=config;this.emitters=Array(32).fill(null);this.profiles=Array(32).fill(null);this.obstacles=Array(32).fill(null);}
    clone(){const s=new Scene(this.config);s.emitters=this.emitters.slice();s.profiles=this.profiles.slice();s.obstacles=this.obstacles.slice();return s;}
    setEmitter(slot,options={}){
        id(slot);const e={position:[.3,.15,.3],direction:[0,1,0],radius:.045,length:.08,speed:1,densityRate:8,temperature:1,enabled:true,...options};
        for(const k of Object.keys(options))if(!['position','direction','radius','length','speed','densityRate','temperature','enabled'].includes(k))fail(`unknown emitter option ${k}`);
        e.position=vec(e.position,'position');e.direction=vec(e.direction,'direction');let norm=Math.hypot(...e.direction);
        if(e.position.some(v=>Math.abs(v)>1e6)||!Number.isFinite(norm)||norm<1e-6)fail('invalid emitter position/direction');
        e.direction=e.direction.map(v=>Math.fround(v/norm));
        for(const k of ['radius','length','speed','densityRate','temperature'])e[k]=Math.fround(range(e[k],0,1000,k));
        if(e.radius<=0||e.speed>this.config.maxVelocity||typeof e.enabled!=='boolean')fail('invalid emitter radius/speed/enabled');
        this.emitters[slot]=Object.freeze(e);
    }
    removeEmitter(slot){id(slot);this.emitters[slot]=this.profiles[slot]=null;}
    setProfile(slot,points,options={}){
        id(slot);if(!this.emitters[slot])fail('emitter not found');if(points==null||points.length===0){this.profiles[slot]=null;return;}
        const {duration=2,startTime=0,repeat=false}=options;range(duration,.4,8,'duration');finite(startTime,'startTime');if(typeof repeat!=='boolean')fail('repeat must be boolean');
        if(!Array.isArray(points)||points.length<2||points.length>64)fail('profile needs 2..64 rows');
        const rows=points.map(r=>{if(!Array.isArray(r)||r.length!==4)fail('profile row must have four values');r=r.slice();r.forEach(v=>finite(v,'profile'));range(r[1],0,16,'speed multiplier');range(r[2],0,1,'amount');range(r[3],0,16,'density multiplier');return r;}).sort((a,b)=>a[0]-b[0]);
        if(rows[0][0]!==0||rows.at(-1)[0]!==1||rows.some((r,i)=>i&&r[0]<=rows[i-1][0]))fail('profile x values must be unique with endpoints 0 and 1');
        this.profiles[slot]={duration,startTime,repeat,curves:[1,2,3].map(ch=>curve(rows.map(r=>[r[0],r[ch]])))};
    }
    setCapsule(slot,a,b,radius,velocity=[0,0,0]){this._obstacle(slot,0,a,b,range(radius,Number.MIN_VALUE,1000,'radius'),velocity);}
    setSphere(slot,center,radius,velocity=[0,0,0]){this.setCapsule(slot,center,center,radius,velocity);}
    setBox(slot,a,b,velocity=[0,0,0]){this._obstacle(slot,1,a,b,0,velocity);}
    _obstacle(slot,kind,a,b,radius,velocity){
        id(slot);a=vec(a,'a');b=vec(b,'b');velocity=vec(velocity,'velocity');
        if((kind===0&&Math.fround(radius)<=0)||[...a,...b].some(v=>Math.abs(v)>1e6)||Math.hypot(...velocity)>this.config.maxVelocity||(kind===1&&a.some((v,i)=>v>=b[i])))fail('invalid obstacle geometry/velocity');
        this.obstacles[slot]={a,b,radius:Math.fround(radius),kind,velocity};
    }
    removeObstacle(slot){id(slot);this.obstacles[slot]=null;}
    pack(time){
        finite(time,'time');const buffer=new ArrayBuffer(3072),view=new DataView(buffer);let off=0;
        const write=values=>{for(const v of values){view.setFloat32(off,v,true);off+=4;}};
        for(let i=0;i<32;i++){
            const e=this.emitters[i];if(!e){off+=48;continue;}let speed=e.speed,density=e.densityRate,enabled=e.enabled;const p=this.profiles[i];
            if(p){let age=time-p.startTime;if(age<0||(!p.repeat&&age>=p.duration))enabled=false;else{if(p.repeat)age=((age%p.duration)+p.duration)%p.duration;const x=Math.max(0,Math.min(1,age/p.duration));speed=Math.fround(speed*Math.fround(p.curves[0](x)));density=Math.fround(density*Math.fround(Math.max(0,Math.min(1,p.curves[1](x)))*Math.max(0,p.curves[2](x))));}}
            if(speed>this.config.maxVelocity||density>1e6||!Number.isFinite(speed)||!Number.isFinite(density))fail('evaluated profile exceeds limits');
            write([...e.position,e.radius,...e.direction,e.length,speed,density,e.temperature,enabled?1:0]);
        }
        for(const o of this.obstacles){if(!o){off+=48;continue;}write([...o.a,o.radius,...o.b,o.kind,...o.velocity,1]);}
        return buffer;
    }
}
export function planClock(clock,elapsed,cfg){
    range(elapsed,0,3600,'elapsed');const dt=cfg.fixedDt,total=clock.accumulator+elapsed,wanted=Math.floor((total+dt*1e-7)/dt);
    return {steps:Math.min(wanted,cfg.maxSubsteps),residual:Math.max(0,Math.min(dt,total-wanted*dt)),dropped:Math.max(0,wanted-cfg.maxSubsteps)*dt};
}
