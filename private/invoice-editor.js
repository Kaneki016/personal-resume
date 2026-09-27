// Private issuer settings are fetched only after owner authentication.
window.InvoiceEditor=(()=>{
 const dialog=document.createElement('dialog');dialog.id='invoice-generator';document.body.append(dialog);
 const q=id=>dialog.querySelector('#'+id.replace(/^f-/, 'bill-'));
 let busy=false;
 dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
 function frame(title,body,button){
  dialog.innerHTML=`<form id="invoice-form"><header class="dialog-header"><h2>${title}</h2><button type="button" data-close class="icon-button" aria-label="Close invoice dialog">×</button></header>${body.replace(/id="f-/g,'id="bill-').replace(/for="f-/g,'for="bill-')}<p id="invoice-error" class="error" role="alert"></p><footer class="dialog-footer"><button type="button" data-close>Cancel</button><button class="primary" id="invoice-submit">${button}</button></footer></form>`;
  dialog.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>{if(!busy)dialog.close();}));
  dialog.showModal();
 }
 async function configure(){
  let values;try{values=await api('/api/invoice-settings');}catch(e){notice(e.message);return;}
  const fields=[['name','Issuer name *',160],['email','Email',200],['phone','Phone',80],['bank','Bank name *',120],['account','Account number *',80],['holder','Account holder *',160]];
  frame('Invoice settings',`<p class="help">These details appear on new invoices. Previously generated invoices retain their original details.</p><div class="two-fields">${fields.map(([k,label,max])=>field(k,label,values[k],'text',`maxlength="${max}" ${label.endsWith('*')?'required':''}`)).join('')}${area('address','Issuer address (optional)',values.address,'maxlength="600"')}${area('terms','Payment terms *',values.terms,'required maxlength="1000"')}</div>`,'Save invoice settings');
  q('invoice-form').addEventListener('submit',async event=>{
   event.preventDefault();busy=true;q('invoice-submit').disabled=true;q('invoice-error').textContent='';
   try{await api('/api/invoice-settings',{method:'PUT',body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});dialog.close();notice('Invoice settings saved. New invoices will use these details.');}
   catch(e){q('invoice-error').textContent=e.message;}finally{busy=false;q('invoice-submit').disabled=false;}
  });
 }
 function generate(){
  const requestKey=crypto.randomUUID();
  frame('Generate an invoice',`<p class="help">A running number is assigned when you generate the invoice. Existing client and project names reuse that project; a new pair creates a client project with its agreed fee left unset.</p><div class="two-fields">${field('client','Client name *','','text','required maxlength="160" list="invoice-clients" autocomplete="off"')}${field('project','Client project *','','text','required maxlength="160" list="invoice-projects" autocomplete="off"')}${field('amount','Amount billed (MYR) *','','number','required min="0.01" max="99999999.99" step="0.01" placeholder="1500.00"')}${area('description','What is this billed for? *','','required maxlength="2000" placeholder="50% deposit for website development"')}</div><datalist id="invoice-clients">${[...new Set(state.jobs.map(j=>j.client))].map(c=>`<option value="${esc(c)}"></option>`).join('')}</datalist><datalist id="invoice-projects"></datalist><details class="invoice-dates"><summary>Dates · today, due in 14 days</summary><div class="two-fields">${field('issue_date','Issue date *',today(),'date','required')}${field('due_date','Due date *',addDays(today(),14),'date','required')}</div></details><p class="help">The amount entered is the amount billed, including for a deposit. No tax is added. Payments are recorded separately after receipt.</p>`,'Generate invoice');
  const updateProjects=()=>{q('invoice-projects').innerHTML=state.jobs.filter(j=>j.client.toLowerCase()===q('f-client').value.trim().toLowerCase()).map(j=>`<option value="${esc(j.name)}"></option>`).join('');};
  q('f-client').addEventListener('input',updateProjects);
  q('f-issue_date').addEventListener('change',()=>{if(q('f-issue_date').value)q('f-due_date').value=addDays(q('f-issue_date').value,14);});
  q('invoice-form').addEventListener('submit',async event=>{
   event.preventDefault();busy=true;q('invoice-submit').disabled=true;q('invoice-error').textContent='';
   try{
    const data={...Object.fromEntries(new FormData(event.target)),request_key:requestKey};
    const result=await api('/api/invoices/generate',{method:'POST',body:JSON.stringify(data)});
    $('year').value=data.issue_date.slice(0,4);await refresh();
    dialog.innerHTML=`<div class="invoice-success"><span class="eyebrow">INVOICE READY</span><h2>${esc(result.number)}</h2><p>Your invoice has been saved to your records. Open it to print or save a PDF for your client.</p><a class="primary" href="/api/invoices/${result.id}/print" target="_blank" rel="noopener">View / Print invoice ↗</a><button id="invoice-done">Done</button></div>`;
    q('invoice-done').addEventListener('click',()=>dialog.close());
   }catch(e){q('invoice-error').textContent=e.message;}finally{busy=false;if(q('invoice-submit'))q('invoice-submit').disabled=false;}
  });
 }
 return {generate,configure};
})();
