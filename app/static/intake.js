'use strict';
// The PIC's submission to Finance: the six required fields filled, open checks acknowledged in a note, the statement
// ticked. The server checks all of it again; this only explains the choice before it is sent.
function submitIssues(detail){
  const checks=window.amigaReviewChecks(detail),titles=new Map();
  // Registering the vendor settles these two: its account becomes verified and its invoices can be compared.
  const settled=submitAddsVendor(detail)?['BANK_UNVERIFIED','DUPLICATE_CHECK']:[];
  [...checks.blockers,...checks.sources].filter(check=>!settled.includes(check.code)).forEach(check=>titles.set(check.code,checkTitle(check)));
  const tax=detail.draft?.tax?.status;
  if(tax&&tax!=='COMPUTED')titles.set('TAX',checkTitle(tax==='NOT_SELECTED'?{code:'TAX_SELECTION_REQUIRED',message:'Jenis pajak belum dipilih'}:{code:'TAX_NOT_COMPUTED',message:'Nominal pajak belum dapat dihitung'}));
  return [...titles.values()];
}
// A vendor the client's master does not know yet is registered with this submission; there is no way around it.
const submitAddsVendor=detail=>!(detail.missing_required||[]).length&&detail.approval?.vendor_known===false;
// One button: red fields are pointed out first, unsaved edits are saved as a draft, and only then the dialog opens.
// The dialog reads the saved version, so what the PIC confirms is what Finance receives.
async function openSubmit(){
  if(!state.detail?.can_submit)return;
  const problems=$$('[data-field]').filter(input=>fieldProblem(input));
  if(problems.length){
    const names=[...new Set(problems.map(input=>fieldLabel(input.dataset.field)))];
    toast(`Perbaiki ${names.length} isian merah dulu: ${names.slice(0,4).join(', ')}${names.length>4?', dan lainnya':''}.`);
    jumpToField(problems[0].dataset.field);return;
  }
  if(state.dirty){
    $('#submit-open').disabled=true;$('#review-error').textContent='';
    try{await saveDraft(PIC_DRAFT_REASON);}catch(error){showSaveError(error);return;}finally{updateApproval();}
  }
  const detail=state.detail;if(!detail?.can_submit)return;
  const invoice=detail.draft.invoice,missing=detail.missing_required||[],issues=submitIssues(detail),vendor=submitAddsVendor(detail);
  $('#submit-form').reset();$('#submit-error').textContent='';delete $('#submit-form').dataset.tried;
  $('#submit-summary').innerHTML=[['Vendor',invoice.vendor_name],['Nomor invoice',invoice.invoice_number],['Total tagihan',money(invoice.stated_total)],['Rekening tujuan',`${invoice.payment?.bank_name||'-'} ${invoice.payment?.account_number||''}`]].map(([key,value])=>`<dt>${escapeHTML(key)}</dt><dd>${escapeHTML(value??'-')}</dd>`).join('');
  $('#submit-missing').hidden=!missing.length;
  $('#submit-missing').innerHTML=missing.length?`<strong>Lengkapi dulu isian wajib</strong><ul>${missing.map(path=>`<li>${escapeHTML(fieldLabel(path))}</li>`).join('')}</ul>`:'';
  $('#submit-vendor').hidden=!vendor;
  $('#submit-vendor').innerHTML=vendor?`<strong>Vendor baru akan didaftarkan</strong><p>${escapeHTML(invoice.vendor_name)} belum ada di master vendor klien ini. Saat diajukan, vendor ini didaftarkan dengan rekening ${escapeHTML(invoice.payment?.bank_name||'')} ${escapeHTML(invoice.payment?.account_number||'')} dari invoice. Finance dan Manajer Keuangan AMIGA melihat tanda "Vendor baru, didaftarkan PIC".</p>`:'';
  $('#submit-issues').hidden=!issues.length;
  $('#submit-issues').innerHTML=issues.length?`<strong>${issues.length} kendala masih terbuka</strong><p>Invoice tetap boleh diajukan. Tulis alasannya di catatan. Finance dan Manajer Keuangan AMIGA tetap memeriksa.</p><ul>${issues.map(title=>`<li>${escapeHTML(title)}</li>`).join('')}</ul>`:'';
  $('#submit-note-title').textContent=issues.length||vendor?'Catatan untuk Finance (wajib)':'Catatan untuk Finance (opsional)';
  $('#submit-consent-text').textContent=detail.signature?.consent_text||'';
  updateSubmitConfirm();$('#submit-dialog').showModal();$('#submit-note').focus();
}
function submitProblems(){
  const detail=state.detail,noteNeeded=submitIssues(detail).length||submitAddsVendor(detail);
  return {note:noteNeeded&&$('#submit-note').value.trim().length<5?'Tulis catatan minimal 5 karakter: kenapa invoice ini tetap diajukan.':'',
    consent:$('#submit-consent').checked?'':'Centang pernyataan ini sebelum mengajukan.'};
}
// The confirm button stays clickable; after the first try, whatever is still missing turns red in the dialog.
function updateSubmitConfirm(){
  const detail=state.detail;if(!detail)return;
  $('#submit-confirm').disabled=(detail.missing_required||[]).length>0;
  const problems=submitProblems(),tried=$('#submit-form').dataset.tried==='1';
  [['note','#submit-note-error','#submit-note'],['consent','#submit-consent-error','#submit-consent']].forEach(([key,error,input])=>{
    const text=tried?problems[key]:'';$(error).hidden=!text;$(error).textContent=text;$(input).closest('label').classList.toggle('invalid',!!text);});
}
['#submit-consent','#submit-note'].forEach(selector=>{$(selector).addEventListener('input',updateSubmitConfirm);$(selector).addEventListener('change',updateSubmitConfirm);});
$('#submit-open').addEventListener('click',openSubmit);
['#close-submit','#cancel-submit'].forEach(selector=>$(selector).addEventListener('click',()=>$('#submit-dialog').close()));
$('#submit-form').addEventListener('submit',async event=>{
  event.preventDefault();$('#submit-form').dataset.tried='1';updateSubmitConfirm();
  const problems=submitProblems();if(problems.note||problems.consent){(problems.note?$('#submit-note'):$('#submit-consent')).focus();return;}
  $('#submit-confirm').disabled=true;$('#submit-error').textContent='';
  const note=$('#submit-note').value.trim();
  try{await api('/requests/'+state.current+'/submit',{method:'POST',json:{expected_version:state.detail.current_version,consent:true,note:note||null}});$('#submit-dialog').close();await loadDetail(state.current);toast('Diajukan ke Finance. Koreksi berikutnya dilakukan Finance.');}
  catch(error){$('#submit-error').textContent=error.message;updateSubmitConfirm();
    // A conflict means the invoice moved on in another session: show its new state instead of a stale form. An account
    // that belongs to another vendor stays in the dialog, so the PIC can read which vendor name to use.
    if(error.status===409&&error.code!=='VENDOR_EXISTS'){$('#submit-dialog').close();toast(error.message);await loadDetail(state.current);}}
});
