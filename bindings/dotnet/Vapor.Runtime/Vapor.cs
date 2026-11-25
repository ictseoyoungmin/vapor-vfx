using System;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace VaporGame
{
    [StructLayout(LayoutKind.Sequential)]
    public struct Float3
    {
        public float X,Y,Z;
        public Float3(float x,float y,float z){X=x;Y=y;Z=z;}
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct Config
    {
        public uint Size,Version,Nx,Ny,Nz;
        public float CellSize;
        public Float3 Origin;
        public float FixedDt;
        public uint MaxSubsteps,PressureIterations;
        public float SorOmega,DensityDecay,Cooling,Buoyancy,DensityWeight,Drag,Vorticity;
        public Float3 Wind;
        public float MaxVelocity,DensityCap;
        public uint Boundary;
        public static Config Default {get {Native.Check(Native.vapor_default_config_v1(out Config c,(uint)Marshal.SizeOf<Config>()));return c;}}
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct Emitter
    {
        public uint Size,Version;
        public Float3 Position,Direction;
        public float Radius,Length,Speed,DensityRate,Temperature;
        public uint Enabled;
        public static Emitter Default {get {Native.Check(Native.vapor_default_emitter_v1(out Emitter e,(uint)Marshal.SizeOf<Emitter>()));return e;}}
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct Obstacle
    {
        public uint Size,Version,Kind;
        public Float3 A,B;
        public float Radius;
        public Float3 Velocity;
        public uint Enabled;
        public static Obstacle Capsule(Float3 a,Float3 b,float radius,Float3 velocity=default)
        {return new Obstacle{Size=(uint)Marshal.SizeOf<Obstacle>(),Version=1,Kind=0,A=a,B=b,Radius=radius,Velocity=velocity,Enabled=1};}
        public static Obstacle Box(Float3 min,Float3 max,Float3 velocity=default)
        {return new Obstacle{Size=(uint)Marshal.SizeOf<Obstacle>(),Version=1,Kind=1,A=min,B=max,Velocity=velocity,Enabled=1};}
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct Metrics
    {
        public uint Size,Version;
        public ulong Ticks;
        public double Time,DensityIntegral;
        public float MaxDensity,MaxSpeed;
        public double DivergenceRms,PressureResidualRms,CentroidX,CentroidY,CentroidZ;
        public uint NonFinite,Reserved;
        public ulong ClampedVelocities;
        public double DroppedSeconds;
        public ulong CpuBytes;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct AdvanceReport
    {
        public uint Size,Version,Steps,Reserved;
        public double Alpha,DroppedSeconds,SimulatedSeconds;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct RenderOptions
    {
        public uint Size,Version,Width,Height,Steps;
        public float Extinction;
        public Float3 Colour,Eye,Target,Up;
        public float VerticalFovDegrees;
    }
    public enum BackendMode:uint {Auto=0,Cpu=1,Gpu=2,Hybrid=3}
    [StructLayout(LayoutKind.Sequential)]
    public struct BackendOptions
    {
        public uint Size,Version;
        public BackendMode Mode;
        public uint DetailScale,Flags,Reserved;
        public float DetailTurbulence,DetailFrequency;
        public static BackendOptions For(BackendMode mode,uint detailScale=1,bool allowCpuFallback=false,bool allowSoftwareGpu=false)
        {return new BackendOptions {Size=(uint)Marshal.SizeOf<BackendOptions>(),Version=1,Mode=mode,DetailScale=detailScale,
            Flags=(allowCpuFallback?1u:0u)|(allowSoftwareGpu?2u:0u),DetailFrequency=8};}
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct BackendInfo
    {
        public uint Size,Version;
        public BackendMode Requested,Active;
        public uint DetailScale,Flags,RenderNx,RenderNy,RenderNz,Reserved;
        public ulong CpuBytes,GpuBytes,HybridUploadBytes;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct AtlasTicket
    {
        public uint Size,Version;
        public ulong Id,Ticks;
        public uint Bytes,Reserved;
    }
    public enum Field:uint {Density=0,Temperature=1,Pressure=2,Solid=3,Velocity=4}
    public sealed class VaporException:Exception
    {public int Code{get;}public VaporException(int code,string message):base("Vapor ["+code+"]: "+message){Code=code;}}

    internal static class Native
    {
#if UNITY_IOS && !UNITY_EDITOR
        internal const string Library="__Internal";
#else
        internal const string Library="vapor";
#endif
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern uint vapor_abi_version_v1();
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_default_config_v1(out Config config,uint size);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_default_emitter_v1(out Emitter emitter,uint size);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_create_v1(in Config config,out uint handle);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_create_ex_v1(in Config config,in BackendOptions backend,out uint handle);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_backend_info_v1(uint handle,out BackendInfo info,uint size);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_copy_mac_v1(uint handle,[Out] float[] output,uint elements);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_release_v1(uint handle);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_reset_v1(uint handle);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_step_v1(uint handle,uint count);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_advance_v1(uint handle,double seconds,out AdvanceReport result,uint size);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_set_emitter_v1(uint handle,uint id,in Emitter emitter);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_remove_emitter_v1(uint handle,uint id);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_set_obstacle_v1(uint handle,uint id,in Obstacle obstacle);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_remove_obstacle_v1(uint handle,uint id);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_set_profile_v1(uint handle,uint id,[In] double[] points,uint count,double duration,double start,uint repeat);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_metrics_v1(uint handle,out Metrics result,uint size);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_field_len_v1(uint handle,uint field,out uint length);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_copy_field_v1(uint handle,uint field,[Out] float[] output,uint elements);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_begin_atlas_v1(uint handle,out AtlasTicket ticket,uint size);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_poll_atlas_v1(uint handle,ulong id,[In,Out] byte[] output,uint bytes,out uint ready);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_cancel_atlas_v1(uint handle,ulong id);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_copy_atlas_v1(uint handle,[Out] byte[] output,uint bytes);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern int vapor_render_v1(uint handle,in RenderOptions options,[Out] byte[] output,uint bytes);
        [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] internal static extern uint vapor_last_error_v1([Out] byte[] output,uint bytes);
        internal static void Check(int code)
        {if(code==0)return;byte[] text=new byte[2048];vapor_last_error_v1(text,(uint)text.Length);int n=Array.IndexOf(text,(byte)0);throw new VaporException(code,Encoding.UTF8.GetString(text,0,n<0?text.Length:n));}
    }
    internal sealed class SimulationHandle:SafeHandleZeroOrMinusOneIsInvalid
    {
        internal SimulationHandle(uint token):base(true){SetHandle(new IntPtr(unchecked((int)token)));}
        internal uint Token{get {return unchecked((uint)DangerousGetHandle().ToInt64());}}
        protected override bool ReleaseHandle(){return Native.vapor_release_v1(unchecked((uint)handle.ToInt64()))==0;}
    }
    /// <summary>Native CPU/GPU/hybrid runtime. Legacy readbacks block; ticketed atlas polling does not wait.</summary>
    public sealed class Simulation:IDisposable
    {
        private readonly object sync=new object();
        private readonly SimulationHandle handle;
        public Config Configuration{get;}
        public int VoxelCount{get;}
        public BackendInfo Backend{get;}
        public int RenderVoxelCount{get;}
        public Simulation(Config config):this(config,null){}
        public Simulation(Config config,BackendOptions backend):this(config,(BackendOptions?)backend){}
        private Simulation(Config config,BackendOptions? backend)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            throw new PlatformNotSupportedException("Use the direct browser WASM SDK. This native Unity adapter does not implement Unity WebGL interop.");
#else
            if(Native.vapor_abi_version_v1()!=1)throw new VaporException(-1,"ABI mismatch");
            config.Size=(uint)Marshal.SizeOf<Config>();config.Version=1;
            uint h;
            if(backend.HasValue){var opts=backend.Value;opts.Size=(uint)Marshal.SizeOf<BackendOptions>();opts.Version=1;
                Native.Check(Native.vapor_create_ex_v1(in config,in opts,out h));}
            else Native.Check(Native.vapor_create_v1(in config,out h));
            handle=new SimulationHandle(h);Configuration=config;
            try {
                VoxelCount=checked((int)((ulong)config.Nx*config.Ny*config.Nz));
                if(backend.HasValue){Native.Check(Native.vapor_backend_info_v1(h,out BackendInfo info,(uint)Marshal.SizeOf<BackendInfo>()));Backend=info;}
                else Backend=new BackendInfo{Size=(uint)Marshal.SizeOf<BackendInfo>(),Version=1,Requested=BackendMode.Cpu,Active=BackendMode.Cpu,
                    DetailScale=1,Flags=1,RenderNx=config.Nx,RenderNy=config.Ny,RenderNz=config.Nz};
                RenderVoxelCount=checked((int)((ulong)Backend.RenderNx*Backend.RenderNy*Backend.RenderNz));
            } catch {handle.Dispose();throw;}
#endif
        }
        private uint Token {get {if(handle==null||handle.IsClosed||handle.IsInvalid)throw new ObjectDisposedException(nameof(Simulation));return handle.Token;}}
        public void Dispose(){lock(sync){handle?.Dispose();}}
        // Host-side generation lets adapters forget a ticket invalidated by an external reset.
        public ulong AtlasEpoch {get {lock(sync){return atlasEpoch;}}}
        private ulong atlasEpoch;
        public void Reset(){lock(sync){uint token=Token;try{Native.Check(Native.vapor_reset_v1(token));}finally{unchecked{atlasEpoch++;}}}}
        public void Step(uint count=1){lock(sync){Native.Check(Native.vapor_step_v1(Token,count));}}
        public AdvanceReport Advance(double elapsed){lock(sync){Native.Check(Native.vapor_advance_v1(Token,elapsed,out AdvanceReport result,(uint)Marshal.SizeOf<AdvanceReport>()));return result;}}
        public void SetEmitter(uint id,Emitter e){lock(sync){e.Size=(uint)Marshal.SizeOf<Emitter>();e.Version=1;Native.Check(Native.vapor_set_emitter_v1(Token,id,in e));}}
        public void RemoveEmitter(uint id){lock(sync){Native.Check(Native.vapor_remove_emitter_v1(Token,id));}}
        public void SetObstacle(uint id,Obstacle o){lock(sync){o.Size=(uint)Marshal.SizeOf<Obstacle>();o.Version=1;Native.Check(Native.vapor_set_obstacle_v1(Token,id,in o));}}
        public void RemoveObstacle(uint id){lock(sync){Native.Check(Native.vapor_remove_obstacle_v1(Token,id));}}
        public void SetProfile(uint id,double[] xySpeedAmountDensity,double duration=2,double startTime=0,bool repeat=false)
        {lock(sync){int n=xySpeedAmountDensity?.Length??0;if(n%4!=0||n>256)throw new ArgumentException("Use 2..64 packed [x,speed,amount,density] rows, or null to clear.");Native.Check(Native.vapor_set_profile_v1(Token,id,xySpeedAmountDensity,(uint)(n/4),duration,startTime,repeat?1u:0u));}}
        public Metrics Metrics(){lock(sync){Native.Check(Native.vapor_metrics_v1(Token,out Metrics result,(uint)Marshal.SizeOf<Metrics>()));return result;}}
        public int FieldLength(Field field){lock(sync){Native.Check(Native.vapor_field_len_v1(Token,(uint)field,out uint n));return checked((int)n);}}
        public void CopyField(Field field,float[] output){if(output==null)throw new ArgumentNullException(nameof(output));lock(sync){Native.Check(Native.vapor_copy_field_v1(Token,(uint)field,output,(uint)output.Length));}}
        public float[] ReadField(Field field=Field.Density){var output=new float[FieldLength(field)];CopyField(field,output);return output;}
        public float[] ReadMacCells(){lock(sync){var output=new float[checked((int)((Configuration.Nx+1)*(Configuration.Ny+1)*(Configuration.Nz+1)*8))];Native.Check(Native.vapor_copy_mac_v1(Token,output,(uint)output.Length));return output;}}
        public void CopyAtlas(byte[] output){if(output==null)throw new ArgumentNullException(nameof(output));lock(sync){Native.Check(Native.vapor_copy_atlas_v1(Token,output,(uint)output.Length));}}
        /// <summary>False means the one outstanding slot is busy. IDs are scoped to this Simulation.</summary>
        public bool TryBeginAtlas(out AtlasTicket ticket){lock(sync){Native.Check(Native.vapor_begin_atlas_v1(Token,out ticket,(uint)Marshal.SizeOf<AtlasTicket>()));return ticket.Id!=0;}}
        /// <summary>False means pending (output unchanged); true copies once and consumes the ticket.</summary>
        public bool TryPollAtlas(AtlasTicket ticket,byte[] output){if(output==null)throw new ArgumentNullException(nameof(output));lock(sync){Native.Check(Native.vapor_poll_atlas_v1(Token,ticket.Id,output,(uint)output.Length,out uint ready));return ready!=0;}}
        public void CancelAtlas(AtlasTicket ticket){lock(sync){Native.Check(Native.vapor_cancel_atlas_v1(Token,ticket.Id));}}
        public byte[] Render(RenderOptions options)
        {lock(sync){options.Size=(uint)Marshal.SizeOf<RenderOptions>();options.Version=1;if(options.Width==0||options.Height==0||options.Width>4096||options.Height>4096)throw new ArgumentOutOfRangeException(nameof(options));var output=new byte[checked((int)(options.Width*options.Height*4))];Native.Check(Native.vapor_render_v1(Token,in options,output,(uint)output.Length));return output;}}
    }
}
