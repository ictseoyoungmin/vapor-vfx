"""Rust Vapor game runtime. Import is lazy; no NumPy or native library required until use.

    with Simulation(cells=(16,20,16), cell_size=.04) as sim:
        sim.set_emitter(0, position=(.32,.1,.32))
        sim.step(60)
        density = sim.field("density", numpy=True)
"""
from __future__ import annotations
import ctypes as C
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

class VaporError(RuntimeError):
    def __init__(self, code: int, message: str):
        self.code=code
        super().__init__(f"Vapor [{code}]: {message}")

U=C.c_uint32; F=C.c_float; D=C.c_double; Q=C.c_uint64
class Config(C.Structure):
    _fields_=[("size",U),("version",U),("nx",U),("ny",U),("nz",U),("cell_size",F),("origin",F*3),("fixed_dt",F),("max_substeps",U),("pressure_iterations",U),("sor_omega",F),("density_decay",F),("cooling",F),("buoyancy",F),("density_weight",F),("drag",F),("vorticity",F),("wind",F*3),("max_velocity",F),("density_cap",F),("boundary",U)]
class Emitter(C.Structure):
    _fields_=[("size",U),("version",U),("position",F*3),("direction",F*3),("radius",F),("length",F),("speed",F),("density_rate",F),("temperature",F),("enabled",U)]
class Obstacle(C.Structure):
    _fields_=[("size",U),("version",U),("kind",U),("a",F*3),("b",F*3),("radius",F),("velocity",F*3),("enabled",U)]
class Metrics(C.Structure):
    _fields_=[("size",U),("version",U),("ticks",Q),("time",D),("density_integral",D),("max_density",F),("max_speed",F),("divergence_rms",D),("pressure_residual_rms",D),("centroid",D*3),("non_finite",U),("reserved",U),("clamped_velocities",Q),("dropped_seconds",D),("cpu_bytes",Q)]
class Advance(C.Structure):
    _fields_=[("size",U),("version",U),("steps",U),("reserved",U),("alpha",D),("dropped_seconds",D),("simulated_seconds",D)]
class Render(C.Structure):
    _fields_=[("size",U),("version",U),("width",U),("height",U),("steps",U),("extinction",F),("colour",F*3),("eye",F*3),("target",F*3),("up",F*3),("vertical_fov_degrees",F)]
class BackendOptions(C.Structure):
    _fields_=[("size",U),("version",U),("mode",U),("detail_scale",U),("flags",U),("reserved",U),("detail_turbulence",F),("detail_frequency",F)]
class BackendInfo(C.Structure):
    _fields_=[("size",U),("version",U),("requested",U),("active",U),("detail_scale",U),("flags",U),("render_cells",U*3),("reserved",U),("cpu_bytes",Q),("gpu_bytes",Q),("hybrid_upload_bytes",Q)]
class _CAtlasTicket(C.Structure):
    _fields_=[("size",U),("version",U),("id",Q),("ticks",Q),("bytes",U),("reserved",U)]
@dataclass(frozen=True)
class AtlasTicket:
    id: int
    ticks: int
    bytes: int
    _owner: object

MODES={"auto":0,"cpu":1,"gpu":2,"hybrid":3}
FIELDS={"density":0,"temperature":1,"pressure":2,"solid":3,"velocity":4}

def _u32(value: int, name: str) -> int:
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=0xffffffff:
        raise ValueError(f"{name} must be an unsigned 32-bit integer")
    return value

def _dict(value: C.Structure) -> dict:
    return {name:list(getattr(value,name)) if isinstance(getattr(value,name),C.Array) else getattr(value,name)
            for name,_ in value._fields_ if name not in ("size","version","reserved")}

def _set(value: C.Structure, kwargs: dict, excluded=()) -> None:
    fields=dict(value._fields_)
    for name,item in kwargs.items():
        if name not in fields or name in ("size","version",*excluded): raise TypeError(f"unknown/protected option: {name}")
        kind=fields[name]
        if issubclass(kind,C.Array):
            if len(item)!=kind._length_: raise ValueError(f"{name} requires {kind._length_} values")
            setattr(value,name,kind(*item))
        elif kind is U:
            setattr(value,name,_u32(int(item) if isinstance(item,bool) else item,name))
        else: setattr(value,name,item)

