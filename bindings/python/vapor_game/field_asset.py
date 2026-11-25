"""VPF1 lossless portable Float32 field; importing needs no native runtime."""
from array import array
from dataclasses import dataclass
import math, struct, sys, zlib
from pathlib import Path
HEADER=80
MAX=2097152
_FORMAT=struct.Struct('<4sI3II3dddIIII')
assert _FORMAT.size==HEADER
@dataclass(frozen=True)
class BakedField:
    cells:tuple
    extent:tuple
    density_cap:float
    time:float
    density:array
    temperature:array
    def native_fields(self):
        from .fidelity import Fields
        return Fields(self.cells,self.extent,self.density_cap,self.density,self.temperature)

def _grid(cells,extent,cap,time):
    if len(cells)!=3 or any(type(n) is not int or not 4<=n<=512 for n in cells):raise ValueError('invalid VPF cells')
    n=math.prod(cells)
    if n>MAX or len(extent)!=3 or any(not math.isfinite(x) or not .0001<=x<=1e7 for x in extent) or not math.isfinite(cap) or not .00001<=cap<=100 or not math.isfinite(time) or not 0<=time<=1e7:raise ValueError('invalid VPF grid/time')
    return n

def _values(d,t,n,cap):
    if len(d)!=n or len(t)!=n or any(not math.isfinite(x) or not 0<=x<=cap*(1+1e-6) for x in d) or any(not math.isfinite(x) or not 0<=x<=1e5 for x in t):raise ValueError('invalid VPF scalar')

def decode_field_asset(data):
    b=memoryview(data).cast('B')
    if not HEADER<=len(b)<=HEADER+MAX*8:raise ValueError('invalid VPF byte count')
    magic,header,nx,ny,nz,flags,x,y,z,cap,time,crc,reserved,payload,reserved2=_FORMAT.unpack_from(b)
    if magic!=b'VPF1' or header!=HEADER or flags or reserved or reserved2:raise ValueError('unsupported VPF header')
    cells=(nx,ny,nz);extent=(x,y,z);n=_grid(cells,extent,cap,time)
    if payload!=n*8 or len(b)!=HEADER+payload or zlib.crc32(b[HEADER:])!=crc:raise ValueError('invalid VPF payload length/CRC')
    d=array('f');t=array('f');d.frombytes(b[HEADER:HEADER+n*4]);t.frombytes(b[HEADER+n*4:]);
    if sys.byteorder!='little':d.byteswap();t.byteswap()
    _values(d,t,n,cap)
    return BakedField(cells,extent,cap,time,d,t)

def read_field_asset(path):
    # Bound allocation even for untrusted files; decode rejects extra bytes.
    with Path(path).open('rb') as f:return decode_field_asset(f.read(HEADER+MAX*8+1))

def encode_field_asset(field):
    n=_grid(field.cells,field.extent,field.density_cap,field.time)
    d=array('f',field.density);t=array('f',field.temperature);_values(d,t,n,field.density_cap)
    if sys.byteorder!='little':d.byteswap();t.byteswap()
    payload=d.tobytes()+t.tobytes()
    return _FORMAT.pack(b'VPF1',HEADER,*field.cells,0,*field.extent,field.density_cap,field.time,zlib.crc32(payload),0,len(payload),0)+payload
