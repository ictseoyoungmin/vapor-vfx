/** Independent worker keeps the orbit renderer responsive; generated files stay local. */
export function setupCloudBake(scene,getQuality){
  const $=id=>document.getElementById(id),button=$('bake'),cancel=$('bake-cancel'),status=$('bake-status'),result=$('bake-result');
  let worker=null,urls=[];
  const clear=()=>{for(const url of urls)URL.revokeObjectURL(url);urls=[];result.replaceChildren();};
  const stop=()=>{worker?.terminate();worker=null;button.disabled=false;cancel.hidden=true;};
  const link=(name,bytes,mime,description)=>{
    const url=URL.createObjectURL(new Blob([bytes],{type:mime}));urls.push(url);
    const row=document.createElement('div'),a=document.createElement('a'),small=document.createElement('small');
    a.href=url;a.download=name;a.textContent=name;small.textContent=description+' · '+(bytes.byteLength/1048576).toFixed(2)+' MiB';row.append(a,small);result.append(row);
  };
  $('bake-threshold').addEventListener('input',()=>{$('threshold-value').value=Number($('bake-threshold').value).toFixed(2);});
  cancel.onclick=()=>{stop();status.textContent='Bake cancelled.';};
  button.onclick=()=>{
    if(worker)return;
    clear();button.disabled=true;cancel.hidden=false;
    status.textContent='Preparing cloud asset…';
    try{
      const quality=getQuality(),threshold=Number($('bake-threshold').value);
      worker=new Worker(new URL('./bake-worker.mjs',import.meta.url),{type:'module'});
      const current=worker;
      const fail=error=>{if(worker!==current)return;stop();status.textContent='Bake failed: '+error;};
      worker.onerror=e=>fail(e.message||'Export worker unavailable');
      worker.onmessage=({data})=>{
        if(worker!==current)return;
        if(data.error){fail(data.error);return;}
        if(data.progress){status.textContent=data.progress;return;}
        try{
          for(const o of data.outputs)link(o.name,o.bytes,'model/gltf-binary',o.resolution+'³ · '+o.triangles.toLocaleString()+' triangles');
          link('vapor-cloud-source.vpf',data.vpf,'application/octet-stream','Original Float32 volume');
          stop();status.textContent='Ready · '+data.quality+' source · threshold '+data.threshold.toFixed(2);
        }catch(error){clear();fail(error.message);}
      };
      worker.postMessage({scene,quality,threshold,material:$('bake-material').checked,lod:$('bake-lod').checked});
    }catch(error){stop();status.textContent='Bake failed: '+error.message;}
  };
  button.disabled=false;
  window.addEventListener('pagehide',()=>{stop();clear();});
}
