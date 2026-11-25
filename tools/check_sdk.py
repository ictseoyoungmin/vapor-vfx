#!/usr/bin/env python3
"""Source/boundary checks plus real Rust runtime gates. A test double is never a runtime PASS."""
from __future__ import annotations
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
PROJECT=json.loads((ROOT/'project.json').read_text())

def runtime_required(cpu:bool,gpu:bool,wasm:bool)->bool:
    # An explicitly requested accelerator/runtime must never exit success on BLOCKED.
    return cpu or gpu or wasm

def atomic_report(path:Path,report:dict)->None:
    """Keep the previous checkpoint or the complete new JSON, never partial JSON."""
    path.parent.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.validation-',suffix='.tmp',delete=False) as f:
            name=f.name;json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush()
        os.replace(name,path)
    finally:
        if name is not None and os.path.exists(name):os.unlink(name)

def incomplete_report(checks:dict,*,cpu:bool,gpu:bool,wasm:bool,active:str|None=None)->dict:
    return {'schema':'vapor.game-sdk.validation/5','distribution_version':PROJECT['distribution_version'],'sdk_version':PROJECT['sdk_version'],'fidelity_lab_version':PROJECT['lab_version'],
            'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'complete':False,'status':'IN_PROGRESS','active_check':active,
            'runtime_required':runtime_required(cpu,gpu,wasm),'gpu_runtime_requested':gpu,'wasm_runtime_requested':wasm,
            'source_checks_passed':False,'core_release_gates_passed':False,
            'cpu_runtime_gates_passed':False,'gpu_runtime_gates_passed':False,'production_release_ready':False,
            'notice':'Incomplete report; previous or interrupted results never certify a runtime. Rerun check_sdk.py.',
            'checks':checks}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-runtime',action='store_true',help='Require actual native CPU tests; GPU/WASM are required only when separately requested')
    parser.add_argument('--gpu-runtime',action='store_true',help='Run a real native GPU path; missing adapter is a failure, never a CPU substitution')
    parser.add_argument('--wasm-runtime',action='store_true',help='Also build/test actual Rust CPU WASM')
    parser.add_argument('--lab',action='store_true',help='Also execute independent Lab tests (NumPy/SciPy required)')
    parser.add_argument('--legacy',action='store_true',help='Require original v18 re-audit from optional history/legacy/v18')
    parser.add_argument('--source-only',action='store_true',help='Explicitly omit runtime builds, never count them as PASS')
    parser.add_argument('--allow-software',action='store_true',help='Allow and report a software GPU adapter')
    args=parser.parse_args()
    if args.source_only and (args.require_runtime or args.gpu_runtime or args.wasm_runtime):
        parser.error('--source-only cannot satisfy runtime flags')
    checks={};report_path=ROOT/'reports/validation-current.json'
    def checkpoint(active=None):
        atomic_report(report_path,incomplete_report(checks,cpu=args.require_runtime,gpu=args.gpu_runtime,wasm=args.wasm_runtime,active=active))
    checkpoint()
    def blocked(key,reason):
        checks[key]={'status':'BLOCKED','reason':reason}
        checkpoint();print('BLOCKED',key,flush=True)
    def run(key,command,env=None,timeout=120,evidence='source-contract'):
        command=list(map(str,command));checkpoint(key)
        try:
            p=subprocess.run(command,cwd=ROOT,env={**os.environ,**(env or {})},capture_output=True,text=True,timeout=timeout)
            output=p.stdout+p.stderr
            checks[key]={'status':'PASS' if p.returncode==0 else 'BLOCKED' if p.returncode==2 and key.startswith('real_') else 'FAIL','evidence':evidence,'command':command,'returncode':p.returncode,'output':output[-16000:]}
            count=re.search(r'^# tests (\d+)\s*$',output,re.M) or re.search(r'Ran (\d+) tests?',output)
            if count:checks[key]['test_count']=int(count.group(1))
        except (OSError,subprocess.TimeoutExpired) as error:
            checks[key]={'status':'BLOCKED' if isinstance(error,FileNotFoundError) else 'FAIL','evidence':evidence,'reason':str(error)}
        checkpoint();print(checks[key]['status'],key,flush=True)
        return checks[key]['status']=='PASS'

    if args.legacy:
        run('legacy_source_hashes',[sys.executable,'tools/freeze_contract.py','--check'])
        run('legacy_static_checks',[sys.executable,'history/legacy/v18/tests/verify.py'])
        run('original_js_pchip_156_vectors',['node','tools/generate_pchip_fixtures.mjs','--check'])
    run('field_asset_python',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_field_asset.py','-v'],evidence='actual VPF1 decoding/roundtrip; not Rust execution')
    run('field_sequence_python',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_field_sequence.py','-v'],evidence='actual Python VPA decode/interpolation/cache/CRC')
    run('field_sequence_js',['node','--test','tests/field-sequence.test.mjs'],evidence='actual JS VPA playback plus explicit GPU host test double')
    run('cloud_mesh_glb_js',['node','--test','tests/cloud-mesh.test.mjs'],evidence='actual VPF1 static GLB extraction, topology, LOD and material checks')
    run('field_asset_js',['node','--test','tests/field-asset.test.mjs'],evidence='actual JS VPF1 decoder/encoder')
    run('stage1_contract_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_contract.py','-v'])
    run('runtime_tool_self_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_runtime_tools.py','-v'],evidence='tool/provenance/PNG self-tests, NOT Rust runtime')
    run('cloud_equivalence_and_package_guards',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_cloud_equivalence.py','-v'],evidence='numeric comparison and fail-closed packaging controls, not Rust runtime')
    run('resolved_runtime_tool_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_resolved_runtime_tools.py','-v'],evidence='runtime report/PPM boundary only; no Rust execution')
    run('temporal_projection_math',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_temporal_math.py','-v'],evidence='independent CPU camera packet / normalized FP16 anchor math; NOT WGSL execution')
    run('detail_curl_math',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_detail_curl_math.py','-v'],evidence='independent CPU math for bounded tapered curl, NOT WGSL execution')
    run('quality_metric_self_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_quality_metrics.py','-v'],evidence='independent field diagnostics and timing/gate self-tests, not Rust runtime')
    run('emitter_kernel_audit',[sys.executable,'tools/audit_emitter.py'],evidence='independent NumPy source quadrature; NOT Rust/WGSL runtime')
    run('effect_catalog_generated',[sys.executable,'tools/generate_effects.py','--check'])
    run('effect_procedural_fixtures',['node','tools/generate_effects_fixtures.mjs','--check'],evidence='actual JS atlas replay; Rust comparison separate')
    run('effect_python_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_effects.py','-v'],evidence='catalog/recipe/ABI boundary; not native fluid execution')
    run('effect_cpp_layout',['g++','-std=c++17','-Wall','-Wextra','-Werror','-Iinclude','-fsyntax-only','tests/effects_layout.cpp'])
    run('fidelity_port_golden_replay',['node','tools/generate_fidelity_port_fixtures.mjs','--check'],evidence='Actual JS golden fields/optics, not Rust execution')
    run('fidelity_port_host_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_fidelity_port.py','-v'],evidence='ctypes layout; not native runtime')
    run('fidelity_c_header_layout',['gcc','-std=c11','-Wall','-Wextra','-Werror','-Iinclude','-fsyntax-only','tests/fidelity_layout.c'])
    run('python_syntax',[sys.executable,'-m','compileall','-q','bindings/python','examples/python','tools','lab'])
    scripts=sorted([*ROOT.glob('bindings/web/*.mjs'),*ROOT.glob('adapters/three/*.mjs'),*ROOT.glob('examples/**/*.mjs'),*ROOT.glob('tools/*.mjs'),*ROOT.glob('lab/*.mjs')])
    for path in scripts:
        rel=str(path.relative_to(ROOT))
        run('js_syntax_'+rel.replace('/','_'),['node','--check',rel])
    suites={
        'procedural_full_atlas_parity':('tests/procedural-parity.test.mjs','actual JS CPU atlas, full buffer hashes recorded from 0.8'),
        'temporal_reprojection_tests':('tests/reprojection.test.mjs','actual JS CPU optical-layer reprojection and prior preview parity; not native fluid or GPU'),
        'high_fidelity_reference_tests':('tests/fidelity.test.mjs','actual Float32 CPU density and optical tests; NOT native fluid or GPU'),
        'scene_depth_float_tests':('tests/scene-depth.test.mjs','actual JS CPU analytic optics and field precision, NOT Rust/GPU execution'),
        'atlas_preview_tests':('tests/atlas-preview.test.mjs','actual JS procedural atlas + CPU raymarch, not native fluid execution'),
        'effect_js_tests':('tests/effects.test.mjs','actual CPU procedural atlas/preview; fluid lifecycle only uses an explicit test double'),
        'gpu_protocol_tests':('tests/gpu-protocol.test.mjs','control-and-wire; no WGSL execution'),
        'gpu_host_tests':('tests/gpu-host.test.mjs','GPU device test double; no WGSL execution'),
        'gpu_readback_pool_tests':('tests/readback-pool.test.mjs','stateful GPU transfer test double; no hardware timing'),
        'worker_lifecycle_tests':('tests/worker-client.test.mjs','Worker transport test double; real client lifecycle'),
    }
    for key,(path,evidence) in suites.items():run(key,['node','--test',path],evidence=evidence)
    run('wgsl_reserved_word_preflight',[sys.executable,'tools/check_wgsl_source.py'],evidence='lexical preflight; NOT WGSL compilation')
    run('wgsl_lexical_guard_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_shader_source.py','-v'],evidence='lexical guard self-tests; NOT WGSL compilation')
    run('gpu_schedule_generated',[sys.executable,'tools/generate_passes.py','--check'])
    run('distribution_copies',[sys.executable,'tools/sync_distribution.py','--check'])
    run('typescript_api',['tsc','-p','tests/tsconfig.json'])
    with tempfile.TemporaryDirectory(prefix='vapor-abi-test-') as tmp:
        t=Path(tmp);native=t/'libfixture.so';wasm=t/'fixture.wasm'
        if run('cpp_field_sequence_build',['g++','-std=c++17','-Wall','-Wextra','-Werror','-Iinclude','tests/field_sequence.cpp','-o',t/'field-sequence']):
            run('cpp_field_sequence_execute',[t/'field-sequence',ROOT/'fixtures/field-sequence'],evidence='actual C++17 VPA player, not Rust/engine')
        if run('cpp_field_asset_build',['g++','-std=c++17','-Wall','-Wextra','-Werror','-Iinclude','tests/field_asset.cpp','-o',t/'field-asset']):
            run('cpp_field_asset_execute',[t/'field-asset',ROOT/'fixtures/field-asset.vpf'],evidence='actual C++17 VPF1 data-only reader; not native Rust or game editor')
        if run('c_header_layout_build',['gcc','-std=c11','-Wall','-Wextra','-Werror','-Iinclude','tests/abi_layout.c','-o',t/'layout']):
            run('c_header_layout_execute',[t/'layout'])
        run('cpp_header_layout',['g++','-std=c++17','-Wall','-Wextra','-Werror','-Iinclude','-x','c++','-fsyntax-only','tests/abi_layout.c'])
        if run('c_test_double_build',['gcc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-Iinclude','tests/ffi_fixture.c','-o',native],evidence='C ABI test double only'):
            run('python_abi_boundary_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_bindings.py','-v'],{'VAPOR_TEST_FIXTURE_LIBRARY':str(native)},evidence='C fixture, not Rust')
            if run('cpp_atlas_stream_build',['g++','-std=c++17','-Wall','-Wextra','-Werror','-Iinclude','tests/atlas_stream.cpp',native,'-o',t/'atlas_stream']):
                run('cpp_atlas_stream_lifecycle',[t/'atlas_stream'],evidence='C++ helper against explicit C fixture; not engine or Rust execution')
        else:blocked('python_abi_boundary_tests','C fixture build unavailable/failed')
        if run('wasm_c_test_double_build',['clang','--target=wasm32','-O0','-nostdlib','-fno-builtin','-Iinclude','tests/ffi_fixture.c','-Wl,--no-entry','-Wl,--export-all','-Wl,--export-memory','-Wl,--initial-memory=262144','-o',wasm],evidence='C/WASM ABI test double only'):
            run('javascript_abi_boundary_tests',['node','--test','tests/web-binding.test.mjs'],{'VAPOR_TEST_FIXTURE_WASM':str(wasm)},evidence='C/WASM fixture, not Rust')
        else:blocked('javascript_abi_boundary_tests','C/WASM fixture build unavailable/failed')
    run('project_layout',[sys.executable,'tools/verify_layout.py'])
    if args.lab:run('lab_optical_calibration',['node','--test','lab/tests/optical-calibration.test.mjs'],evidence='actual Beer-Lambert authoring math, not microphysical validation')
    if args.lab:run('lab_tests',[sys.executable,'-m','unittest','discover','-s','lab/tests','-v'],evidence='independent research, not SDK runtime')
    source_keys=list(checks)
    if not args.lab:checks['lab_tests']={'status':'NOT_RUN','reason':'Optional independent research suite: --lab'}
    if not args.legacy:
        for k in ('legacy_source_hashes','legacy_static_checks','original_js_pchip_156_vectors'):
            checks[k]={'status':'NOT_RUN','reason':'Optional archive re-audit: extract companion history ZIP and pass --legacy. Frozen fixtures retained.'}
    runtime_keys=['real_rust_cpu_runtime','real_native_fidelity']
    if args.gpu_runtime:runtime_keys.append('real_gpu_hybrid_runtime')
    if args.wasm_runtime:runtime_keys+=['real_rust_wasm_build','real_rust_wasm_node_smoke','real_rust_wasm_fidelity']
    if args.source_only:
        for key in runtime_keys:checks[key]={'status':'NOT_RUN','reason':'Explicit --source-only; no runtime success claimed'}
    else:
        cpu_ok=run('real_rust_cpu_runtime',[sys.executable,'tools/validate_runtime.py','--build','--modes','cpu','--capture'],
            timeout=1800,evidence='actual Rust CPU + C ABI required; missing compiler fails closed')
        if cpu_ok:run('real_native_fidelity',[sys.executable,'tools/validate_native_fidelity.py','--capture'],timeout=600,evidence='actual Rust generator and optics via C ABI against JS golden fields')
        else:blocked('real_native_fidelity','Native Rust CPU build/test gate did not pass')
        if args.gpu_runtime:
            run('real_gpu_hybrid_runtime',[sys.executable,'tools/validate_runtime.py','--build','--modes','gpu','hybrid','--capture']+
                (['--allow-software'] if args.allow_software else []),timeout=2400,
                evidence='actual WGSL/GPU and one-way Hybrid; CPU substitution forbidden')
        else:checks['real_gpu_hybrid_runtime']={'status':'NOT_RUN','reason':'GPU is separate; use supplied validation script on the target PC'}
        if args.wasm_runtime:
            built=run('real_rust_wasm_build',[sys.executable,'tools/build.py','--web'],timeout=600,evidence='actual Rust CPU WASM')
            if built:
                run('real_rust_wasm_node_smoke',['node','examples/node/smoke.mjs'],timeout=600,evidence='actual Rust WASM execution')
                run('real_rust_wasm_fidelity',[sys.executable,'tools/validate_wasm_fidelity.py'],timeout=600,evidence='actual Rust WASM Fidelity parity; no JS fallback')
            else:
                blocked('real_rust_wasm_node_smoke','WASM build did not pass')
                blocked('real_rust_wasm_fidelity','WASM build did not pass')
        else:checks['real_rust_wasm_node_smoke']={'status':'NOT_RUN','reason':'Optional separate CPU WASM test; use --wasm-runtime'}
    for engine in ['unity','godot','unreal']:
        checks[engine+'_editor_integration']={'status':'NOT_RUN','reason':'No engine SDK/editor execution; not a required all-platform test matrix.'}
    checks['browser_visual_gpu']={'status':'NOT_RUN','reason':'Not required for CPU gate. tools/capture_cpu.py captures actual CPU WASM separately.'}
    checks['v18_full_visual_numerical_parity']={'status':'NOT_ESTABLISHED','reason':'New MAC/detail paths are not proven equivalent to all v18 numerics, lighting and temporal rendering.'}
    checks['hardware_game_frame_cost']={'status':'NOT_RUN','reason':'Transfer test-double allocation counts are not GPU timings or game FPS.'}
    report={
        'schema':'vapor.game-sdk.validation/5','distribution_version':PROJECT['distribution_version'],'sdk_version':PROJECT['sdk_version'],'fidelity_lab_version':PROJECT['lab_version'],'complete':True,
        'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'runtime_required':runtime_required(args.require_runtime,args.gpu_runtime,args.wasm_runtime),'gpu_runtime_requested':args.gpu_runtime,'wasm_runtime_requested':args.wasm_runtime,
        'cpu_runtime_gates_passed':all(checks.get(k,{}).get('status')=='PASS' for k in ['real_rust_cpu_runtime','real_native_fidelity']),
        'gpu_runtime_gates_passed':checks.get('real_gpu_hybrid_runtime',{}).get('status')=='PASS',
        'production_release_ready':False,
        'source_checks_passed':all(checks[k]['status']=='PASS' for k in source_keys),
        'source_test_count':sum(checks[k].get('test_count',0) for k in source_keys),
        'core_release_gates_passed':all(checks[k]['status']=='PASS' for k in runtime_keys),
        'any_check_failed':any(v['status']=='FAIL' for v in checks.values()),
        'boundary_fixture_notice':'C/WASM fixture, GPU host/readback doubles and Worker transport double do not execute the Rust/WGSL fluid solver. Never shipped as runtimes.',
        'checks':checks,
    }
    report['status']='PASS' if report['core_release_gates_passed'] and report['source_checks_passed'] else 'FAIL' if report['any_check_failed'] or not report['source_checks_passed'] else 'INCOMPLETE_RUNTIME'
    atomic_report(report_path,report)
    print('REPORT',report_path)
    return int(report['any_check_failed'] or not report['source_checks_passed'] or
               (runtime_required(args.require_runtime,args.gpu_runtime,args.wasm_runtime) and not report['core_release_gates_passed']))
if __name__=='__main__':raise SystemExit(main())
