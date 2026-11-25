#!/usr/bin/env python3
"""Build actual Rust artifacts, with a registry-independent CPU workspace.

CPU compilation still requires an installed Rust compiler and platform linker.
No downloads, mock runtimes, or alternative-language solvers are substituted.
"""
from __future__ import annotations
import argparse,json,os,platform,shutil,subprocess,sys,tomllib
from pathlib import Path
from runtime_common import ROOT,library_name,write_receipt

def run(args,*,env=None):
    command=list(map(str,args));print('+',' '.join(command),flush=True)
    subprocess.run(command,cwd=ROOT,check=True,env={**os.environ,**(env or {})})
    return command

def copy(source:Path,dest:Path):
    if not source.is_file():raise FileNotFoundError(source)
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    print('STAGED',dest.relative_to(ROOT))

def cpu_workspace()->Path:
    """Generated manifests point at unchanged source files; no source copies can drift."""
    base=ROOT/'target/cpu-workspace';base.mkdir(parents=True,exist_ok=True)
    meta=tomllib.loads((ROOT/'Cargo.toml').read_text())['workspace']['package']
    root='[workspace]\nmembers = ["vapor-core", "vapor-backend", "vapor-ffi"]\nresolver = "2"\n'
    root+='\n[profile.release]\nlto = "thin"\ncodegen-units = 1\n'
    (base/'Cargo.toml').write_text(root)
    for name in ['vapor-core','vapor-backend','vapor-ffi']:
        original=ROOT/'crates'/name;out=base/name;out.mkdir(exist_ok=True)
        text='[package]\nname = '+json.dumps(name)+'\n'
        for key in ['version','edition','rust-version']:text+=key+' = '+json.dumps(meta[key])+'\n'
        text+='autotests = false\nautoexamples = false\n[lib]\n'
        text+='name = '+json.dumps('vapor' if name=='vapor-ffi' else name.replace('-','_'))+'\n'
        text+='path = '+json.dumps((original/'src/lib.rs').as_posix())+'\n'
        if name=='vapor-ffi':text+='crate-type = ["cdylib", "staticlib", "rlib"]\n'
        # Declare cfg names for check-cfg, without enabling any GPU feature/dependency.
        text+='[features]\ndefault = []\ngpu = []\n'
        if name!='vapor-core':
            text+='[dependencies]\nvapor-core = { path = "../vapor-core" }\n'
        if name=='vapor-ffi':text+='vapor-backend = { path = "../vapor-backend" }\n'
        for test in sorted((original/'tests').glob('*.rs')):
            if test.name=='gpu_runtime.rs':continue
            text+='\n[[test]]\nname = '+json.dumps(test.stem)+'\npath = '+json.dumps(test.as_posix())+'\n'
        for example in sorted((original/'examples').glob('*.rs')):
            text+='\n[[example]]\nname = '+json.dumps(example.stem)+'\npath = '+json.dumps(example.as_posix())+'\n'
        (out/'Cargo.toml').write_text(text)
    return base/'Cargo.toml'

def stage(lib:Path,system:str):
    unity=ROOT/'adapters/unity/Runtime/Plugins'/('macOS' if system=='Darwin' else 'x86_64')
    copy(lib,unity/lib.name);copy(lib,ROOT/'adapters/godot/project/bin'/lib.name)
    ue=ROOT/'adapters/unreal/VaporGame';name={'Windows':'Win64','Linux':'Linux','Darwin':'Mac'}[system]
    copy(lib,ue/'Binaries/ThirdParty'/name/lib.name)
    copy(ROOT/'include/vapor.h',ue/'Source/ThirdParty/Vapor/include/vapor.h')
    if system=='Windows':copy(lib.with_name('vapor.dll.lib'),ue/'Source/ThirdParty/Vapor/Win64/vapor.dll.lib')

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['native','web','stage-adapters','test','gpu','offline']:ap.add_argument('--'+name,action='store_true')
    args=ap.parse_args()
    if not(args.native or args.web or args.test):ap.error('select --native, --web or --test')
    if args.stage_adapters and not args.native:ap.error('--stage-adapters requires --native')
    if not shutil.which('cargo') or not shutil.which('rustc'):
        print('BLOCKED: cargo/rustc absent. Install Rust 1.88+. For web also install wasm32-unknown-unknown. No runtime created.',file=sys.stderr)
        return 2
    try:
        run([sys.executable,'tools/generate_effects.py','--check'])
        rustc=subprocess.check_output(['rustc','--version'],text=True).strip()
        cpu_manifest=cpu_workspace();cpu_target=ROOT/'target/cpu'
        cpu=['--manifest-path',str(cpu_manifest),'--target-dir',str(cpu_target),'--offline']
        gpu=['--manifest-path',str(ROOT/'Cargo.toml'),'--target-dir',str(ROOT/'target/gpu')]
        if args.offline:gpu+=['--offline']
        if args.test:
            run(['cargo','test','--release','--workspace']+cpu)
            if args.gpu:run(['cargo','test','--release','--workspace','--features','vapor-ffi/gpu']+gpu)
        if args.native:
            command=run(['cargo','build','--release','-p','vapor-ffi']+(['--features','gpu']+gpu if args.gpu else cpu))
            source=(ROOT/'target/gpu' if args.gpu else cpu_target)/'release'/library_name()
            lib=ROOT/'dist/native'/library_name();copy(source,lib)
            if platform.system()=='Windows':copy(source.with_name('vapor.dll.lib'),lib.with_name('vapor.dll.lib'))
            write_receipt(lib,features=['cpu','gpu'] if args.gpu else ['cpu'],command=command,rustc=rustc)
            if args.stage_adapters:
                if platform.system()!='Darwin' and platform.machine().lower() not in ('amd64','x86_64'):
                    raise RuntimeError('Default desktop adapter manifests are x86_64 only; custom target packaging required')
                stage(lib,platform.system())
        run([sys.executable,'tools/sync_distribution.py','--check'])
        if args.web:
            command=run(['cargo','build','--release','-p','vapor-ffi','--target','wasm32-unknown-unknown']+cpu)
            wasm=ROOT/'bindings/web/vapor.wasm'
            copy(cpu_target/'wasm32-unknown-unknown/release/vapor.wasm',wasm)
            write_receipt(wasm,features=['cpu','wasm'],command=command,rustc=rustc)
        print('Built actual Rust artifacts. Engine SDK/editor execution remains separate.')
        return 0
    except (subprocess.CalledProcessError,OSError,RuntimeError) as exc:
        print('FAIL:',exc,file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
