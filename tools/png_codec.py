"""Small dependency-free PNG writer for actual runtime captures (no placeholder imagery)."""
from __future__ import annotations
import binascii,struct,zlib
from pathlib import Path

def write_rgba(path:Path,width:int,height:int,pixels:bytes)->None:
    if not 1<=width<=4096 or not 1<=height<=4096 or len(pixels)!=width*height*4:
        raise ValueError('RGBA image dimensions/length mismatch')
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
    rows=b''.join(b'\0'+pixels[y*width*4:(y+1)*width*4] for y in range(height))
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))
    data+=chunk(b'IDAT',zlib.compress(rows,6))+chunk(b'IEND',b'')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)

def composite_linear_premultiplied(pixels:bytes,background=(.016,.023,.034))->bytes:
    """The Rust preview is premultiplied linear RGBA, not straight sRGB PNG."""
    if len(pixels)%4:raise ValueError('Invalid RGBA bytes')
    def srgb(x):
        x=max(0.,min(1.,x));return round(255*(12.92*x if x<=.0031308 else 1.055*x**(1/2.4)-.055))
    out=bytearray(len(pixels))
    for i in range(0,len(pixels),4):
        trans=1-pixels[i+3]/255
        for channel in range(3):out[i+channel]=srgb(pixels[i+channel]/255+background[channel]*trans)
        out[i+3]=255
    return bytes(out)
