"""Game-friendly effect API. Fluid = Rust backend, procedural = Rust CPU atlas.
Importing and resolving presets do not require a native library.
"""
from __future__ import annotations
import ctypes as C
import json,math,re,copy
from pathlib import Path
from . import Simulation, _Library, Config, U, F, D, _set, _u32
_CATALOG=json.loads(Path(__file__).with_name('presets.json').read_text())
def _snake(s):return re.sub(r'[A-Z]',lambda m:'_'+m[0].lower(),s)
def _options(d):return {_snake(k):v for k,v in d.items()}
def get_preset(key,quality='medium'):
    p=next((p for p in _CATALOG['presets'] if key==p['key'] or type(key) is int and key==p['id']),None)
    if p is None or quality not in _CATALOG['quality']:raise ValueError('unknown effect or quality')
    p=copy.deepcopy(p);q=_CATALOG['quality'][quality];p['config']['cells']=[int(n*q['scale']) for n in p['config']['cells']];p['config']['cellSize']/=q['scale'];p['config']['pressureIterations']=q['pressureIterations'];p.update(quality=quality,raySteps=q['steps'],uploadHz=q['uploadHz'] if p['kind']=='fluid' else q['proceduralUploadHz']);return p
def _validate_material(m):
    bounds={'extinction':(0,1000),'anisotropy':(-.9,.9),'albedo':(0,1),'emission':(0,10),'thermalFade':(0,1),'ambient':(0,1)}
    if set(m)!=set(bounds)|{'colour'} or len(m['colour'])!=3 or any(not math.isfinite(x) or not 0<=x<=1 for x in m['colour']):raise ValueError('invalid material')
    for k,(lo,hi) in bounds.items():
        if not math.isfinite(m[k]) or not lo<=m[k]<=hi:raise ValueError('invalid material '+k)
class _Procedural(C.Structure):
    _fields_=[('size',U),('version',U),('kind',U),('seed',U),('coverage',F),('humidity',F),('erosion',F),('wind',F*3)]
