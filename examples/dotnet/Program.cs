using VaporGame;
var cfg=Config.Default;cfg.Nx=12;cfg.Ny=16;cfg.Nz=12;cfg.CellSize=.05f;
using var sim=new Simulation(cfg);
var emitter=Emitter.Default;emitter.Position=new Float3(.3f,.1f,.3f);sim.SetEmitter(0,emitter);sim.Step(60);
var metrics=sim.Metrics();
Console.WriteLine($"profile=game-mac-v1 time={metrics.Time:F3} integral={metrics.DensityIntegral:G9} nonfinite={metrics.NonFinite}");
// Actual native Fidelity calls only. No independent JS/Python fallback.
if(args.Contains("--fidelity")) {
    var grid=new FidelityGrid(32,16,24,new Double3(48,24,36));
    var settings=FidelityDensity.For(FidelityKind.Cloud,43);
    settings.Coverage=.53;settings.Humidity=.76;settings.Erosion=.23;settings.Wind=new Double3(.6,0,.22);
    var volume=FidelityCPU.Generate(grid,settings);
    if(!volume.Density.Any(x=>x>0)||volume.Density.Any(x=>float.IsNaN(x)||float.IsInfinity(x)))throw new Exception("Invalid native density");
    var camera=FidelityCamera.LookAt(new Double3(30,8,-50),new Double3(24,12,18),96,60,64);
    var frame=FidelityCPU.Render(volume,camera,FidelityOptics.Default);
    if(!frame.Alpha.Any(x=>x>0)||frame.Alpha.Any(x=>float.IsNaN(x)||x<0||x>1))throw new Exception("Invalid native image");
    File.WriteAllBytes("native-cloud.rgba",frame.Rgba);
    Console.WriteLine("Native Fidelity CPU output: native-cloud.rgba (96x60 RGBA8)");
}