class _Library:
    def __init__(self,path=None):
        if path is None: path=os.environ.get("VAPOR_LIBRARY")
        if path is None:
            name="vapor.dll" if sys.platform=="win32" else "libvapor.dylib" if sys.platform=="darwin" else "libvapor.so"
            root=Path(__file__).resolve().parents[3]
            candidates=[root/"dist"/"native"/name,root/"target"/"release"/name,Path(__file__).parent/"native"/name]
            path=next((p for p in candidates if p.is_file()),None)
        if path is None: raise FileNotFoundError("Rust library not found. Run: python tools/build.py --native; or set VAPOR_LIBRARY to its absolute path.")
        self.dll=C.CDLL(str(Path(path).resolve()))
        sig={
          "abi_version":([],U),"default_config":([C.POINTER(Config),U],C.c_int32),"default_emitter":([C.POINTER(Emitter),U],C.c_int32),
          "create":([C.POINTER(Config),C.POINTER(U)],C.c_int32),"release":([U],C.c_int32),"reset":([U],C.c_int32),"step":([U,U],C.c_int32),
          "advance":([U,D,C.POINTER(Advance),U],C.c_int32),"set_emitter":([U,U,C.POINTER(Emitter)],C.c_int32),"remove_emitter":([U,U],C.c_int32),
          "set_obstacle":([U,U,C.POINTER(Obstacle)],C.c_int32),"remove_obstacle":([U,U],C.c_int32),
          "set_profile":([U,U,C.POINTER(D),U,D,D,U],C.c_int32),"metrics":([U,C.POINTER(Metrics),U],C.c_int32),
          "field_len":([U,U,C.POINTER(U)],C.c_int32),"copy_field":([U,U,C.POINTER(F),U],C.c_int32),
          "copy_atlas":([U,C.POINTER(C.c_uint8),U],C.c_int32),"render":([U,C.POINTER(Render),C.POINTER(C.c_uint8),U],C.c_int32),
          "last_error":([C.POINTER(C.c_uint8),U],U)}
        for key,(args,result) in sig.items():
            fn=getattr(self.dll,f"vapor_{key}_v1");fn.argtypes=args;fn.restype=result;setattr(self,key,fn)
        if self.abi_version()!=1: raise VaporError(-1,"unsupported ABI version")
    def extended(self):
        if hasattr(self,"create_ex"): return
        sig={"create_ex":([C.POINTER(Config),C.POINTER(BackendOptions),C.POINTER(U)],C.c_int32),
             "backend_info":([U,C.POINTER(BackendInfo),U],C.c_int32),
             "copy_mac":([U,C.POINTER(F),U],C.c_int32)}
        loaded={}
        for key,(args,result) in sig.items():
            try: fn=getattr(self.dll,f"vapor_{key}_v1")
            except AttributeError as exc: raise VaporError(-9,"SDK 0.3 native library is required for backend selection") from exc
            fn.argtypes=args;fn.restype=result;loaded[key]=fn
        for key,fn in loaded.items():setattr(self,key,fn)
    def atlas_async(self):
        if hasattr(self,"begin_atlas"):return
        sig={"begin_atlas":([U,C.POINTER(_CAtlasTicket),U],C.c_int32),
             "poll_atlas":([U,Q,C.POINTER(C.c_uint8),U,C.POINTER(U)],C.c_int32),
             "cancel_atlas":([U,Q],C.c_int32)}
        loaded={}
        for key,(args,result) in sig.items():
            try:fn=getattr(self.dll,f"vapor_{key}_v1")
            except AttributeError as exc:raise VaporError(-9,"SDK 0.8 native library required for ticketed atlas readback") from exc
            fn.argtypes=args;fn.restype=result;loaded[key]=fn
        for key,fn in loaded.items():setattr(self,key,fn)
    def check(self,code):
        if code:
            data=(C.c_uint8*2048)();self.last_error(data,len(data));message=bytes(data).split(b"\0",1)[0].decode("utf-8",errors="replace")
            raise VaporError(code,message or "native operation failed")

