#!/usr/bin/env python3
"""Check active path ownership, migration map and version consistency."""
from pathlib import Path
import json,re,tomllib
ROOT=Path(__file__).resolve().parents[1]
def verify():
    project=json.loads((ROOT/'project.json').read_text())
    assert project['sdk_version']==tomllib.loads((ROOT/'Cargo.toml').read_text())['workspace']['package']['version']
    assert project['bindings']['web']==json.loads((ROOT/'bindings/web/package.json').read_text())['version']
    assert project['unity_adapter_version']==json.loads((ROOT/'adapters/unity/package.json').read_text())['version']
    assert f"<Version>{project['bindings']['dotnet']}</Version>" in (ROOT/'bindings/dotnet/Vapor.Runtime/Vapor.Runtime.csproj').read_text()
    assert project['bindings']['python']==tomllib.loads((ROOT/'bindings/python/pyproject.toml').read_text())['project']['version']
    assert project['production_release_ready'] is False
    mapping=json.loads((ROOT/'docs/MIGRATION_MAP.json').read_text())['moved']
    for old,new in mapping.items():
        assert not (ROOT/old).exists(), f'stale research duplicate {old}'
        assert (ROOT/new).is_file(), f'missing migrated tool {new}'
    for directory in ['crates','bindings','adapters']:
        for p in (ROOT/directory).rglob('*'):
            if p.suffix not in ['.py','.rs','.mjs','.cs','.toml','.cpp','.h']:continue
            s=p.read_text(encoding='utf-8')
            assert not re.search(r'(?m)^\s*(?:from|import)\s+(?:reference_fluid|reference_detail|resolved_source_lab|conservative_transport|lab)(?:\s|\.)',s),f'research dependency {p}'
            assert not re.search(r'(?m)^\s*(?:import|export).*?[\'\"](?:\.\./)+lab/',s),f'research import {p}'
    for p in [ROOT/'README.md',*list((ROOT/'docs').glob('*.md')),ROOT/'lab/README.md']:
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if ':' in target or target.startswith('#'):continue
            file=(p.parent/target.split('#')[0]).resolve()
            if file==ROOT/'reports/validation-current.json':continue
            assert file.exists(),f'broken active doc link {p}: {target}'
    print(f'PASS layout: {len(mapping)} migrated scripts; version, active docs, product dependency boundaries')
if __name__=='__main__':verify()
