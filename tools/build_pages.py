#!/usr/bin/env python3
"""Build a curated static Pages artifact. Never publish native/WASM binaries or scratch logs."""
from __future__ import annotations
import argparse, html, json, re, shutil, tempfile
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
ASSET_GROUPS = {
    'airborne-smoke': ['manifest.json', 'smoke-0040.vpf', 'smoke-0056.vpf', 'smoke-0080.vpf'],
    'cloud-motion': ['sequence.vpa', 'asset.json', 'motion.json', *[f'frame_{i:04}.vpf' for i in range(25)]],
    'field-assets': ['cloud.vpf', 'cloud.json', 'fog.vpf', 'fog.json'],
}
PAGES = {'index.html':'Overview','examples.html':'Examples','guide.html':'Guide','status.html':'Status'}
ICON = '<svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M3 19C9 19 9 7 15 7s5 12 11 12h3M3 25c6 0 6-12 12-12s5 12 11 12h3M3 13c5 0 6-10 12-10 5 0 6 10 11 10h3" stroke="#9ddce0" stroke-width="2" stroke-linecap="round"/></svg>'
DIAGRAM = '<div class="diagram" aria-hidden="true"><svg viewBox="0 0 120 80" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M15 25 59 7l46 20-45 20zM15 25v30l45 18 45-19V27M60 47v26M36 17l46 20M81 17 37 36M15 40l45 19 45-18M37 36v28M82 37v27"/><circle cx="60" cy="46" r="8" fill="currentColor" opacity=".3"/></svg></div>'

def esc(s): return html.escape(str(s), quote=True)

def read_json(p): return json.loads(p.read_text(encoding='utf-8'))

def available_assets(mode):
    result = {}
    for group, files in ASSET_GROUPS.items():
        present = all((ROOT/'assets'/group/name).is_file() for name in files)
        if mode == 'full' and not present:
            raise ValueError(f'missing complete asset group: {group}; use the full SDK or --assets auto')
        result[group] = present and mode != 'none'
    return result

