import {test} from 'node:test';import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';import {createHash} from 'node:crypto';
import {proceduralAtlas} from '../bindings/web/procedural.mjs';import {getPreset} from '../bindings/web/effects.mjs';
const data=JSON.parse(readFileSync(new URL('../fixtures/procedural-v08-full-atlas.json',import.meta.url),'utf8'));
for(const row of data.rows)test(`${row.key} ${row.quality} t=${row.time} bitwise 0.8 parity`,()=>{const d=getPreset(row.key,row.quality);const a=proceduralAtlas(d.config,d.kind,d.procedural,row.time);assert.equal(createHash('sha256').update(a).digest('hex'),row.sha256);});
