using System;
using System.IO;
namespace VaporGame
{
    /// <summary>VPF1 lossless data-only field; independent of native-library availability.</summary>
    public sealed class FieldAsset
    {
        const int Header=80, MaxVoxels=2097152;
        public FidelityFields Fields {get;}
        public double Time {get;}
        private FieldAsset(FidelityFields fields,double time){Fields=fields;Time=time;}
        private static bool Bounded(double v,double lo,double hi){return !double.IsNaN(v)&&!double.IsInfinity(v)&&v>=lo&&v<=hi;}
        private static uint Crc(byte[] b,int offset){uint c=0xffffffff;for(int i=offset;i<b.Length;i++){c^=b[i];for(int j=0;j<8;j++)c=(c>>1)^((c&1)!=0?0xedb88320u:0u);}return ~c;}
        public static FieldAsset Decode(byte[] bytes)
        {
            if(bytes==null||bytes.Length<Header||bytes.Length>Header+MaxVoxels*8)throw new ArgumentException("Invalid VPF length");
            using(var r=new BinaryReader(new MemoryStream(bytes,false)))
            {
                if(r.ReadUInt32()!=0x31465056u||r.ReadUInt32()!=Header)throw new ArgumentException("Unsupported VPF header");
                uint nx=r.ReadUInt32(),ny=r.ReadUInt32(),nz=r.ReadUInt32();if(r.ReadUInt32()!=0)throw new ArgumentException("Unknown VPF flags");
                var extent=new Double3(r.ReadDouble(),r.ReadDouble(),r.ReadDouble());double cap=r.ReadDouble(),time=r.ReadDouble();uint crc=r.ReadUInt32(),reserved=r.ReadUInt32(),size=r.ReadUInt32(),reserved2=r.ReadUInt32();
                var grid=new FidelityGrid(nx,ny,nz,extent,cap);int n=FidelityCPU.ValidateGrid(grid);
                if(!Bounded(time,0,1e7)||reserved!=0||reserved2!=0||size!=(uint)(n*8)||bytes.Length!=Header+n*8||Crc(bytes,Header)!=crc)throw new ArgumentException("Invalid VPF payload");
                var d=new float[n];var t=new float[n];for(int i=0;i<n;i++){d[i]=r.ReadSingle();if(!Bounded(d[i],0,cap*(1+1e-6)))throw new ArgumentException("Invalid VPF density");}
                for(int i=0;i<n;i++){t[i]=r.ReadSingle();if(!Bounded(t[i],0,1e5))throw new ArgumentException("Invalid VPF temperature");}
                return new FieldAsset(new FidelityFields(grid,d,t),time);
            }
        }
    }
}
