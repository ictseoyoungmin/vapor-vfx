"""Canonical shaders/header/binding sources -> distribution copies. --check never writes."""
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
pairs=[(root/'include/vapor.h',root/'adapters/unreal/VaporGame/Source/ThirdParty/Vapor/include/vapor.h'),
       (root/'bindings/dotnet/Vapor.Runtime/Vapor.cs',root/'adapters/unity/Runtime/Vapor.cs')]
pairs.append((root/'include/vapor_atlas_stream.hpp',root/'adapters/unreal/VaporGame/Source/ThirdParty/Vapor/include/vapor_atlas_stream.hpp'))
pairs.append((root/'include/vapor_field_asset.hpp',root/'adapters/unreal/VaporGame/Source/ThirdParty/Vapor/include/vapor_field_asset.hpp'))
pairs.append((root/'include/vapor_effect.hpp',root/'adapters/unreal/VaporGame/Source/ThirdParty/Vapor/include/vapor_effect.hpp'))
pairs.append((root/'bindings/dotnet/Vapor.Runtime/Effects.cs',root/'adapters/unity/Runtime/Effects.cs'))
pairs.append((root/'bindings/dotnet/Vapor.Runtime/Fidelity.cs',root/'adapters/unity/Runtime/Fidelity.cs'))
pairs.append((root/'bindings/dotnet/Vapor.Runtime/FieldAsset.cs',root/'adapters/unity/Runtime/FieldAsset.cs'))
pairs.append((root/'include/vapor_field_sequence.hpp',root/'adapters/unreal/VaporGame/Source/ThirdParty/Vapor/include/vapor_field_sequence.hpp'))
pairs.append((root/'bindings/dotnet/Vapor.Runtime/FieldSequence.cs',root/'adapters/unity/Runtime/FieldSequence.cs'))
for stem in ['field-sequence','field-asset','vapor','gpu','worker-client','effects','gpu-render','gpu-temporal','preview','fidelity','gpu-fidelity','native-fidelity','gpu-field']:
 pairs.append((root/f'bindings/web/{stem}.d.ts',root/f'bindings/web/{stem}.d.mts'))
for src in (root/'shaders').rglob('*'):
 if src.is_file():pairs.append((src,root/'bindings/web/shaders'/src.relative_to(root/'shaders')))
for src,dst in pairs:
 if '--check' in sys.argv:
  if not dst.is_file() or src.read_bytes()!=dst.read_bytes():raise SystemExit(f'FAIL stale distribution copy: {dst.relative_to(root)}')
 else:
  dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(src.read_bytes())
print(f'PASS {len(pairs)} canonical distribution copies')
