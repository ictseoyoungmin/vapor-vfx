#!/usr/bin/env python3
"""Lexical WGSL reserved-word preflight, NOT a parser/compiler or GPU execution test.
Source: https://www.w3.org/TR/2026/CRD-WGSL-20261106/#reserved-words
The real naga parse/validation gate remains mandatory in cargo tests.
"""
from __future__ import annotations
import re
from pathlib import Path

RESERVED = frozenset('''NULL Self abstract active alignas alignof as asm asm_fragment async
attribute auto await become cast catch class co_await co_return co_yield coherent
column_major common compile compile_fragment concept const_cast consteval constexpr
constinit crate debugger decltype delete demote demote_to_helper do dynamic_cast enum
explicit export extends extern external fallthrough filter final finally friend from
fxgroup get goto groupshared highp impl implements import inline instanceof interface
layout lowp macro macro_rules match mediump meta mod module move mut mutable namespace
new nil noexcept noinline nointerpolation non_coherent noncoherent noperspective null
nullptr of operator package packoffset partition pass patch pixelfragment precise
precision premerge priv protected pub public readonly ref regardless register
reinterpret_cast require resource restrict self set shared sizeof smooth snorm static
static_assert static_cast std subroutine super target template this thread_local throw
trait try type typedef typeid typename typeof union unless unorm unsafe unsized use using
varying virtual volatile wgsl where with writeonly yield'''.split())

def strip_comments(text: str) -> str:
    out=list(text);i=0;depth=0
    while i<len(text):
        if text.startswith('/*',i):
            depth+=1;out[i:i+2]=[' ',' '];i+=2
        elif depth and text.startswith('*/',i):
            depth-=1;out[i:i+2]=[' ',' '];i+=2
        elif not depth and text.startswith('//',i):
            while i<len(text) and text[i]!='\n':out[i]=' ';i+=1
        else:
            if depth and text[i]!='\n':out[i]=' '
            i+=1
    if depth:raise ValueError('unterminated block comment')
    return ''.join(out)

def violations(text: str) -> list[tuple[int,str]]:
    code=strip_comments(text)
    return [(code.count('\n',0,m.start())+1,m.group()) for m in
            re.finditer(r'\b[A-Za-z_][A-Za-z_0-9]*\b',code) if m.group() in RESERVED]

def main() -> int:
    root=Path(__file__).resolve().parents[1];failed=False
    for path in sorted((root/'shaders').rglob('*.wgsl')):
        errors=violations(path.read_text())
        for line,word in errors:print(f'FAIL {path.relative_to(root)}:{line}: reserved word {word}');failed=True
        if not errors:print(f'PASS reserved-word preflight {path.relative_to(root)} (NOT WGSL compilation)')
    return int(failed)
if __name__=='__main__':raise SystemExit(main())