class Simulation:
    """Native runtime. Legacy GPU snapshots block; ticketed atlas polling does not wait. CDLL releases the GIL.
    Snapshots are caller-owned copies. close() is idempotent. Prefer a context manager.
    """
    def __init__(self, *, library=None, cells=None, backend="cpu", detail_scale=1,
                 allow_cpu_fallback=False, allow_software_gpu=False,
                 detail_turbulence=0., detail_frequency=8., **options):
        self._lock=threading.RLock();self._handle=0;self._ticket_owner=object();self._lib=_Library(library)
        cfg=Config();self._lib.check(self._lib.default_config(C.byref(cfg),C.sizeof(cfg)))
        if cells is not None:
            if len(cells)!=3: raise ValueError("cells requires 3 integers")
            options.update(dict(zip(("nx","ny","nz"),cells)))
        _set(cfg,options)
        if backend not in MODES:raise ValueError("backend must be cpu, gpu, hybrid or auto")
        if not isinstance(allow_cpu_fallback,bool) or not isinstance(allow_software_gpu,bool):raise TypeError("fallback/software flags must be bool")
        h=U();legacy=(backend=="cpu" and detail_scale==1 and detail_turbulence==0 and detail_frequency==8 and not allow_cpu_fallback and not allow_software_gpu)
        if legacy:
            self._lib.check(self._lib.create(C.byref(cfg),C.byref(h)))
        else:
            self._lib.extended()
            opts=BackendOptions(C.sizeof(BackendOptions),1,MODES[backend],_u32(detail_scale,"detail_scale"),
                int(allow_cpu_fallback)|int(allow_software_gpu)*2,0,detail_turbulence,detail_frequency)
            self._lib.check(self._lib.create_ex(C.byref(cfg),C.byref(opts),C.byref(h)))
        self._handle=h.value
        try:
            self.config=_dict(cfg);self.shape=(cfg.nz,cfg.ny,cfg.nx)
            if legacy:
                self.backend_info=dict(requested=1,active=1,detail_scale=1,flags=1,
                    render_cells=[cfg.nx,cfg.ny,cfg.nz],cpu_bytes=self.metrics()["cpu_bytes"],gpu_bytes=0,hybrid_upload_bytes=0)
            else:
                info=BackendInfo();self._lib.check(self._lib.backend_info(self._h(),C.byref(info),C.sizeof(info)))
                self.backend_info=_dict(info)
            rx,ry,rz=self.backend_info["render_cells"];self.render_shape=(rz,ry,rx)
            self._atlas=(C.c_uint8*(rx*ry*rz*4))()
        except BaseException:
            self.close();raise
    def _h(self):
        if not self._handle: raise VaporError(-2,"simulation is closed")
        return self._handle
    def close(self):
        with self._lock:
            if self._handle:
                handle=self._handle;self._handle=0;self._lib.check(self._lib.release(handle))
    def __enter__(self): self._h();return self
    def __exit__(self,*_): self.close()
    def __del__(self):
        try:self.close()
        except Exception:pass
    def step(self,steps=1):
        with self._lock:self._lib.check(self._lib.step(self._h(),_u32(steps,"steps")))
    def advance(self,seconds:float)->dict:
        with self._lock:
            result=Advance();self._lib.check(self._lib.advance(self._h(),seconds,C.byref(result),C.sizeof(result)));return _dict(result)
    def reset(self):
        with self._lock:self._lib.check(self._lib.reset(self._h()))
    def set_emitter(self,emitter_id:int,**options):
        with self._lock:
            e=Emitter();self._lib.check(self._lib.default_emitter(C.byref(e),C.sizeof(e)));_set(e,options)
            self._lib.check(self._lib.set_emitter(self._h(),_u32(emitter_id,"emitter_id"),C.byref(e)))
    def remove_emitter(self,emitter_id:int):
        with self._lock:self._lib.check(self._lib.remove_emitter(self._h(),_u32(emitter_id,"emitter_id")))
    def set_capsule(self,obstacle_id:int,a:Sequence[float],b:Sequence[float],radius:float,velocity=(0.,0.,0.)):
        self._obstacle(obstacle_id,dict(kind=0,a=a,b=b,radius=radius,velocity=velocity,enabled=1))
    def set_sphere(self,obstacle_id:int,center:Sequence[float],radius:float,velocity=(0.,0.,0.)):
        self.set_capsule(obstacle_id,center,center,radius,velocity)
    def set_box(self,obstacle_id:int,minimum:Sequence[float],maximum:Sequence[float],velocity=(0.,0.,0.)):
        self._obstacle(obstacle_id,dict(kind=1,a=minimum,b=maximum,radius=0.,velocity=velocity,enabled=1))
    def _obstacle(self,obstacle_id,options):
        with self._lock:
            o=Obstacle();o.size=C.sizeof(o);o.version=1;_set(o,options)
            self._lib.check(self._lib.set_obstacle(self._h(),_u32(obstacle_id,"obstacle_id"),C.byref(o)))
    def remove_obstacle(self,obstacle_id:int):
        with self._lock:self._lib.check(self._lib.remove_obstacle(self._h(),_u32(obstacle_id,"obstacle_id")))
    def set_profile(self,emitter_id:int,points:Sequence[Sequence[float]]|None,*,duration=2.,start_time=0.,repeat=False):
        with self._lock:
            rows=[] if points is None else list(points)
            if rows and not 2<=len(rows)<=64:raise ValueError("profile requires 2..64 points, or empty to clear")
            if not isinstance(repeat,bool):raise TypeError("repeat must be bool")
            if any(len(row)!=4 for row in rows):raise ValueError("profile rows are [x,speed,amount,density]")
            data=(D*(len(rows)*4))(*(x for row in rows for x in row))
            self._lib.check(self._lib.set_profile(self._h(),_u32(emitter_id,"emitter_id"),data,len(rows),duration,start_time,int(bool(repeat))))
    def metrics(self)->dict:
        with self._lock:
            m=Metrics();self._lib.check(self._lib.metrics(self._h(),C.byref(m),C.sizeof(m)));return _dict(m)
    def field(self,name="density",*,numpy=False):
        with self._lock:
            f=FIELDS[name];n=U();self._lib.check(self._lib.field_len(self._h(),f,C.byref(n)));data=(F*n.value)()
            self._lib.check(self._lib.copy_field(self._h(),f,data,n.value))
            if numpy:
                import numpy as np
                shape=self.shape+((3,) if f==4 else ())
                return np.ctypeslib.as_array(data).copy().reshape(shape)
            return data
    def mac_cells(self):
        """Owned padded MAC data, eight float32 per cell. Advanced coupling API."""
        with self._lock:
            self._lib.extended();cfg=self.config;n=(cfg["nx"]+1)*(cfg["ny"]+1)*(cfg["nz"]+1)*8
            data=(F*n)();self._lib.check(self._lib.copy_mac(self._h(),data,n));return data
    def atlas_rgba8(self)->bytes:
        with self._lock:self._lib.check(self._lib.copy_atlas(self._h(),self._atlas,len(self._atlas)));return bytes(self._atlas)
    def begin_atlas(self)->AtlasTicket|None:
        """Submit one render snapshot. None means busy, never an implicit blocking copy."""
        with self._lock:
            self._lib.atlas_async();t=_CAtlasTicket()
            self._lib.check(self._lib.begin_atlas(self._h(),C.byref(t),C.sizeof(t)))
            if t.id==0:return None
            return AtlasTicket(t.id,t.ticks,t.bytes,self._ticket_owner)
    def _ticket_id(self,ticket:AtlasTicket)->int:
        if not isinstance(ticket,AtlasTicket) or ticket._owner is not self._ticket_owner:
            raise ValueError("atlas ticket belongs to a different simulation")
        if not isinstance(ticket.id,int) or not 0<ticket.id<=0xffffffffffffffff:
            raise ValueError("invalid atlas ticket ID")
        return ticket.id
    def poll_atlas(self,ticket:AtlasTicket)->bytes|None:
        """Return an owned snapshot when ready; None leaves it pending. Ready consumes ticket."""
        with self._lock:
            self._lib.atlas_async();ready=U()
            self._lib.check(self._lib.poll_atlas(self._h(),self._ticket_id(ticket),self._atlas,len(self._atlas),C.byref(ready)))
            return bytes(self._atlas) if ready.value else None
    def cancel_atlas(self,ticket:AtlasTicket):
        with self._lock:
            self._lib.atlas_async();self._lib.check(self._lib.cancel_atlas(self._h(),self._ticket_id(ticket)))
    def render(self,*,eye,target,up=(0.,1.,0.),width=320,height=240,steps=96,extinction=16.,colour=(.85,.9,.95),vertical_fov_degrees=45.)->bytes:
        with self._lock:
            width=_u32(width,"width");height=_u32(height,"height")
            if not 0<width<=4096 or not 0<height<=4096:raise ValueError("image dimensions must be 1..4096")
            r=Render();r.size=C.sizeof(r);r.version=1
            _set(r,dict(width=width,height=height,steps=steps,extinction=extinction,colour=colour,eye=eye,target=target,up=up,vertical_fov_degrees=vertical_fov_degrees))
            data=(C.c_uint8*(width*height*4))();self._lib.check(self._lib.render(self._h(),C.byref(r),data,len(data)));return bytes(data)

__all__=["Simulation","VaporError","AtlasTicket"]

from .effects import Effect, create_effect, get_preset, create_effect_from_recipe, ember_visual
__all__ += ["Effect", "create_effect", "get_preset", "create_effect_from_recipe", "ember_visual"]
