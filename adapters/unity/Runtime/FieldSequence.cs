using System;
using System.IO;
using System.Collections.Generic;
namespace VaporGame {
    /// <summary>VPA1 data-only playback. Loader must bound I/O by the requested byte count.
    /// Synchronous API, at most two cached keyframes; caller schedules I/O outside render thread.</summary>
    public sealed class FieldSequence {
        readonly FidelityGrid grid;readonly double[] times;readonly int[] sizes;readonly uint[] checksums;readonly Func<int,int,byte[]> load;
        readonly List<KeyValuePair<int,FieldAsset>> cache=new List<KeyValuePair<int,FieldAsset>>(2);
        static bool Bound(double x,double lo,double hi){return !double.IsNaN(x)&&!double.IsInfinity(x)&&x>=lo&&x<=hi;}
        static uint Crc(byte[] b,int start){uint c=0xffffffff;for(int i=start;i<b.Length;i++){c^=b[i];for(int j=0;j<8;j++)c=(c>>1)^((c&1)!=0?0xedb88320u:0u);}return ~c;}
        public static string FrameFilename(int i){if(i<0||i>=4096)throw new ArgumentOutOfRangeException(nameof(i));return "frame_"+i.ToString("D4",System.Globalization.CultureInfo.InvariantCulture)+".vpf";}
        public FieldSequence(byte[] index,Func<int,int,byte[]> loader){
            load=loader??throw new ArgumentNullException(nameof(loader));if(index==null||index.Length<80||index.Length>64+4096*16)throw new ArgumentException("VPA index length");
            using(var r=new BinaryReader(new MemoryStream(index,false))){if(r.ReadUInt32()!=0x31415056u||r.ReadUInt32()!=64)throw new ArgumentException("VPA header");uint count=r.ReadUInt32(),crc=r.ReadUInt32();if(count<1||count>4096||index.Length!=64+count*16||Crc(index,16)!=crc)throw new ArgumentException("VPA index checksum");uint nx=r.ReadUInt32(),ny=r.ReadUInt32(),nz=r.ReadUInt32();if(r.ReadUInt32()!=0)throw new ArgumentException("VPA flags");var ext=new Double3(r.ReadDouble(),r.ReadDouble(),r.ReadDouble());grid=new FidelityGrid(nx,ny,nz,ext,r.ReadDouble());int n=FidelityCPU.ValidateGrid(grid);times=new double[(int)count];sizes=new int[(int)count];checksums=new uint[(int)count];double prev=-1;for(int i=0;i<times.Length;i++){double t=r.ReadDouble();uint size=r.ReadUInt32();checksums[i]=r.ReadUInt32();if(!Bound(t,0,1e7)||t<=prev||size!=80+n*8)throw new ArgumentException("VPA record");times[i]=prev=t;sizes[i]=(int)size;}}
        }
        public double StartTime=>times[0];public double EndTime=>times[times.Length-1];public int CachedFrames=>cache.Count;
        public void Clear(){cache.Clear();}
        FieldAsset Frame(int i){for(int j=0;j<cache.Count;j++)if(cache[j].Key==i){var f=cache[j];cache.RemoveAt(j);cache.Add(f);return f.Value;}
            var raw=load(i,sizes[i]);if(raw==null||raw.Length!=sizes[i]||Crc(raw,0)!=checksums[i])throw new ArgumentException("VPA frame checksum");var a=FieldAsset.Decode(raw);var g=a.Fields.Grid;if(g.Nx!=grid.Nx||g.Ny!=grid.Ny||g.Nz!=grid.Nz||g.Extent.X!=grid.Extent.X||g.Extent.Y!=grid.Extent.Y||g.Extent.Z!=grid.Extent.Z||g.DensityCap!=grid.DensityCap||a.Time!=times[i])throw new ArgumentException("VPA frame metadata");if(cache.Count==2)cache.RemoveAt(0);cache.Add(new KeyValuePair<int,FieldAsset>(i,a));return a;}
        public FidelityFields Sample(double time){if(double.IsNaN(time)||double.IsInfinity(time))throw new ArgumentException("VPA sample time");time=Math.Max(StartTime,Math.Min(EndTime,time));int i=Array.BinarySearch(times,time);if(i<0)i=~i-1;var a=Frame(i).Fields;var d=(float[])a.Density.Clone();var t=(float[])a.Temperature.Clone();if(time!=times[i]){var b=Frame(i+1).Fields;double u=(time-times[i])/(times[i+1]-times[i]);for(int j=0;j<d.Length;j++){d[j]=(float)((double)d[j]+((double)b.Density[j]-d[j])*u);t[j]=(float)((double)t[j]+((double)b.Temperature[j]-t[j])*u);}}return new FidelityFields(grid,d,t);}
    }
}
