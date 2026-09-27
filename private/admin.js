const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>'RM '+(Number(n)/100).toLocaleString('en-MY',{minimumFractionDigits:2,maximumFractionDigits:2});
let session={},state={},projectList=[],view='overview',editing=null,editorImages=[];
function clearEditorImages(){editorImages.forEach(item=>{if(item.preview)URL.revokeObjectURL(item.preview);});editorImages=[];}
$('editor').addEventListener('close',clearEditorImages);
$('editor').addEventListener('cancel',event=>{if($('save').disabled)event.preventDefault();});
const today=()=>new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Kuala_Lumpur'});
$('year').value=new Date().getFullYear();
async function api(path,options={}){
 const response=await fetch(path,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf||'',...options.headers}});
 const data=await response.json();
 if(!response.ok){if(response.status===401 && $('app').hidden===false){$('app').hidden=true;await boot();}throw new Error(data.error||'Request failed.');}return data;
}
function notice(message){$('notice').textContent=message;$('notice').hidden=false;}
async function boot(){
 try{session=await api('/api/session');$('boot').hidden=true;if(!session.authenticated){$('auth').hidden=false;$('app').hidden=true;$('auth-title').textContent=session.setup?'Set up your owner access':'Welcome back';$('auth-copy').textContent=session.setup?'Create the password for this local workspace. Portfolio editing and financial records are private.':'Sign in to manage your portfolio and business records.';$('auth-submit').textContent=session.setup?'Create owner password':'Sign in';$('confirm-wrap').hidden=!session.setup;$('confirm').required=session.setup;$('password').autocomplete=session.setup?'new-password':'current-password';return;}await enter();}
 catch(e){$('boot').textContent='Could not connect to the workspace. Refresh to try again.';}
}
$('auth-form').addEventListener('submit',async event=>{
 event.preventDefault();$('auth-error').textContent='';if(session.setup&&$('password').value!==$('confirm').value){$('auth-error').textContent='Passwords do not match.';return;}
 $('auth-submit').disabled=true;try{const result=await api(session.setup?'/api/setup':'/api/login',{method:'POST',body:JSON.stringify({password:$('password').value})});session={authenticated:true,csrf:result.csrf};$('auth-form').reset();await enter();}catch(e){$('auth-error').textContent=e.message;}finally{$('auth-submit').disabled=false;}
});
async function enter(){$('auth').hidden=true;$('app').hidden=false;await refresh();}
async function refresh(){
 try{[state,projectList]=await Promise.all([api('/api/records?year='+$('year').value),api('/api/projects')]);render();}catch(e){notice(e.message);}
}
$('logout').addEventListener('click',async()=>{if(window.SiteEditor&&!SiteEditor.canLeave())return;try{await api('/api/logout',{method:'POST',body:'{}'});$('editor').close();state={};projectList=[];await boot();}catch(e){notice(e.message);}});
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{if(window.SiteEditor&&!SiteEditor.canLeave())return;view=button.dataset.view;render();}));
$('year').addEventListener('change',()=>{if($('year').reportValidity())refresh();});
const heading=(title,description,action='')=>`<div class="page-heading"><div><h1>${title}</h1><p>${description}</p></div>${action}</div>`;
const addButton=(label)=>`<button class="primary" data-add>+ ${label}</button>`;
const empty=(title,copy)=>`<div class="empty"><h3>${title}</h3><p>${copy}</p></div>`;
const badge=(label,cls='')=>`<span class="status-tag ${cls}">${esc(label)}</span>`;
const editButton=id=>`<button class="mini-button" data-edit="${id}">Edit</button>`;
const inYear=(record,key='date')=>record[key].startsWith($('year').value+'-');
function table(headers,rows){return `<div class="panel table-scroll"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;}
function render(){
 $('year').parentElement.hidden=view==='content';
 document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-current',b.dataset.view===view?'page':'false');});
 if(view==='content'){window.SiteEditor.open();return;}
 let html='';const s=state.summary;
 if(view==='overview'){
  html=heading('A little more organised.','Your portfolio and freelance business, in one place.')+`<div class="stats"><div class="stat"><span class="label">Payments received · ${state.year}</span><strong>${money(s.received)}</strong><small>By date received</small></div><div class="stat"><span class="label">Business expenses · ${state.year}</span><strong>${money(s.expenses)}</strong><small>Business portion of payments recorded</small></div><div class="stat"><span class="label">Net cash · ${state.year}</span><strong>${money(s.net_cash)}</strong><small>Received less recorded expenses</small></div><div class="stat"><span class="label">Outstanding · all invoices</span><strong>${money(s.outstanding)}</strong><small>Unpaid balance, as of now</small></div></div><div class="overview-grid"><section class="panel"><h2>Recent payments</h2>${state.payments.filter(p=>!p.void&&inYear(p)).length?`<ul class="compact-list">${state.payments.filter(p=>!p.void&&inYear(p)).slice(0,5).map(p=>`<li><div>${esc(p.client)}<small>${esc(p.number)} · ${esc(p.date)}</small></div><strong>${money(p.amount_cents)}</strong></li>`).join('')}</ul>`:empty('No payments recorded yet','Record a client project, add its invoice, then log the payments as they arrive.')}<p>Invoiced in ${state.year}: <strong>${money(s.invoiced)}</strong>. Overpayments across all invoices: <strong>${money(s.credit)}</strong>.</p></section><section class="panel"><h2>A simple way to keep records</h2><ol class="steps"><li>Add the client project and agreed total fee.</li><li>Record each invoice or milestone separately.</li><li>Log the actual deposit and balance payments.</li><li>Record expenses and keep their receipts.</li><li>Export records and download a backup regularly.</li></ol><p class="subtle">Net cash is a bookkeeping measure, not a calculation of taxable income. Invoice totals and received payments are tracked separately.</p></section></div>`;
 }else if(view==='projects'){
  html=heading('Your work, on display.','Add projects, update details, and choose what appears publicly.',addButton('Add project'))+`<div class="project-cards">${projectList.map(p=>`<article class="admin-project">${p.image?`<img src="${esc(p.image)}" alt="${esc(p.title)}">`:'<div class="project-placeholder">LY / WORK</div>'}<div class="body">${badge(p.published?'Published':'Draft',p.published?'published':'')}<h3>${esc(p.title)}</h3><p>${esc(p.summary)}</p><button data-edit="${p.id}">Edit project</button></div></article>`).join('')}</div>`;
 }else if(['jobs','invoices','payments','expenses'].includes(view)){
  const info={jobs:['Client projects','Track agreed fees separately from amounts invoiced or paid.','Add client project'],invoices:['Invoices','Generate a numbered invoice, print or save a PDF, and track payments separately.','Generate invoice'],payments:['Payments received','Record each deposit and balance payment on its actual received date.','Add payment'],expenses:['Expenses','Record paid expenses in MYR. Keep supporting receipts using the reference field.','Add expense']}[view];
  html=heading(info[0],info[1],view==='invoices'?`<div class="actions"><button data-invoice-settings>Invoice settings</button>${addButton(info[2])}</div>`:addButton(info[2]));
  const items=view==='jobs'?state.jobs:state[view].filter(r=>inYear(r,view==='invoices'?'issue_date':'date'));
  if(!items.length)html+=empty(`No ${view==='jobs'?'client projects':view} yet`,view==='jobs'?'Add your first client and agreed project fee.':`No entries dated ${state.year}. Use the button above to add a record.`);
  else if(view==='jobs')html+=table(['Project / client','Agreed fee','Status',''],items.map(r=>`<tr><td>${esc(r.name)}<small>${esc(r.client)}</small></td><td class="money">${r.fee_known?money(r.fee_cents):'<span class="subtle">Not set</span>'}</td><td>${badge(r.status)}</td><td>${editButton(r.id)}</td></tr>`));
  else if(view==='invoices')html+=table(['Invoice / client','Dates','Billed','Received','Balance','Status',''],items.map(r=>`<tr><td>${esc(r.number)}<small>${esc(r.client)} · ${esc(r.job_name)}</small></td><td>${esc(r.issue_date)}<small>Due ${esc(r.due_date)}</small></td><td class="money">${money(r.amount_cents)}</td><td class="money">${money(r.paid_cents)}</td><td class="money">${money(r.amount_cents-r.paid_cents)}</td><td>${badge(r.void?'Void':r.paid_cents>=r.amount_cents?'Paid':r.due_date<today()?'Overdue':r.paid_cents?'Part paid':'Unpaid',r.void?'void':'')}</td><td><div class="actions"><a class="mini-button" href="/api/invoices/${r.id}/print" target="_blank" rel="noopener">View / Print</a>${editButton(r.id)}</div></td></tr>`));
  else if(view==='payments')html+=table(['Date','Client / invoice','Amount','Method / reference','Status',''],items.map(r=>`<tr><td>${esc(r.date)}</td><td>${esc(r.client)}<small>${esc(r.number)}</small></td><td class="money">${money(r.amount_cents)}</td><td>${esc(r.method)}<small>${esc(r.reference)}</small></td><td>${badge(r.void?'Void':'Recorded',r.void?'void':'')}</td><td>${editButton(r.id)}</td></tr>`));
  else html+=table(['Date / payee','Category','Paid','Business portion','Receipt reference','Status',''],items.map(r=>`<tr><td>${esc(r.date)}<small>${esc(r.payee)}</small></td><td>${esc(r.category)}</td><td class="money">${money(r.amount_cents)}</td><td class="money">${money(Math.round(r.amount_cents*r.business_percent/100))}<small>${r.business_percent}%</small></td><td>${esc(r.reference||'Not provided')}</td><td>${badge(r.void?'Void':'Recorded',r.void?'void':'')}</td><td>${editButton(r.id)}</td></tr>`));
  html+='<p class="subtle">Voided entries stay in the records and exports but do not contribute to totals. Corrections are retained in the change history.</p>';
 }else if(view==='exports'){
  html=heading('Ready when you need them.','Download your records for review, bookkeeping, or tax preparation.')+`<div class="export-grid">${[['jobs','Client projects','All agreed project fees and client references.'],['invoices','Invoices','Invoices issued in the selected year, with current paid balances.'],['payments','Payments received','Payments dated in the selected year, including voided records.'],['expenses','Expenses','Paid expenses, categories, business percentages, and receipt references.'],['audit','Full change history','All creates and corrections, with original and revised values.']].map(([key,title,copy])=>`<section class="panel"><h2>${title}</h2><p>${copy}</p><a class="primary" href="/api/export?type=${key}&year=${state.year}">Download CSV</a></section>`).join('')}<section class="panel"><h2>Private backup</h2><p>A JSON copy of your financial records, portfolio entries and change history. Download the portfolio-images bucket separately from Supabase Storage to back up image files. Keep both copies private.</p><a class="primary" href="/api/backup">Download records JSON</a></section></div><section class="panel" style="margin-top:22px"><h2>Keep the supporting documents</h2><p>Keep bank statements, invoices, receipts, and relevant agreements alongside these records. Receipt references here point to your own files; this version does not upload receipt documents.</p><p>For current filing guidance, visit <a href="https://www.hasil.gov.my/individu/lapor-pendapatan/" target="_blank" rel="noopener noreferrer">HASiL’s official income reporting page ↗</a>.</p><p class="subtle">The selected year uses payment dates for receipts and expenses, and issue dates for invoices. These exports help organise your records; they do not file a return, determine deductibility, or calculate your income tax.</p></section>`;
 }else if(view==='settings'){
  html=heading('Your workspace settings.','One owner account. Changes to records are kept in the activity log.')+`<section class="panel"><h2>Change password</h2><form id="password-form" class="settings-form"><label for="current-password">Current password</label><input type="password" id="current-password" autocomplete="current-password" required><label for="new-password">New password</label><input type="password" id="new-password" autocomplete="new-password" minlength="12" maxlength="256" required><label for="confirm-password">Confirm new password</label><input type="password" id="confirm-password" autocomplete="new-password" minlength="12" maxlength="256" required><p class="error" id="password-error" role="alert"></p><button class="primary">Update password & sign out</button></form></section><section class="panel"><h2>Recent activity</h2><div id="activity">Loading activity…</div></section>`;
 }
 $('content').innerHTML=html;
 $('content').querySelector('[data-add]')?.addEventListener('click',()=>view==='invoices'?InvoiceEditor.generate():openEditor());
 $('content').querySelector('[data-invoice-settings]')?.addEventListener('click',()=>InvoiceEditor.configure());
 $('content').querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click',()=>openEditor(Number(b.dataset.edit))));
 if(view==='settings')settings();
}
function field(name,label,value='',type='text',extra=''){
 return `<div class="field"><label for="f-${name}">${label}</label><input id="f-${name}" name="${name}" type="${type}" value="${esc(value)}" ${extra}></div>`;
}
function area(name,label,value='',extra=''){return `<div class="field full"><label for="f-${name}">${label}</label><textarea id="f-${name}" name="${name}" ${extra}>${esc(value)}</textarea></div>`;}
function select(name,label,options,value){return `<div class="field"><label for="f-${name}">${label}</label><select id="f-${name}" name="${name}" required>${options.map(([id,label])=>`<option value="${esc(id)}" ${String(id)===String(value)?'selected':''}>${esc(label)}</option>`).join('')}</select></div>`;}
function check(name,label,checked){return `<div class="check"><input id="f-${name}" name="${name}" type="checkbox" ${checked?'checked':''}><label for="f-${name}">${label}</label></div>`;}
function openEditor(id){
 const collection=view==='projects'?projectList:state[view];const r=id?collection.find(r=>r.id===id):{};editing={entity:view,id};$('save-error').textContent='';
 const titles={projects:'portfolio project',jobs:'client project',invoices:'invoice',payments:'payment',expenses:'expense'};
 $('editor-title').textContent=(id?'Edit ':'Add ')+titles[view];let html='';
 if(view==='projects'){
  html=field('title','Project title *',r.title,'text','required maxlength="140"')+field('category','Category *',r.category||'Client work','text','required maxlength="60"')+area('summary','Short summary *',r.summary,'required maxlength="700"')+area('details','Project details',r.details,'maxlength="6000"')+field('tags','Tools / skills (comma separated)',r.tags,'text','maxlength="300"')+field('url','Live project link',r.url,'url','placeholder="https://" maxlength="1000"')+field('position','Display order',r.position||0,'number','min="0" max="999" required')+`<div class="field full field-image"><label for="f-image-file">Project screenshots (up to 20; JPG, PNG, WebP; 3 MB each)</label><input type="file" id="f-image-file" accept="image/jpeg,image/png,image/webp" multiple><p class="help">The first screenshot is the project cover. Move images to change their order. Removing a screenshot removes it from this project after saving.</p><div id="editor-images" class="editor-images"></div></div>`+`<div class="field full">${check('published','Show this project on the public portfolio',r.published)}<p class="help">Leave unchecked to keep it as a draft. Uploaded draft images are private until the project is published.</p></div>`;
 }else if(view==='jobs'){
  html=field('name','Project name *',r.name,'text','required maxlength="160"')+field('client','Client name *',r.client,'text','required maxlength="160"')+field('fee','Agreed project fee (MYR, optional)',id&&r.fee_known?r.fee_cents/100:'','number','min="0" max="99999999.99" step="0.01" placeholder="Leave blank if not agreed"')+select('status','Project status',[['active','Active'],['complete','Complete'],['cancelled','Cancelled']],r.status||'active')+area('notes','Scope / reference notes',r.notes,'maxlength="3000"');
 }else if(view==='invoices'){
  html=select('job_id','Client project *',[['','Select a client project'],...state.jobs.map(j=>[j.id,j.client+' · '+j.name])],r.job_id||'')+field('number','Invoice number *',r.number,'text','required maxlength="80" placeholder="INV-2026-001"')+field('issue_date','Issue date *',r.issue_date||today(),'date','required')+field('due_date','Due date *',r.due_date||addDays(today(),14),'date','required')+field('amount','Amount billed (MYR) *',id?r.amount_cents/100:'','number','min="0.01" max="99999999.99" step="0.01" required')+area('description','Milestone / invoice description',r.description,'maxlength="2000"')+'<p class="help field full">For a 50% deposit on a RM3,000 project, record a RM1,500 deposit invoice. Record the balance as a separate milestone invoice. Use View / Print in the invoice list to print or save a PDF. Generated invoice details are fixed; void and generate a replacement for corrections.</p>';
 }else if(view==='payments'){
  html=select('invoice_id','Invoice *',[['','Select an invoice'],...state.invoices.map(i=>[i.id,i.number+' · '+i.client+(i.void?' [void]':'')])],r.invoice_id||'')+field('date','Date received *',r.date||today(),'date','required')+field('amount','Amount received (MYR) *',id?r.amount_cents/100:'','number','min="0.01" max="99999999.99" step="0.01" required')+field('method','Payment method *',r.method||'Bank transfer','text','required maxlength="80"')+field('reference','Bank / transaction reference',r.reference,'text','maxlength="300"')+area('notes','Notes',r.notes,'maxlength="2000"')+'<p class="help field full">Record only money actually received. If a gateway deducts fees, record gross receipts here and the fee separately as an expense, using your statement to reconcile.</p>';
 }else if(view==='expenses'){
  html=field('date','Date paid *',r.date||today(),'date','required')+field('payee','Payee / supplier *',r.payee,'text','required maxlength="160"')+field('category','Category *',r.category,'text','required maxlength="80" placeholder="Hosting, software, equipment…"')+field('amount','Total paid (MYR) *',id?r.amount_cents/100:'','number','min="0.01" max="99999999.99" step="0.01" required')+field('business_percent','Business use (%) *',r.business_percent??100,'number','min="0" max="100" step="1" required')+field('reference','Receipt filename / reference',r.reference,'text','maxlength="300"')+area('notes','Purpose / supporting notes',r.notes,'maxlength="2000"')+'<p class="help field full">The business percentage helps separate personal use. It does not establish tax deductibility. Keep the original receipt in your own files.</p>';
 }
 if(id&&['invoices','payments','expenses'].includes(view))html+=`<div class="field full">${check('void','Void this record (retain it, exclude from totals)',r.void)}</div>`;
 $('fields').innerHTML='<div class="two-fields">'+html+'</div>';
 if(view==='invoices'&&r.generated){$('fields').querySelectorAll('input:not([type=checkbox]),textarea,select').forEach(el=>el.disabled=true);}
 clearEditorImages();
 if(view==='projects'){
  editorImages=(r.screenshots?.length?r.screenshots:(r.image?[r.image]:[])).map(url=>({url}));renderEditorImages();
  $('f-image-file').addEventListener('change',event=>{
   const files=[...event.target.files];$('save-error').textContent='';
   if(editorImages.length+files.length>20){$('save-error').textContent='Use up to 20 screenshots per project.';event.target.value='';return;}
   if(files.some(file=>file.size>3*1024*1024||!['image/jpeg','image/png','image/webp'].includes(file.type))){$('save-error').textContent='Choose JPG, PNG or WebP images smaller than 3 MB each.';event.target.value='';return;}
   files.forEach(file=>editorImages.push({file,preview:URL.createObjectURL(file)}));event.target.value='';renderEditorImages();
  });
 }
 $('editor').showModal();
}
function renderEditorImages(){
 $('editor-images').innerHTML=editorImages.map((item,index)=>`<div class="editor-image"><img src="${esc(item.preview||item.url)}" alt="Screenshot ${index+1}"><span>${index===0?'Cover · ':''}Screenshot ${index+1}</span><div><button type="button" data-image-up="${index}" aria-label="Move screenshot ${index+1} earlier" ${index===0?'disabled':''}>↑</button><button type="button" data-image-down="${index}" aria-label="Move screenshot ${index+1} later" ${index===editorImages.length-1?'disabled':''}>↓</button><button type="button" data-image-remove="${index}" aria-label="Remove screenshot ${index+1}">Remove</button></div></div>`).join('')||'<p class="help">No screenshots yet. Add images above.</p>';
 $('editor-images').querySelectorAll('[data-image-remove]').forEach(button=>button.addEventListener('click',()=>{const [item]=editorImages.splice(Number(button.dataset.imageRemove),1);if(item.preview)URL.revokeObjectURL(item.preview);renderEditorImages();}));
 for(const [attribute,delta] of [['imageUp',-1],['imageDown',1]])$('editor-images').querySelectorAll(attribute==='imageUp'?'[data-image-up]':'[data-image-down]').forEach(button=>button.addEventListener('click',()=>{const i=Number(button.dataset[attribute]);[editorImages[i],editorImages[i+delta]]=[editorImages[i+delta],editorImages[i]];renderEditorImages();}));
}
function addDays(day,days){const d=new Date(day+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10);}
function closeEditor(){if(!$('save').disabled)$('editor').close();}
$('close-editor').addEventListener('click',closeEditor);$('cancel-editor').addEventListener('click',closeEditor);
$('edit-form').addEventListener('submit',async event=>{
 event.preventDefault();$('save-error').textContent='';$('save').disabled=true;
 try{
  const data=Object.fromEntries(new FormData($('edit-form')));
  if(editing.entity==='invoices'){const original=state.invoices.find(i=>i.id===editing.id);if(original?.generated)Object.assign(data,{job_id:original.job_id,number:original.number,issue_date:original.issue_date,due_date:original.due_date,amount:(original.amount_cents/100).toFixed(2),description:original.description});}
  ['published','void'].forEach(key=>{if($(('f-'+key)))data[key]=$('f-'+key).checked?1:0;});
  if(editing.entity==='projects'){
   $('fields').querySelectorAll('button,input[type=file]').forEach(control=>control.disabled=true);
   for(const item of editorImages){if(!item.file)continue;const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read the image.'));reader.readAsDataURL(item.file);});const upload=await api('/api/upload',{method:'POST',body:JSON.stringify({data:encoded})});item.url=upload.url;delete item.file;}
   data.screenshots=editorImages.map(item=>item.url);data.image=data.screenshots[0]||'';
  }
  await api('/api/'+editing.entity+(editing.id?'/'+editing.id:''),{method:editing.id?'PUT':'POST',body:JSON.stringify(data)});
  $('editor').close();notice(editing.entity==='projects'?'Project saved. Published changes appear when the portfolio is refreshed.':'Record saved. Totals and exports have been updated.');await refresh();
 }catch(e){$('save-error').textContent=e.message;}finally{$('save').disabled=false;if(editing?.entity==='projects'&&$('editor').open){renderEditorImages();$('f-image-file').disabled=false;}}
});
async function settings(){
 try{const activity=await api('/api/audit');if($('activity'))$('activity').innerHTML=activity.length?`<ul class="compact-list">${activity.map(a=>`<li><span>${esc(a.action)} · ${esc(a.entity)} #${a.entity_id}</span><small>${esc(a.recorded_at)} UTC</small></li>`).join('')}</ul>`:'<p class="subtle">Activity appears after you add or update a record.</p>';}catch(e){if($('activity'))$('activity').textContent=e.message;}
 $('password-form')?.addEventListener('submit',async event=>{event.preventDefault();$('password-error').textContent='';if($('new-password').value!==$('confirm-password').value){$('password-error').textContent='Passwords do not match.';return;}try{await api('/api/password',{method:'POST',body:JSON.stringify({current:$('current-password').value,password:$('new-password').value})});await boot();}catch(e){$('password-error').textContent=e.message;}});
}
boot();