def copy_file(source, destination):
    if source.is_symlink() or not source.is_file(): raise ValueError(f'not a regular source file: {source}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)

def card(item, groups):
    hosted = item['group'] != 'local' and (not item.get('asset') or groups[item['asset']])
    picture = f'<img src="{esc(item["image"])}" alt="Actual project preview for {esc(item["title"])}" loading="lazy">' if item.get('image') else DIAGRAM
    link = (f'<a class="action" href="{esc(item["route"])}">{esc(item["action"])} →</a>' if hosted else f'<p class="not-hosted">{ "Requires the full asset package." if item.get("asset") else "Run from the local SDK." } <a href="guide.html#quickstart">Setup →</a><br><code>{esc(item["route"])}</code></p>')
    return f'<article class="demo"><div class="demo-media">{picture}</div><div class="demo-content"><span class="kind">{esc(item["kind"])}</span><h3>{esc(item["title"])}</h3><p>{esc(item["desc"])}</p><div class="test">{esc(item["status"])}</div>{link}</div></article>'

def layout(name, body, project):
    links = ''.join('<a href="{}"{}>{}</a>'.format(p, ' aria-current="page"' if p == name else '', label) for p,label in PAGES.items())
    v = esc(project['distribution_version']); sdk = esc(project['sdk_version'])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="Vapor experimental volumetric effects SDK and Fidelity Lab. Actual examples, integration guides and verification status."><meta name="color-scheme" content="dark"><title>Vapor — {PAGES[name]}</title><link rel="stylesheet" href="styles.css"></head><body><a class="skip" href="#main">Skip to content</a><header class="site-header"><nav class="nav" aria-label="Main navigation"><a class="brand" href="index.html">{ICON}Vapor</a><div class="links">{links}</div><span class="version">v{v} · preview</span></nav></header><main id="main" class="wrap">{body}</main><footer><div class="wrap"><span>Vapor · distribution {v} / core {sdk}</span><span>Research & source preview · <a href="status.html">Verification and rights</a></span></div></footer><script src="site.js" defer></script></body></html>'''

def hosted_example(page, original, groups):
    # Keep the actual render / simulation modules untouched. Public variants expose only
    # prerequisites available in this artifact and do not navigate to optional history.
    if page == 'interactive-cloud':
        original = original.replace('href="../index.html"', 'href="../../examples.html"')
    if page == 'airborne-smoke' and not groups['airborne-smoke']:
        original = original.replace('<a style="color:#9bc6e8" href="inspect.html">3D 볼륨 검사기</a>', '3D 볼륨 검사기(전체 SDK 필요)')
    if page == 'high-fidelity':
        original = re.sub(r'<option value="(?:cigarette_smoke|exhaled_aerosol)">.*?</option>', '', original)
        original = original.replace('<option value="medium">Medium</option>', '<option value="medium" selected>Medium</option>').replace('<option value="detail" selected>Fine detail (fluid snapshot)</option>', '')
        original = original.replace('Smoke and aerosol use calculated snapshots from the independent CPU reference solver, not native runtime output. Fluid snapshot files require the optional history archive.', 'This hosted viewer exposes procedural clouds and terrain fog. Archived fluid snapshots are available only in a local SDK with optional history.')
        original = re.sub(r'<p><a href="../../history/.*?</p>', '<p><a href="../../examples.html">Back to example gallery</a></p>', original, flags=re.S)
        # Preserve the element used by the module, but hide the local-only control.
        original = original.replace('<label>Fluid optics<select', '<label style="display:none">Fluid optics<select')
    if page == 'fidelity-cloud':
        original = original.replace('<option value="rust">Rust WASM (requires build)</option>', '<option value="rust" disabled>Rust WASM (local build only)</option>').replace('<option value="js">JS reference (explicit)</option>', '<option value="js" selected>JS reference (explicit)</option>')
    if page == 'webgpu-volume':
        original = original.replace('<option value="hybrid">Hybrid (Rust WASM)</option>', '<option value="hybrid" disabled>Hybrid (local Rust WASM build)</option>')
        original = re.sub(r'<a style="color:#9cb9e0" href="../effects-studio/">Effects Studio</a>', '<a style="color:#9cb9e0" href="../../examples.html">Example gallery</a>', original)
    return original

class References(HTMLParser):
    def __init__(self): super().__init__();self.refs=[]
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('href','src','poster') and value: self.refs.append(value)

def verify_site(out):
    checked = 0
    for p in sorted(out.rglob('*.html')):
        text=p.read_text(encoding='utf-8'); parser=References();parser.feed(text)
        for ref in parser.refs:
            u=urlsplit(ref)
            if u.scheme or u.netloc or not u.path: continue
            if u.path.startswith('/'): raise ValueError(f'root-absolute Pages path in {p.relative_to(out)}: {ref}')
            dest=(p.parent/unquote(u.path)).resolve()
            if not dest.is_relative_to(out.resolve()): raise ValueError(f'path leaves site: {ref}')
            if dest.is_dir():dest/= 'index.html'
            if not dest.is_file(): raise ValueError(f'broken HTML reference in {p.relative_to(out)}: {ref}')
            checked += 1
    # Static ES module imports (dynamic fetches are covered by group allowlists and browser checks).
    for p in sorted(out.rglob('*.mjs')):
        for ref in re.findall(r'''(?:\bfrom\s*|\bimport\s*)['"](\.[^'"]+)['"]''',p.read_text(encoding='utf-8')):
            dest=(p.parent/ref).resolve()
            if not dest.is_relative_to(out.resolve()) or not dest.is_file():raise ValueError(f'broken module {p.relative_to(out)}: {ref}')
            checked+=1
    forbidden=[p for p in out.rglob('*') if p.is_file() and (p.suffix in {'.wasm','.dll','.so','.dylib','.exe','.py','.rs'} or 'history' in p.relative_to(out).parts or 'reports' in p.relative_to(out).parts)]
    if forbidden:raise ValueError(f'private or native files in site: {forbidden[:3]}')
    return checked

def build(out, mode):
    project=read_json(ROOT/'project.json'); catalog=read_json(SITE/'catalog.json');groups=available_assets(mode)
    if out.exists():raise ValueError('builder requires an empty, nonexistent staging destination')
    out.mkdir(parents=True)
    for name in ('styles.css','site.js'):copy_file(SITE/name,out/name)
    for p in sorted((SITE/'media').iterdir()):copy_file(p,out/'media'/p.name)
    for p in sorted((ROOT/'bindings/web').rglob('*')):
        if p.is_file() and p.suffix in {'.mjs','.wgsl','.json'} and p.name != 'package.json' and not p.name.endswith('.build.json'):
            copy_file(p,out/p.relative_to(ROOT))
    for name in ('cloud-hero.json','airborne-smoke.json'):copy_file(ROOT/'contracts'/name,out/'contracts'/name)
    for group, enabled in groups.items():
        if enabled:
            for name in ASSET_GROUPS[group]:copy_file(ROOT/'assets'/group/name,out/'assets'/group/name)
    folders = {Path(item['route']).parent.name for item in catalog if item['group']!='local' and (not item.get('asset') or groups[item['asset']])}
    # The film and inspector share one directory. Do not copy the inspector without its fields.
    for folder in sorted(folders):
        for p in sorted((ROOT/'examples'/folder).iterdir()):
            if not p.is_file() or p.suffix not in {'.html','.mjs','.css'}:continue
            if folder=='airborne-smoke' and not groups['airborne-smoke'] and p.name!='index.html':continue
            dest=out/p.relative_to(ROOT);copy_file(p,dest)
            if p.suffix=='.html':
                dest.write_text(hosted_example(folder,dest.read_text(encoding='utf-8'),groups),encoding='utf-8')
    # The film remains available even without the optional inspector fields.
    validation=read_json(ROOT/'reports/validation-current.json')
    count=validation.get('source_test_count') if validation.get('complete') and validation.get('source_checks_passed') else None
    count_text=str(count) if isinstance(count,int) else 'Not recorded'
    test_version=f"Evidence report: distribution {validation.get('distribution_version','unknown')}." if count is not None else 'No completed source-test report in this checkout.'
    featured_ids=('interactive-cloud','airborne','inspector') if groups['airborne-smoke'] else ('interactive-cloud','airborne','fidelity')
    asset_links='<p class="asset-list"><a href="assets/field-assets/cloud.vpf" download>Cloud VPF1 (14.9 MB)</a> <a href="assets/field-assets/fog.vpf" download>Fog VPF1 (1.8 MB)</a></p>' if groups['field-assets'] else '<p class="small">Field downloads are not included in this site build; use the full SDK.</p>'
    replacements={'FEATURED':''.join(card(next(x for x in catalog if x['id']==i),groups) for i in featured_ids), 'ASSET_LINKS':asset_links,'SOURCE_COUNT':esc(count_text),'TEST_VERSION':esc(test_version),'VERSION':esc(project['distribution_version']),'SDK_VERSION':esc(project['sdk_version'])}
    replacements.update({g.upper():''.join(card(x,groups) for x in catalog if x['group']==g) for g in ('reference','experimental','local')})
    for name in PAGES:
        body=(SITE/name).read_text(encoding='utf-8')
        for key,value in replacements.items():body=body.replace(f'@@{key}@@',value)
        if re.search(r'@@\w+@@',body):raise ValueError(f'unresolved template in {name}')
        (out/name).write_text(layout(name,body,project),encoding='utf-8')
    (out/'.nojekyll').write_text('',encoding='utf-8')
    (out/'404.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Vapor | Not found</title><h1>Page not found</h1><p>Return to the Vapor project home using your browser history or the project URL.</p></html>',encoding='utf-8')
    checked=verify_site(out)
    result={'schema':'vapor.pages/1','distribution':project['distribution_version'],'sdk':project['sdk_version'],'asset_groups':groups,'static_references_checked':checked,'hosted_examples':sorted(folders),'files':sum(p.is_file() for p in out.rglob('*')),'runtime_binaries':False,'release_certification':False}
    (out/'site-build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--assets',choices=['none','auto','full'],default='auto');parser.add_argument('--output',type=Path,default=ROOT/'dist/pages');args=parser.parse_args();dest=args.output.resolve()
    # Only overwrite a previously generated Pages tree with our own marker.
    if dest==ROOT or dest in ROOT.parents or (dest.is_relative_to(ROOT) and not dest.is_relative_to(ROOT/'dist')):parser.error('output inside the project must be below dist/')
    if dest.exists() and (not dest.is_dir() or not (dest/'site-build.json').is_file() or read_json(dest/'site-build.json').get('schema')!='vapor.pages/1'):parser.error('refusing to overwrite non-Pages output')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pages-',dir=dest.parent) as tmp:
        stage=Path(tmp)/'site';report=build(stage,args.assets)
        if dest.exists():shutil.rmtree(dest)
        stage.rename(dest)
    print(json.dumps(report,indent=2));print('Built:',dest)
if __name__=='__main__':main()
