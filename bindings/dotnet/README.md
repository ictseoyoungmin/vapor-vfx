# .NET / C# wrapper

Build the native Rust library first (`python tools/build.py --native`). Build `Vapor.Runtime/Vapor.Runtime.csproj` with a .NET SDK supporting .NET Standard 2.1, or include `Vapor.cs` in the host engine assembly. Native library must be discoverable by the process loader: executable directory or an explicitly configured loader path; Python's `VAPOR_LIBRARY` variable does not configure .NET.

`Vapor.Runtime` uses only P/Invoke, blittable structs and SafeHandle. No NuGet dependency. ABI errors throw `VaporException`, whose `Code` preserves the native status. Types and buffers are explicit; Float3 uses three f32 values, not System.Numerics packing assumptions. Close/Dispose is idempotent. Unit tests for .NET are not reported as run.

The example is `examples/dotnet/Smoke.csproj` (net8.0). The Unity adapter carries a byte-identical copy of Vapor.cs; `check_sdk.py` verifies that copies do not diverge.

0.8: `TryBeginAtlas(out AtlasTicket)` / `TryPollAtlas(ticket, byte[])` / `CancelAtlas(ticket)` expose bounded ticketed native snapshots. `false` means busy or pending respectively. The output is consumed once and reset invalidates tickets. CPU is immediately ready; GPU/Hybrid only copy ready mapped data. Native 0.8 library required for these calls. .NET compile/execution not verified.
