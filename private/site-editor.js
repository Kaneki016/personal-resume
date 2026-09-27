/* Structured website editing; only saved content is published. */
window.SiteEditor=(()=>{
 let data=null,key='profile',draft=null,dirty=false,busy=false;
 const copy=value=>JSON.parse(JSON.stringify(value));
 function canLeave(){
  if(busy)return false;
  if(dirty&&!confirm('Discard the unsaved changes to this website section?'))return false;
  dirty=false;return true;
 }
 window.addEventListener('beforeunload',event=>{if(dirty||busy){event.preventDefault();event.returnValue='';}});
 function changed(){dirty=true;const status=document.getElementById('cms-status');if(status)status.textContent='Unsaved changes';}
 async function open(){
  $('content').innerHTML=heading('Website content','Update the words, images and background information on your public portfolio.')+'<div class="panel" id="cms-root"><p>Loading your content…</p></div>';
  try{data=await api('/api/site-content');if(view!=='content')return;draft=copy(data.sections[key]);dirty=false;render();}catch(error){const root=$('cms-root');if(root){root.innerHTML='<p class="error"></p><button type="button" id="cms-retry">Try again</button>';root.querySelector('p').textContent=error.message;$('cms-retry').onclick=open;}}
 }
 function render(){
  const spec=data.schema[key];
  $('cms-root').innerHTML=`<div class="cms-toolbar"><div><label for="cms-section">Section to edit</label><select id="cms-section">${Object.entries(data.schema).map(([value,s])=>`<option value="${esc(value)}" ${value===key?'selected':''}>${esc(s.label)}</option>`).join('')}</select></div><a href="/" target="_blank" rel="noopener">View live website ↗</a></div><p class="help">Save & publish updates this section immediately. You can edit other sections separately. Contact details here do not change your owner login.</p><form id="cms-form"><div id="cms-fields"></div>${spec.collection?'<button type="button" id="cms-add">+ Add entry</button>':''}<p id="cms-error" class="error" role="alert"></p><div class="cms-footer"><span id="cms-status" role="status">${dirty?'Unsaved changes':'All changes saved'}</span><div class="actions"><button type="button" id="cms-reload">Reload section</button><button type="submit" class="primary" id="cms-save">Save & publish</button></div></div></form>`;
  renderFields();
  $('cms-section').onchange=event=>{const next=event.target.value;if(!canLeave()){event.target.value=key;return;}key=next;draft=copy(data.sections[key]);render();};
  $('cms-add')?.addEventListener('click',()=>{if(draft.length>=spec.max_items){$('cms-error').textContent='Use at most '+spec.max_items+' entries.';return;}draft.push(Object.fromEntries(spec.fields.map(f=>[f.key,f.type==='checkbox'?true:''])));changed();renderFields();$('cms-fields').lastElementChild?.querySelector('input:not([type=hidden]),textarea')?.focus();});
  $('cms-reload').onclick=()=>{if(canLeave())open();};
  $('cms-form').onsubmit=save;
 }
 function fieldHtml(field,item,index){
  const id='cms-'+index+'-'+field.key,value=item[field.key]??'',attributes=`data-index="${index}" data-key="${esc(field.key)}"`;
  if(field.type==='checkbox')return `<div class="check"><input type="checkbox" id="${id}" ${attributes} ${value?'checked':''}><label for="${id}">${esc(field.label)}</label></div>`;
  let control='';
  if(field.type==='textarea')control=`<textarea id="${id}" ${attributes} maxlength="${field.max}" ${field.required?'required':''}>${esc(value)}</textarea>`;
  else if(field.type==='image')control=`<input type="hidden" id="${id}" value="${esc(value)}">`;
  else control=`<input id="${id}" ${attributes} type="${['url','email'].includes(field.type)?field.type:'text'}" value="${esc(value)}" maxlength="${field.max}" ${field.required?'required':''}>`;
  if(['image','asset'].includes(field.type)){
   control+=`<div class="cms-image-preview">${value&&value.startsWith('/')?`<img src="${esc(value)}" alt="${esc(field.label)}">`:''}</div><label class="cms-upload-label" for="${id}-upload">${field.type==='asset'?'Or upload a certificate image':'Upload image'} (JPG, PNG or WebP, up to 3 MB)</label><input id="${id}-upload" type="file" accept="image/jpeg,image/png,image/webp" data-upload-index="${index}" data-upload-key="${esc(field.key)}">${value?`<button type="button" class="mini-button cms-remove-image" data-clear-index="${index}" data-clear-key="${esc(field.key)}">Remove image / link</button>`:''}`;
  }
  return `<div class="field ${['textarea','image','asset'].includes(field.type)?'full':''}"><label for="${id}">${esc(field.label)}${field.required?' *':''}</label>${control}</div>`;
 }
 function renderFields(){
  const spec=data.schema[key],items=spec.collection?draft:[draft];
  $('cms-fields').innerHTML=items.map((item,index)=>`<section class="cms-entry">${spec.collection?`<header><h3>${esc(item.title||'New entry')} <small>(${index+1})</small></h3><div class="actions"><button type="button" data-move="${index}" data-direction="-1" aria-label="Move entry ${index+1} earlier" ${index===0?'disabled':''}>↑</button><button type="button" data-move="${index}" data-direction="1" aria-label="Move entry ${index+1} later" ${index===items.length-1?'disabled':''}>↓</button><button type="button" data-remove="${index}" aria-label="Remove entry ${index+1}">Remove</button></div></header>`:''}<div class="two-fields">${spec.fields.map(field=>fieldHtml(field,item,index)).join('')}</div></section>`).join('')||'<p class="help">No entries. Add one below, then save to publish it.</p>';
  $('cms-fields').querySelectorAll('[data-key]').forEach(input=>input.addEventListener('input',()=>{const item=spec.collection?draft[Number(input.dataset.index)]:draft;item[input.dataset.key]=input.type==='checkbox'?input.checked:input.value;changed();}));
  $('cms-fields').querySelectorAll('[data-remove]').forEach(button=>button.onclick=()=>{draft.splice(Number(button.dataset.remove),1);changed();renderFields();});
  $('cms-fields').querySelectorAll('[data-move]').forEach(button=>button.onclick=()=>{const i=Number(button.dataset.move),j=i+Number(button.dataset.direction);[draft[i],draft[j]]=[draft[j],draft[i]];changed();renderFields();});
  $('cms-fields').querySelectorAll('[data-clear-key]').forEach(button=>button.onclick=()=>{const item=spec.collection?draft[Number(button.dataset.clearIndex)]:draft;item[button.dataset.clearKey]='';changed();renderFields();});
  $('cms-fields').querySelectorAll('[data-upload-key]').forEach(input=>input.onchange=()=>upload(input));
 }
 function lock(value){busy=value;$('cms-root').querySelectorAll('input,textarea,select,button').forEach(el=>el.disabled=value);}
 async function upload(input){
  const file=input.files[0];if(!file)return;
  $('cms-error').textContent='';
  if(file.size>3*1024*1024||!['image/jpeg','image/png','image/webp'].includes(file.type)){$('cms-error').textContent='Use a JPG, PNG or WebP image smaller than 3 MB.';input.value='';return;}
  const index=Number(input.dataset.uploadIndex),field=input.dataset.uploadKey;
  lock(true);$('cms-status').textContent='Uploading image…';
  try{
   const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read the image.'));reader.readAsDataURL(file);});
   const result=await api('/api/upload',{method:'POST',body:JSON.stringify({data:encoded})});
   const item=data.schema[key].collection?draft[index]:draft;item[field]=result.url;changed();
  }catch(error){$('cms-error').textContent=error.message;}
  finally{lock(false);renderFields();$('cms-status').textContent=dirty?'Unsaved changes':'All changes saved';}
 }
 async function save(event){
  event.preventDefault();$('cms-error').textContent='';lock(true);$('cms-status').textContent='Saving…';
  try{
   const result=await api('/api/site-content/'+key,{method:'PUT',body:JSON.stringify({content:draft,revision:data.revisions[key]})});
   data.sections[key]=result.content;data.revisions[key]=result.revision;draft=copy(result.content);dirty=false;
   $('cms-status').textContent='Published — your live website is updated.';
  }catch(error){$('cms-error').textContent=error.message;$('cms-status').textContent='Not saved. Your changes are still here.';}
  finally{lock(false);renderFields();}
 }
 return {open,canLeave};
})();
