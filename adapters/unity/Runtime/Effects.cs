using System;
using System.Runtime.InteropServices;
namespace VaporGame
{
    public enum EffectId:uint { CigaretteSmoke=1,ExhaledAerosol=2,CumulusCloud=3,GroundFog=4,Steam=5,Smoke=6,Dust=7,Flame=8 }
    public enum EffectQuality:uint { Low=0,Medium=1,High=2 }
    [StructLayout(LayoutKind.Sequential)] public struct EffectMaterial { public Float3 Colour;public float Extinction,Anisotropy,Albedo,Emission,ThermalFade,Ambient; }
    [StructLayout(LayoutKind.Sequential)] public struct ProceduralSettings {public uint Size,Version,Kind,Seed;public float Coverage,Humidity,Erosion;public Float3 Wind;}
    [StructLayout(LayoutKind.Sequential)] public struct EffectPreset {
        public uint Size,Version,Id,Kind;public Config Config;public Emitter Emitter;public EffectMaterial Material;public ProceduralSettings Procedural;public uint RaySteps,UploadHz,Ember,ProfileCount;public float Duration;
        public static EffectPreset Get(EffectId id,EffectQuality quality=EffectQuality.Medium){Native.Check(EffectNative.vapor_effect_preset_v1((uint)id,(uint)quality,out EffectPreset p,(uint)Marshal.SizeOf<EffectPreset>()));return p;}
        public double[] Profile(){var a=new double[checked((int)ProfileCount*4)];if(a.Length>0)Native.Check(EffectNative.vapor_effect_profile_v1(Id,a,(uint)a.Length));return a;}
    }
    [StructLayout(LayoutKind.Sequential)] public struct EmberVisual {
        public Float3 Colour;public float Intensity,Heat,AshFraction;
        public static EmberVisual At(double time,float progress=0,bool lit=true){Native.Check(EffectNative.vapor_ember_visual_v1(time,progress,lit?1u:0u,out EmberVisual v,(uint)Marshal.SizeOf<EmberVisual>()));return v;}
    }
    internal static class EffectNative {
        [DllImport(Native.Library,CallingConvention=CallingConvention.Cdecl)]internal static extern int vapor_ember_visual_v1(double time,float progress,uint lit,out EmberVisual output,uint bytes);
        [DllImport(Native.Library,CallingConvention=CallingConvention.Cdecl)]internal static extern int vapor_effect_preset_v1(uint id,uint quality,out EffectPreset preset,uint bytes);
        [DllImport(Native.Library,CallingConvention=CallingConvention.Cdecl)]internal static extern int vapor_effect_profile_v1(uint id,[Out]double[] points,uint elements);
        [DllImport(Native.Library,CallingConvention=CallingConvention.Cdecl)]internal static extern int vapor_procedural_atlas_v1(in Config config,in ProceduralSettings settings,double time,[Out]byte[] atlas,uint bytes);
    }
    /// <summary>Game-thread owned local effect. The host controls transform and rendering.</summary>
    public sealed class Effect:IDisposable {
        public EffectPreset Definition{get;}
        public Simulation Runtime{get;}
        public Emitter Source;
        public ProceduralSettings Procedural;
        public double Time{get;private set;}
        public bool Playing{get;private set;}
        public bool Paused{get;set;}
        public int RenderVoxelCount{get;}
        bool closed;
        public Effect(EffectId id,EffectQuality quality=EffectQuality.Medium,BackendOptions? execution=null){
            Definition=EffectPreset.Get(id,quality);Source=Definition.Emitter;Procedural=Definition.Procedural;
            if(Definition.Kind==0){Runtime=execution.HasValue?new Simulation(Definition.Config,execution.Value):new Simulation(Definition.Config);RenderVoxelCount=Runtime.RenderVoxelCount;}
            else{if(execution.HasValue&&((execution.Value.Mode!=BackendMode.Cpu&&execution.Value.Mode!=BackendMode.Auto)||execution.Value.DetailScale!=1||execution.Value.DetailTurbulence!=0))throw new NotSupportedException("Procedural effects use CPU generation");var c=Definition.Config;RenderVoxelCount=checked((int)((ulong)c.Nx*c.Ny*c.Nz));}
        }
        void Check(){if(closed)throw new ObjectDisposedException(nameof(Effect));}
        public void Play(){Check();if(Runtime!=null){Runtime.SetEmitter(0,Source);try{Runtime.SetProfile(0,Definition.Profile(),Definition.ProfileCount>0?Definition.Duration:2,Time,false);}catch{Runtime.RemoveEmitter(0);Playing=false;throw;}}Playing=true;}
        public void Stop(){Check();Runtime?.RemoveEmitter(0);Playing=false;}
        public void Reset(){Stop();Runtime?.Reset();Time=0;}
        public void SetPose(Float3 position,Float3 direction){Check();if(Runtime==null)throw new InvalidOperationException("Use the host volume transform");var e=Source;e.Position=position;e.Direction=direction;if(Playing)Runtime.SetEmitter(0,e);Source=e;}
        public void Advance(double seconds){Check();if(double.IsNaN(seconds)||double.IsInfinity(seconds)||seconds<0||seconds>10)throw new ArgumentOutOfRangeException(nameof(seconds));if(Paused)return;if(Runtime!=null)Time=Runtime.Advance(seconds).SimulatedSeconds;else if(Playing){if(Time+seconds>1e7)throw new InvalidOperationException("Reset procedural clock before 10000000 seconds");Time+=seconds;}}
        public void CopyAtlas(byte[] atlas){Check();if(atlas==null||atlas.Length!=checked(RenderVoxelCount*4))throw new ArgumentException("atlas length mismatch");if(Runtime!=null)Runtime.CopyAtlas(atlas);else{var c=Definition.Config;Native.Check(EffectNative.vapor_procedural_atlas_v1(in c,in Procedural,Time,atlas,(uint)atlas.Length));}}
        public void Dispose(){if(closed)return;closed=true;Runtime?.Dispose();}
    }
}
