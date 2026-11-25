"""Opt-in native Fidelity CPU path. This module never falls back to JS/Python simulation.
Native ABI is experimental; returns caller-owned Float32 arrays (x-fastest).
"""
from __future__ import annotations
import ctypes as C, math
from dataclasses import dataclass
from . import _Library,U,D,F,_set
from .effects import get_preset

class _Grid(C.Structure):
    _fields_=[('size',U),('version',U),('cells',U*3),('reserved',U),('extent',D*3),('density_cap',D)]
class _Density(C.Structure):
    _fields_=[('size',U),('version',U),('kind',U),('seed',U),('coverage',D),('humidity',D),('erosion',D),('wind',D*3)]
class _Optics(C.Structure):
    _fields_=[('size',U),('version',U),('shadow_steps',U),('reserved',U),('colour',D*3),('extinction',D),('anisotropy',D),('albedo',D),('emission',D),('thermal_fade',D),('ambient',D),('direction',D*3),('radiance',D*3),('sky',D*3),('ground',D*3),('multi_scatter',D),('light_scale',D)]
class _Camera(C.Structure):
    _fields_=[('size',U),('version',U),('width',U),('height',U),('steps',U),('dark',U),('eye',D*3),('target',D*3),('fov',D),('exposure',D),('jitter',D)]

def _struct(cls,**values):
    obj=cls();obj.size=C.sizeof(cls);obj.version=1;_set(obj,values);return obj

def _grid(cells,extent,cap):
    cells=tuple(cells);extent=tuple(extent)
    if len(cells)!=3 or any(type(v) is not int or not 4<=v<=512 for v in cells) or math.prod(cells)>2097152:raise ValueError('invalid fidelity cells')
    if len(extent)!=3 or any(not math.isfinite(v) or not .0001<=v<=1e7 for v in extent) or not math.isfinite(cap) or not .00001<=cap<=100:raise ValueError('invalid extent or cap')
    return _struct(_Grid,cells=cells,extent=extent,density_cap=cap)

@dataclass(frozen=True)
class Fields:
    cells:tuple
    extent:tuple
    density_cap:float
    density:object
    temperature:object

class FidelityCPU:
    """The stateless C ABI recomputes the cache for every render; Rust API can reuse it."""
    def __init__(self,library=None):
        self._lib=_Library(library);dll=self._lib.dll;P=C.POINTER(F)
        self._generate=dll.vapor_fidelity_generate_v1;self._generate.argtypes=[C.POINTER(_Grid),C.POINTER(_Density),D,P,U,P,P,U];self._generate.restype=C.c_int32
        self._render=dll.vapor_fidelity_render_v1;self._render.argtypes=[C.POINTER(_Grid),C.POINTER(_Optics),C.POINTER(_Camera),P,P,U,P,P,U,C.POINTER(C.c_uint8),U,P,U];self._render.restype=C.c_int32
    def generate(self,key,*,quality='high',cells=None,extent=None,settings=None,time=0.,terrain=None):
        p=get_preset(key,quality);kind={'cumulus_cloud':1,'ground_fog':2,'dust':3}.get(p['key'])
        if kind is None:raise ValueError('fluid requires actual simulation fields')
        cfg=p['config'];g=_grid(cfg['cells'] if cells is None else cells,[n*cfg['cellSize'] for n in cfg['cells']] if extent is None else extent,cfg['densityCap'])
        values=dict(p['procedural']);values.update(settings or {});s=_struct(_Density,kind=kind,**values)
        n=math.prod(g.cells);d=(F*n)();t=(F*n)();height=None
        if terrain is not None:
            count=g.cells[0]*g.cells[2]
            if kind==1 or len(terrain)!=count:raise ValueError('invalid terrain size/kind')
            height=(F*count)(*terrain)
        self._lib.check(self._generate(C.byref(g),C.byref(s),time,height,0 if height is None else len(height),d,t,n))
        return Fields(tuple(g.cells),tuple(g.extent),g.density_cap,d,t)
    def render(self,fields,*,eye,target,width=640,height=400,steps=128,fov=40.,exposure=1.,jitter=.5,dark=False,material=None,lighting=None,depth=None,radiance=None):
        g=_grid(fields.cells,fields.extent,fields.density_cap);n=math.prod(g.cells)
        if type(width) is not int or type(height) is not int or type(steps) is not int or not 1<=width<=1600 or not 1<=height<=1600 or not 8<=steps<=512 or width*height*steps>180_000_000:raise ValueError('invalid render budget')
        if len(fields.density)!=n or len(fields.temperature)!=n:raise ValueError('invalid field size')
        d=fields.density if isinstance(fields.density,F*n) else (F*n)(*fields.density);t=fields.temperature if isinstance(fields.temperature,F*n) else (F*n)(*fields.temperature)
        values=dict(colour=[.91,.96,1.],extinction=.32,anisotropy=.55,albedo=.9,emission=0.,thermal_fade=0.,ambient=.1,direction=[-.8,.56,.16],radiance=[2.6,2.45,2.2],sky=[.07,.105,.18],ground=[.035,.04,.05],multi_scatter=.29,shadow_steps=24,light_scale=.5)
        values.update(material or {});values.update(lighting or {});o=_struct(_Optics,**values)
        c=_struct(_Camera,eye=eye,target=target,width=width,height=height,steps=steps,fov=fov,exposure=exposure,jitter=jitter,dark=int(dark))
        p=width*height;z=rgb=None
        if depth is not None or radiance is not None:
            if depth is None or radiance is None or len(depth)!=p or len(radiance)!=3*p:raise ValueError('invalid scene arrays')
            z=(F*p)(*depth);rgb=(F*(p*3))(*radiance)
        rgba=(C.c_uint8*(4*p))();alpha=(F*p)()
        self._lib.check(self._render(C.byref(g),C.byref(o),C.byref(c),d,t,n,z,rgb,p if z is not None else 0,rgba,len(rgba),alpha,len(alpha)))
        return bytes(rgba),alpha