class Effect:
    """One local domain. Call play(), advance(), atlas_rgba8(). Use context manager.
    Stopping a fluid source leaves its density to dissipate. No GPU fallback for procedural effects.
    """
    def __init__(self,key,*,quality='medium',backend='cpu',library=None,config=None,procedural=None,emitter=None,material=None,**execution):
        self.definition=get_preset(key,quality);self.definition['material'].update(material or {});_validate_material(self.definition['material']);self._sim=None;self.closed=False;self.playing=False;self.paused=False;self.time=0.;self._cached=None
        self.emitter=_options(self.definition['emitter']);self.emitter.update(_options(emitter or {}));self.emitter['enabled']=int(bool(self.emitter['enabled']))
        self.config=_options(self.definition['config']);self.config.update(_options(config or {}));self.settings=copy.deepcopy(self.definition['procedural']);self.backend=backend
        if self.definition['kind']=='fluid':
            if procedural:raise ValueError('procedural options not valid for fluid')
            self._sim=Simulation(library=library,backend=backend,**self.config,**execution);self.backend_info=self._sim.backend_info;self.backend={1:"cpu",2:"gpu",3:"hybrid"}[self.backend_info["active"]];self.render_shape=self._sim.render_shape
        else:
            if backend not in ('cpu','auto') or execution:raise ValueError('procedural effects use explicit CPU generation, no GPU/hybrid options')
            if set(procedural or {})-set(self.settings):raise ValueError("unknown procedural options")
            self.settings.update(procedural or {});self._lib=_Library(library);self._native_cfg=Config();self._lib.check(self._lib.default_config(C.byref(self._native_cfg),C.sizeof(self._native_cfg)))
            c=self.config.copy();cells=c.pop('cells');c.update(zip(('nx','ny','nz'),cells));_set(self._native_cfg,c)
            dims=[self._native_cfg.nx,self._native_cfg.ny,self._native_cfg.nz]
            if any(not 4<=n<=192 for n in dims) or math.prod(n+1 for n in dims)>2097152:raise ValueError('grid exceeds bounds')
            self.render_shape=tuple(reversed(dims));self.backend='procedural-cpu';self.backend_info={'active':'procedural-cpu','render_cells':dims}
            fn=self._lib.dll.vapor_procedural_atlas_v1;fn.argtypes=[C.POINTER(Config),C.POINTER(_Procedural),D,C.POINTER(C.c_uint8),U];fn.restype=C.c_int32;self._generate=fn
            self._cache_size=math.prod(dims)*4;self._buffer=(C.c_uint8*self._cache_size)();self.atlas_rgba8()
    def _check(self):
        if self.closed:raise RuntimeError('effect closed')
    @property
    def runtime(self):return self._sim
    def play(self):
        self._check()
        if self._sim:
            self._sim.set_emitter(0,**self.emitter)
            try:
                p=self.definition['profile'];self._sim.set_profile(0,p['points'] if p else None,duration=p['duration'] if p else 2,start_time=self.time)
            except BaseException:
                self._sim.remove_emitter(0);self.playing=False;raise
        self.playing=True;return self
    def stop(self):
        self._check()
        if self._sim:self._sim.remove_emitter(0)
        self.playing=False
    def reset(self):
        self.stop()
        if self._sim:self._sim.reset()
        self.time=0.;self._cached=None
    def set_pose(self,position,direction=None):
        self._check()
        if not self._sim:raise ValueError('move procedural volume with host transform')
        e=dict(self.emitter,position=list(position),direction=list(direction) if direction is not None else self.emitter['direction'])
        if any(len(e[k])!=3 or not all(math.isfinite(v) for v in e[k]) for k in ('position','direction')) or math.hypot(*e['direction'])<1e-6:raise ValueError('invalid pose')
        if self.playing:self._sim.set_emitter(0,**e)
        self.emitter=e
    def set_wind(self,wind):
        self._check()
        if self._sim:raise ValueError('fluid wind is immutable; pass config at creation')
        w=list(wind);extent=[self._native_cfg.nx*self._native_cfg.cell_size,self._native_cfg.ny*self._native_cfg.cell_size,self._native_cfg.nz*self._native_cfg.cell_size]
        if len(w)!=3 or any(not math.isfinite(v) or abs(v)>100 or abs(v)/extent[i]>100 for i,v in enumerate(w)):raise ValueError('invalid wind')
        self.settings['wind']=w;self._cached=None
    def advance(self,seconds):
        self._check()
        if not math.isfinite(seconds) or not 0<=seconds<=10:raise ValueError('advance requires 0..10 s')
        if self.paused or seconds==0:return None
        if self._sim:
            r=self._sim.advance(seconds);self.time=r['simulated_seconds'];return r
        if self.playing:
            if self.time+seconds>1e7:raise ValueError('procedural time limit reached; reset')
            self.time+=seconds;self._cached=None
        return None
    def atlas_rgba8(self):
        self._check()
        if self._sim:return self._sim.atlas_rgba8()
        if self._cached is None:
            s=_Procedural();s.size=C.sizeof(s);s.version=1;s.kind=1 if self.definition['kind']=='cloud' else 2;_set(s,self.settings)
            self._lib.check(self._generate(C.byref(self._native_cfg),C.byref(s),self.time,self._buffer,len(self._buffer)));self._cached=bytes(self._buffer)
        return self._cached
    def close(self):
        if self.closed:return
        self.closed=True;self._cached=None
        if self._sim:self._sim.close()
    def __enter__(self):self._check();return self
    def __exit__(self,*_):self.close()
    def __del__(self):
        try:self.close()
        except Exception:pass

def create_effect(key,**options):return Effect(key,**options)

def create_effect_from_recipe(recipe,**execution):
    if isinstance(recipe,str):recipe=json.loads(recipe)
    if not isinstance(recipe,dict) or recipe.get('schema')!='vapor.effect-recipe/1' or set(recipe)-{'schema','preset','quality','config','emitter','procedural','material'}:raise ValueError('invalid recipe')
    return Effect(recipe['preset'],**{k:recipe[k] for k in ('quality','config','emitter','procedural','material') if k in recipe},**execution)

def ember_visual(time,lit=True,progress=0.):
    if not math.isfinite(time) or not 0<=time<=1e7 or not math.isfinite(progress) or not 0<=progress<=1 or type(lit) is not bool:raise ValueError('invalid ember animation input')
    heat=.72+.08*math.sin(time*2.9)+.045*math.sin(time*7.3) if lit else 0.
    return dict(heat=heat,colour=[1.,.24+.22*heat,.035+.05*heat],intensity=heat*3.2,ash_fraction=progress)
