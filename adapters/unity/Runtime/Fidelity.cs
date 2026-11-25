using System;
using System.Runtime.InteropServices;

namespace VaporGame
{
    [StructLayout(LayoutKind.Sequential)]
    public struct Double3
    {
        public double X,Y,Z;
        public Double3(double x,double y,double z){X=x;Y=y;Z=z;}
    }
    public enum FidelityKind:uint { Cloud=1,Fog=2,Dust=3 }
    [StructLayout(LayoutKind.Sequential)]
    public struct FidelityGrid
    {
        internal uint Size,Version;
        public uint Nx,Ny,Nz;
        internal uint Reserved;
        public Double3 Extent;
        public double DensityCap;
        public FidelityGrid(uint nx,uint ny,uint nz,Double3 extent,double cap=1)
        {Size=56;Version=1;Nx=nx;Ny=ny;Nz=nz;Reserved=0;Extent=extent;DensityCap=cap;}
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct FidelityDensity
    {
        internal uint Size,Version;
        public FidelityKind Kind;
        public uint Seed;
        public double Coverage,Humidity,Erosion;
        public Double3 Wind;
        public static FidelityDensity For(FidelityKind kind,uint seed=137)
        {return new FidelityDensity{Size=64,Version=1,Kind=kind,Seed=seed,Coverage=.6,Humidity=.65,Erosion=.4};}
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct FidelityOptics
    {
        internal uint Size,Version;
        public uint ShadowSteps;
        internal uint Reserved;
        public Double3 Colour;
        public double Extinction,Anisotropy,Albedo,Emission,ThermalFade,Ambient;
        public Double3 Direction,Radiance,Sky,Ground;
        public double MultiScatter,LightScale;
        public static FidelityOptics Default {get {return new FidelityOptics{Size=200,Version=1,ShadowSteps=24,Colour=new Double3(.91,.96,1),Extinction=.32,Anisotropy=.55,Albedo=.9,Ambient=.1,Direction=new Double3(-.8,.56,.16),Radiance=new Double3(2.6,2.45,2.2),Sky=new Double3(.07,.105,.18),Ground=new Double3(.035,.04,.05),MultiScatter=.29,LightScale=.5};}}
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct FidelityCamera
    {
        internal uint Size,Version;
        public uint Width,Height,Steps,Dark;
        public Double3 Eye,Target;
        public double Fov,Exposure,Jitter;
        public static FidelityCamera LookAt(Double3 eye,Double3 target,uint width=640,uint height=400,uint steps=128)
        {return new FidelityCamera{Size=96,Version=1,Width=width,Height=height,Steps=steps,Eye=eye,Target=target,Fov=40,Exposure=1,Jitter=.5};}
    }
    public sealed class FidelityFields
    {
        public FidelityGrid Grid {get;}
        public float[] Density {get;}
        public float[] Temperature {get;}
        public FidelityFields(FidelityGrid grid,float[] density,float[] temperature)
        {int count=FidelityCPU.ValidateGrid(grid);if(density==null||temperature==null||density.Length!=count||temperature.Length!=count)throw new ArgumentException("Invalid field lengths");Grid=grid;Density=density;Temperature=temperature;}
    }
    public sealed class FidelityFrame
    {
        public byte[] Rgba {get;}
        public float[] Alpha {get;}
        public uint Width {get;}
        public uint Height {get;}
        internal FidelityFrame(byte[] rgba,float[] alpha,uint w,uint h){Rgba=rgba;Alpha=alpha;Width=w;Height=h;}
    }
    /// <summary>Rust native CPU Fidelity, no alternative backend. Stateless offline/authoring calls;
    /// optical cache rebuilt each render. Float32 fields and straight display RGBA, separate alpha.</summary>
    public static class FidelityCPU
    {
        [DllImport(Native.Library,CallingConvention=CallingConvention.Cdecl)]
        private static extern int vapor_fidelity_generate_v1(in FidelityGrid grid,in FidelityDensity settings,double time,[In] float[] terrain,uint terrainElements,[Out] float[] density,[Out] float[] temperature,uint elements);
        [DllImport(Native.Library,CallingConvention=CallingConvention.Cdecl)]
        private static extern int vapor_fidelity_render_v1(in FidelityGrid grid,in FidelityOptics optics,in FidelityCamera camera,[In] float[] density,[In] float[] temperature,uint elements,[In] float[] depth,[In] float[] radiance,uint scenePixels,[Out] byte[] rgba,uint bytes,[Out] float[] alpha,uint alphaElements);
        private static bool Bounded(double x,double lo,double hi){return !double.IsNaN(x)&&!double.IsInfinity(x)&&x>=lo&&x<=hi;}
        internal static int ValidateGrid(FidelityGrid g)
        {if(g.Nx<4||g.Ny<4||g.Nz<4||g.Nx>512||g.Ny>512||g.Nz>512||!Bounded(g.Extent.X,.0001,1e7)||!Bounded(g.Extent.Y,.0001,1e7)||!Bounded(g.Extent.Z,.0001,1e7)||!Bounded(g.DensityCap,.00001,100))throw new ArgumentOutOfRangeException(nameof(g));ulong n=(ulong)g.Nx*g.Ny*g.Nz;if(n>2097152)throw new ArgumentOutOfRangeException(nameof(g),"Voxel budget exceeded");return (int)n;}
        private static void CheckAbi()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            throw new PlatformNotSupportedException("Use native-fidelity.mjs for browser Rust WASM. Unity WebGL interop is not implemented.");
#else
            if(Marshal.SizeOf<FidelityGrid>()!=56||Marshal.SizeOf<FidelityDensity>()!=64||Marshal.SizeOf<FidelityOptics>()!=200||Marshal.SizeOf<FidelityCamera>()!=96||Native.vapor_abi_version_v1()!=1)throw new InvalidOperationException("Fidelity ABI mismatch");
#endif
        }
        /// <summary>Generate from the canonical native effect catalog, not manual defaults.</summary>
        public static FidelityFields Generate(EffectId id,EffectQuality quality=EffectQuality.High,double time=0,float[] terrain=null)
        {
            FidelityKind kind;
            switch(id){case EffectId.CumulusCloud:kind=FidelityKind.Cloud;break;case EffectId.GroundFog:kind=FidelityKind.Fog;break;case EffectId.Dust:kind=FidelityKind.Dust;break;default:throw new ArgumentException("Fluid requires actual simulation fields",nameof(id));}
            CheckAbi();var p=EffectPreset.Get(id,quality);var c=p.Config;var s=p.Procedural;
            var grid=new FidelityGrid(c.Nx,c.Ny,c.Nz,new Double3(c.Nx*(double)c.CellSize,c.Ny*(double)c.CellSize,c.Nz*(double)c.CellSize),c.DensityCap);
            var settings=FidelityDensity.For(kind,s.Seed);settings.Coverage=s.Coverage;settings.Humidity=s.Humidity;settings.Erosion=s.Erosion;settings.Wind=new Double3(s.Wind.X,s.Wind.Y,s.Wind.Z);
            return Generate(grid,settings,time,terrain);
        }
        public static FidelityFields Generate(FidelityGrid grid,FidelityDensity settings,double time=0,float[] terrain=null)
        {int n=ValidateGrid(grid);if(!Bounded(time,0,1e7))throw new ArgumentOutOfRangeException(nameof(time));if(terrain!=null&&(settings.Kind==FidelityKind.Cloud||terrain.Length!=checked((int)(grid.Nx*grid.Nz))))throw new ArgumentException("Invalid terrain");CheckAbi();grid.Size=56;grid.Version=1;grid.Reserved=0;settings.Size=64;settings.Version=1;var d=new float[n];var t=new float[n];Native.Check(vapor_fidelity_generate_v1(in grid,in settings,time,terrain,(uint)(terrain?.Length??0),d,t,(uint)n));return new FidelityFields(grid,d,t);}
        public static FidelityFrame Render(FidelityFields fields,FidelityCamera camera,FidelityOptics optics,float[] depth=null,float[] radiance=null)
        {if(fields==null)throw new ArgumentNullException(nameof(fields));var grid=fields.Grid;int n=ValidateGrid(grid);if(camera.Width<1||camera.Height<1||camera.Width>1600||camera.Height>1600||camera.Steps<8||camera.Steps>512||(ulong)camera.Width*camera.Height*camera.Steps>180000000)throw new ArgumentOutOfRangeException(nameof(camera));int p=checked((int)(camera.Width*camera.Height));if((depth!=null||radiance!=null)&&(depth==null||radiance==null||depth.Length!=p||radiance.Length!=p*3))throw new ArgumentException("Invalid scene arrays");CheckAbi();grid.Size=56;grid.Version=1;grid.Reserved=0;camera.Size=96;camera.Version=1;optics.Size=200;optics.Version=1;optics.Reserved=0;var rgba=new byte[p*4];var alpha=new float[p];Native.Check(vapor_fidelity_render_v1(in grid,in optics,in camera,fields.Density,fields.Temperature,(uint)n,depth,radiance,(uint)(depth==null?0:p),rgba,(uint)rgba.Length,alpha,(uint)p));return new FidelityFrame(rgba,alpha,camera.Width,camera.Height);}
    }
}
