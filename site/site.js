// Static site only; no analytics, network requests, dependencies or runtime fallback.
for (const box of document.querySelectorAll('.code')) {
  const pre=box.querySelector('pre'); if(!pre) continue;
  const button=document.createElement('button');button.type='button';button.textContent='Copy';button.setAttribute('aria-label','Copy code snippet');
  button.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(pre.textContent);button.textContent='Copied';}catch{const r=document.createRange();r.selectNodeContents(pre);const s=getSelection();s.removeAllRanges();s.addRange(r);button.textContent='Selected';}setTimeout(()=>button.textContent='Copy',1500);});
  box.append(button);
}
const capability=document.querySelector('[data-capability]');
if(capability) capability.textContent = navigator.gpu ? 'WebGPU API detected · hardware execution not tested' : 'WebGPU unavailable in this browser · CPU and film examples remain available';
