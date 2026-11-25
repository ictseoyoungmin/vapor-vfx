import {readFile,writeFile} from 'node:fs/promises';
import {loadVapor} from '../../bindings/web/vapor.mjs';
import {NativeFidelityCPU} from '../../bindings/web/native-fidelity.mjs';
const sdk=new NativeFidelityCPU(await loadVapor(await readFile(new URL('../../bindings/web/vapor.wasm',import.meta.url))));
const v=sdk.generate('cumulus_cloud',{cells:[32,16,24],extent:[48,24,36]});
const f=sdk.render(v,{width:96,height:60,steps:64,eye:[30,8,-50],target:[24,12,18]});
const output=process.argv[2]??'cloud.rgba';await writeFile(output,f.rgba);console.log({model:f.model,dimensions:[f.width,f.height],bytes:f.rgba.length,output});
