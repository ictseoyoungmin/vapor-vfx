"""VPA1 index + independent VPF1 frames. Data-only, no native fallback.
Two decoded keyframes maximum; linear interpolation of density and temperature.
"""
from __future__ import annotations
from array import array
from bisect import bisect_right
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import math,struct,zlib
from .field_asset import BakedField,decode_field_asset,HEADER as FIELD_HEADER,MAX as MAX_VOXELS,_grid
HEADER=64; RECORD=16; MAX_FRAMES=4096; MAX_FIELD=FIELD_HEADER+MAX_VOXELS*8
H=struct.Struct('<4sII I 3I I 3d d'); R=struct.Struct('<dII')
assert H.size==HEADER and R.size==RECORD

def frame_filename(i):
    if type(i) is not int or not 0<=i<MAX_FRAMES:raise ValueError('invalid VPA frame index')
    return f'frame_{i:04d}.vpf'

@dataclass(frozen=True)
class SequenceIndex:
    cells:tuple;extent:tuple;density_cap:float;records:tuple
    @property
    def times(self):return tuple(r[0] for r in self.records)

def decode_index(data):
    b=memoryview(data).cast('B')
    if not HEADER+RECORD<=len(b)<=HEADER+MAX_FRAMES*RECORD:raise ValueError('invalid VPA index length')
    magic,header,count,crc,nx,ny,nz,res,x,y,z,cap=H.unpack_from(b)
    if magic!=b'VPA1' or header!=HEADER or not 1<=count<=MAX_FRAMES or res or len(b)!=HEADER+count*RECORD or zlib.crc32(b[16:])!=crc:raise ValueError('invalid VPA header/checksum')
    cells=(nx,ny,nz);ext=(x,y,z);n=_grid(cells,ext,cap,0.);records=tuple(R.iter_unpack(b[HEADER:]));previous=-1.
    for t,length,c in records:
        if not math.isfinite(t) or not previous<t<=1e7 or t<0 or length!=FIELD_HEADER+n*8:raise ValueError('invalid VPA record')
        previous=t
    return SequenceIndex(cells,ext,cap,records)

def _record(raw,f):return (f.time,len(raw),zlib.crc32(raw))
def encode_index(frames):
    records=[];grid=None
    for raw in frames:
        if len(records)>=MAX_FRAMES:raise ValueError('too many VPA frames')
        f=decode_field_asset(raw);g=(f.cells,f.extent,f.density_cap)
        if grid is None:grid=g
        if g!=grid:raise ValueError('inconsistent VPA grid')
        records.append(_record(raw,f))
    if not records:raise ValueError('empty sequence')
    b=bytearray(H.pack(b'VPA1',HEADER,len(records),0,*grid[0],0,*grid[1],grid[2])+b''.join(R.pack(*r) for r in records))
    struct.pack_into('<I',b,12,zlib.crc32(b[16:]));decode_index(b);return bytes(b)

def index_from_paths(paths):
    def read():
        for p in paths:
            with Path(p).open('rb') as f:yield f.read(MAX_FIELD+1)
    return encode_index(read())

class FieldSequence:
    def __init__(self,index,load_frame):
        self.index=decode_index(index);self._load=load_frame;self._cache=OrderedDict();self._times=self.index.times
    @classmethod
    def open(cls,path):
        path=Path(path)
        with path.open('rb') as f:idx=f.read(HEADER+MAX_FRAMES*RECORD+1)
        def load(i,n):
            with (path.parent/frame_filename(i)).open('rb') as f:return f.read(n+1)
        return cls(idx,load)
    def _frame(self,i):
        if i in self._cache:self._cache.move_to_end(i);return self._cache[i]
        t,length,c=self.index.records[i];raw=self._load(i,length)
        if len(raw)!=length or zlib.crc32(raw)!=c:raise ValueError('VPA frame length/checksum mismatch')
        f=decode_field_asset(raw)
        if (f.cells,f.extent,f.density_cap,f.time)!=(self.index.cells,self.index.extent,self.index.density_cap,t):raise ValueError('VPA frame metadata mismatch')
        if len(self._cache)==2:self._cache.popitem(last=False)
        self._cache[i]=f;return f
    def sample(self,time):
        if not math.isfinite(time):raise ValueError('invalid sample time')
        time=min(max(time,self._times[0]),self._times[-1]);i=bisect_right(self._times,time)-1
        a=self._frame(i)
        if time==a.time:return BakedField(a.cells,a.extent,a.density_cap,time,array('f',a.density),array('f',a.temperature))
        b=self._frame(i+1);u=(time-a.time)/(b.time-a.time)
        lerp=lambda x,y:array('f',(float(p)+(float(q)-float(p))*u for p,q in zip(x,y)))
        return BakedField(a.cells,a.extent,a.density_cap,time,lerp(a.density,b.density),lerp(a.temperature,b.temperature))
    @property
    def cached_frames(self):return len(self._cache)
    def clear(self):self._cache.clear()
