"""Shared evidence helpers. A build receipt is provenance, not a runtime PASS."""
from __future__ import annotations
import hashlib, json, platform, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def source_fingerprint()->str:
    files=[ROOT/'Cargo.toml',ROOT/'project.json',ROOT/'tools/build.py',ROOT/'tools/runtime_common.py',ROOT/'effects/presets.json',ROOT/'tools/generate_effects.py']
    files+=sorted((ROOT/'crates').rglob('*.rs'))+sorted((ROOT/'crates').rglob('Cargo.toml'))
    files+=sorted((ROOT/'shaders').rglob('*'))
    h=hashlib.sha256()
    for path in sorted(set(files)):
        if path.is_file():
            h.update(path.relative_to(ROOT).as_posix().encode());h.update(b'\0')
            h.update(path.read_bytes());h.update(b'\0')
    return h.hexdigest()

def library_name()->str:
    return {'Windows':'vapor.dll','Darwin':'libvapor.dylib','Linux':'libvapor.so'}[platform.system()]

def default_library()->Path:return ROOT/'dist/native'/library_name()

def receipt_path(artifact:Path)->Path:return artifact.with_name(artifact.name+'.build.json')

def write_receipt(artifact:Path,*,features:list[str],command:list[str],rustc:str)->None:
    data={'schema':'vapor.build-receipt/1','sdk_version':json.loads((ROOT/'project.json').read_text())['sdk_version'],'artifact':artifact.name,
          'artifact_sha256':sha256(artifact),'source_fingerprint':source_fingerprint(),
          'features':features,'command':command,'rustc':rustc,'host':platform.platform(),
          'notice':'Actual Rust compiler output. This receipt is not evidence of successful runtime tests.'}
    receipt_path(artifact).write_text(json.dumps(data,indent=2)+'\n')

def require_receipt(artifact:Path,*,gpu:bool=False)->dict:
    if not artifact.is_file():raise FileNotFoundError(f'Actual Rust artifact missing: {artifact}')
    receipt=receipt_path(artifact)
    if not receipt.is_file():raise RuntimeError(f'Build receipt missing: {receipt}; build with tools/build.py')
    data=json.loads(receipt.read_text())
    if data.get('schema')!='vapor.build-receipt/1':raise RuntimeError('Unknown build receipt')
    if data.get('artifact_sha256')!=sha256(artifact):raise RuntimeError('Artifact hash differs from its build receipt')
    if data.get('source_fingerprint')!=source_fingerprint():raise RuntimeError('Artifact was built from different sources; rebuild before validation')
    if gpu and 'gpu' not in data.get('features',[]):raise RuntimeError('GPU/Hybrid validation requires a GPU-feature native build')
    return data


def clear_previous_outputs(directory:Path,names:list[str])->None:
    """Remove only explicitly owned report files so a blocked rerun cannot show old shots."""
    for name in names:
        if not name or Path(name).name != name or name in ('.','..'):
            raise ValueError('Output cleanup requires plain file names')
    for name in names:
        path=directory/name
        if path.is_file() or path.is_symlink():path.unlink()
