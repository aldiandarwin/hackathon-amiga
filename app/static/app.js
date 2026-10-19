'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {user:null,client:null,items:[],filter:'ALL',current:null,detail:null,invoice:null,dirty:false,queueTimer:null,detailTimer:null,fieldErrors:{}};
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statuses = {QUEUED:['Menunggu proses','processing'],PROCESSING:['Sedang diproses','processing'],READY_FOR_REVIEW:['Siap diperiksa','ready'],EXCEPTION:['Perlu perhatian','exception'],AMIGA_REVIEWED:['Menunggu manajer keuangan','ready'],AMIGA_APPROVED:['Disetujui manajer keuangan','approved'],RETURNED:['Dikembalikan manajer keuangan','exception'],INTAKE:['Belum diajukan','processing']};
// INTAKE is a display bucket, not a status: read but not yet submitted by its PIC. The status keeps the check result.
// A submitted invoice whose only open items are source checks, which Finance confirms while signing, is ready for Finance.
// Queue rows carry issue_count; the review screen counts the same blockers from its approval and tax.
const openBlockers = r => r.issue_count ?? ((r.approval?.blocking_checks||[]).length+(['NOT_SELECTED','NOT_COMPUTED'].includes(r.draft?.tax?.status)?1:0));
const shownStatus = r => r.stage==='INTAKE'&&r.current_version>0?'INTAKE':r.stage==='FINANCE'&&r.status==='EXCEPTION'&&!openBlockers(r)?'READY_FOR_REVIEW':r.status;
const ROLES={PIC:'PIC klien',FINANCE_REVIEWER:'Finance reviewer',AMIGA_DIRECTOR:'Manajer keuangan'};
const isDirector=()=>state.user?.role==='AMIGA_DIRECTOR';
const valueAt=(object,path)=>path.replace(/\[(\d+)\]/g,'.$1').split('.').reduce((value,key)=>value?.[key],object);
const money = value => window.amigaNumbers.currency(value);
const displayField = (path,value) => value == null ? 'Kosong' : typeof value === 'boolean' ? (value?'Ya':'Tidak') : window.amigaNumbers.isField(path) ? window.amigaNumbers.format(value,!path.endsWith('.quantity')) : String(value);
const date = value => new Intl.DateTimeFormat('id-ID',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(value));
const dateTime = value => new Intl.DateTimeFormat('id-ID',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(value));
// Stage 6: people read field names, not data paths such as line_items[0].quantity.
const FIELD_LABELS={vendor_name:'Nama vendor',vendor_npwp:'NPWP vendor',buyer_name:'Nama pembeli',buyer_npwp:'NPWP pembeli',invoice_number:'Nomor invoice',po_number:'Nomor PO',invoice_date:'Tanggal invoice',due_date:'Jatuh tempo',faktur_number:'Nomor faktur pajak',faktur_date:'Tanggal faktur',currency:'Mata uang',stated_subtotal:'Subtotal',stated_discount_total:'Diskon',stated_other_charges_total:'Biaya lain',stated_tax_total:'PPN tertulis',stated_total:'Total tagihan sebelum PPh','payment.bank_name':'Nama bank','payment.account_number':'Nomor rekening','payment.account_holder':'Pemilik rekening',line_items:'Rincian barang',description:'Deskripsi',quantity:'Jumlah',unit_price:'Harga satuan',stated_line_total:'Total baris'};
function fieldLabel(path){const line=/^line_items\[(\d+)\](?:\.(\w+))?$/.exec(path||'');if(line)return `Baris ${Number(line[1])+1}`+(line[2]?' · '+(FIELD_LABELS[line[2]]||line[2]):'');const tax=/^tax_selection\.(\w+)$/.exec(path||'');if(tax)return {pph:'Jenis PPh',ppn:'PPN',recipient_has_npwp:'Status NPWP penerima',faktur_number:'Nomor faktur pajak'}[tax[1]]||tax[1];return FIELD_LABELS[path]||path;}
function checkTitle(c){return (typeof window.amigaLabel==='function'&&window.amigaLabel(c.code))||c.message;}
const READERS={'global.amazon.nova-2-lite-v1:0':'Amazon Nova 2 Lite'};
function readerNote(source){
  if(!source||!source.mode)return '';
  if(source.mode==='SAVED_OPENAI_RESPONSE')return 'Contoh sintetis: memakai hasil baca yang sudah tersimpan, tanpa panggilan AI baru.';
  const seconds=source.duration_ms?` dalam ${(source.duration_ms/1000).toLocaleString('id-ID',{maximumFractionDigits:1})} detik`:'';
  return source.fallback_from?`Dibaca AI cadangan${seconds}. Periksa hasilnya dengan dokumen.`:`Dibaca AI${seconds}.`;
}
const statusHTML = value => {const [label,style]=statuses[value]||[value,'processing'];return `<span class="status ${style}">${escapeHTML(label)}</span>`;};
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,5500);}
async function api(path,options={}){
  const headers={...options.headers};
  if(state.user) headers['X-CSRF-Token']=state.user.csrf;
  if(options.json!==undefined){headers['Content-Type']='application/json';options.body=JSON.stringify(options.json);delete options.json;}
  const response=await fetch('/api/v1'+path,{...options,headers,credentials:'same-origin'});
  const data=await response.json().catch(()=>({message:'Respons server tidak dapat dibaca.'}));
  if(!response.ok){const error=new Error(data.message||'Permintaan gagal.');error.code=data.code;error.field=data.field;error.status=response.status;if(response.status===401&&path!='/login')showLogin();throw error;}
  return data;
}
const optionOf=(value,label)=>{const element=document.createElement('option');element.value=value;element.textContent=label;return element;};
// The topbar lists the session's clients; with more than one, "Semua klien" shows the whole portfolio at once.
function fillClientSelect(){$('#client-select').replaceChildren(...(state.user.clients.length>1?[optionOf('','Semua klien')]:[]),...state.user.clients.map(c=>optionOf(c.id,c.name)));$('#client-select').value=state.client??'';}
function showLogin(){clearTimeout(state.queueTimer);clearTimeout(state.detailTimer);state.user=null;state.current=null;state.detail=null;state.items=[];state.invoice=null;state.dirty=false;$('#workspace').hidden=true;$('#login-screen').hidden=false;$('#invoice-rows').replaceChildren();$('#invoice-fields').replaceChildren();$('#history-panel').replaceChildren();$('#pdf-preview').replaceChildren();$('#voucher-current').replaceChildren();$('#voucher-history').replaceChildren();$('#tax-panel').replaceChildren();$('#tax-panel').hidden=true;if(typeof resetBatchWorkspace==='function')resetBatchWorkspace();}
async function enter(){
  const requestLink=/^#request=([0-9a-f-]{36})$/.exec(location.hash);
  // Several clients open on all of them at once; the sample buttons and the batch history ask for one client.
  state.user=await api('/session');if(!requestLink){location.replace('/');return;}state.client=state.user.clients.length>1?'':state.user.clients[0]?.id;fillClientSelect();
  $('#user-name').textContent=state.user.name;$('#user-role').textContent=ROLES[state.user.role]||state.user.role;document.body.classList.toggle('role-director',isDirector());$('#nav-upload').hidden=state.user.role!=='PIC';$('#nav-handover').hidden=state.user.role!=='PIC';$('#nav-approvals').hidden=state.user.role==='PIC';$('#avatar').textContent=state.user.name.split(' ').map(s=>s[0]).slice(0,2).join('');
  // The Manajer Keuangan opens on the vouchers that wait for the final approval.
  state.items=[];state.filter=isDirector()?'AMIGA_REVIEWED':state.user.role==='PIC'?'INTAKE':'ALL';$('#search').value='';$$('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter===state.filter));renderQueue();
  $('#login-screen').hidden=true;$('#workspace').hidden=false;$('#password').value='';
  if(typeof loadTaxRules==='function')loadTaxRules();
  await showQueue(false);updateBudget();
  // The Next.js queue dashboard links rows here as #request=<id>.
  const link=/^#request=([0-9a-f-]{36})$/.exec(location.hash);
  if(link){history.replaceState(null,'',location.pathname+'#request='+link[1]);await openReview(link[1]);}
}
$('#login-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;$('#login-error').textContent='';try{await api('/login',{method:'POST',json:{email:$('#email').value,password:$('#password').value}});history.replaceState(null,'',location.pathname+location.hash);await enter();}catch(error){$('#login-error').textContent=error.message;}finally{button.disabled=false;}});
$('#logout').addEventListener('click',async()=>{if(!canLeave())return;try{await api('/logout',{method:'POST'});showLogin();}catch(error){toast(error.message);}});
function canLeave(){return !state.dirty||window.confirm('Ada koreksi yang belum disimpan. Tinggalkan perubahan?');}
async function showQueue(confirm=true){if(confirm){if(canLeave())location.assign('/');return;}clearTimeout(state.detailTimer);state.current=null;state.detail=null;state.dirty=false;document.body.classList.remove('reviewing');$('#review-screen').hidden=true;$('#queue-screen').hidden=false;$('#breadcrumb').textContent='Invoice';$('#pdf-preview').replaceChildren();window.scrollTo({top:0});await loadQueue();if(typeof loadBatches==='function')loadBatches();}
$('#nav-queue').addEventListener('click',()=>showQueue());$('#back').addEventListener('click',()=>showQueue());
$('#client-select').addEventListener('change',async()=>{if(!canLeave()){$('#client-select').value=state.client;return;}state.client=$('#client-select').value;location.assign('/?client='+encodeURIComponent(state.client));});
async function loadQueue(){
  clearTimeout(state.queueTimer);if(!state.user||state.client==null)return;
  const client=state.client;
  try{const data=await api('/requests'+(client?'?client_id='+encodeURIComponent(client):''));if(client!==state.client)return;state.items=data.items;renderQueue();}
  catch(error){toast(error.message);}
  if(state.user&&!state.current&&state.items.some(r=>['QUEUED','PROCESSING'].includes(r.status)))state.queueTimer=setTimeout(loadQueue,2000);
}
function queueIssue(row){
  if(row.needs_other_reviewer)return 'Perlu reviewer Finance lain';
  if(row.returned_to_pic)return 'Dikembalikan Finance';
  if(row.error_code)return window.amigaReadFailure(row.error_code).title;
  const code=row.issue_codes?.[0];
  if(code)return (typeof window.amigaLabel==='function'?window.amigaLabel(code):code)+((row.issue_count||0)>1?' · '+(row.issue_count-1)+' kendala lainnya':'');
  return row.source_check_count?row.source_check_count+' pemeriksaan sumber oleh Finance':'';
}
function renderQueue(){
  const search=$('#search').value.toLowerCase().trim();
  const rows=state.items.filter(r=>(state.filter==='ALL'||shownStatus(r)===state.filter)&&[r.filename,r.invoice?.vendor_name,r.invoice?.invoice_number].join(' ').toLowerCase().includes(search));
  $('#nav-count').textContent=state.items.length;$('#total-count').textContent=state.items.length;$('#ready-count').textContent=state.items.filter(r=>shownStatus(r)==='READY_FOR_REVIEW').length;$('#exception-count').textContent=state.items.filter(r=>shownStatus(r)==='EXCEPTION').length;
  $('#invoice-rows').innerHTML=rows.map(r=>`<tr><td><div class="vendor-cell"><span class="file-icon">▤</span><div><strong>${escapeHTML(r.invoice?.vendor_name||r.filename)}</strong><small>${state.client?'':escapeHTML(r.client_name||'')+' · '}${escapeHTML(r.invoice?.invoice_number||(r.error_code?window.amigaReadFailure(r.error_code).title:['QUEUED','PROCESSING'].includes(r.status)?'Menunggu dibaca AI':'Data invoice belum terbaca'))} · ${r.mode==='REPLAY'?'Contoh':'Unggahan'}</small></div></div></td><td class="date-cell">${date(r.created_at)}</td><td class="money">${money(r.invoice?.stated_total)}${r.net_payable!=null?`<small>${r.status==='AMIGA_APPROVED'?'Disetujui':'Rencana ke vendor'} ${money(r.net_payable)}</small>`:''}</td><td>${statusHTML(shownStatus(r))}<small class="queue-issue">${escapeHTML(queueIssue(r))}</small></td><td><button class="review-link" data-request="${escapeHTML(r.id)}">Periksa ↗</button></td></tr>`).join('');
  $('#empty-state').hidden=rows.length>0;$('#empty-state h3').textContent=state.items.length?'Tidak ada hasil yang cocok':'Mulai dari satu invoice';$('#empty-state p').textContent=state.items.length?'Coba kata kunci atau filter lain.':'Unggah invoice Anda, atau coba contoh di bawah.';$('#row-count').textContent=`${rows.length} dari ${state.items.length} invoice`;
  $$('[data-request]').forEach(button=>button.addEventListener('click',()=>openReview(button.dataset.request)));
  // Samples and the demo batch land in one client, so they wait until one is chosen.
  $$('[data-sample]').forEach(button=>button.disabled=!state.client);$('#demo-batch').disabled=!state.client;$('#sample-hint').hidden=Boolean(state.client);
}
$$('[data-filter]').forEach(button=>button.addEventListener('click',()=>{state.filter=button.dataset.filter;$$('[data-filter]').forEach(b=>b.classList.toggle('active',b===button));renderQueue();}));$('#search').addEventListener('input',renderQueue);
async function updateBudget(){try{const b=await api('/budget');const bedrock=b.bedrock&&b.bedrock.available!==false?`Bedrock terpakai US$${Number(b.bedrock.usage_cost_upper_estimate_usd).toFixed(4)} dari US$${b.bedrock.operational_ceiling_usd}`:'Bedrock belum tercatat';$('#budget-summary').textContent=`Pembaca utama: ${b.reader==='openai'?'OpenAI':'AWS Bedrock'} · ${bedrock} · ${b.available===false?'cadangan OpenAI tidak tersedia':'cadangan OpenAI '+b.remaining_calls+' slot'}`; }catch{$('#budget-summary').textContent='Informasi anggaran sementara tidak tersedia.';}}
$$('[data-sample]').forEach(button=>button.addEventListener('click',async()=>{button.disabled=true;try{const result=await api('/demo/'+button.dataset.sample+'?client_id='+encodeURIComponent(state.client),{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()}});await openReview(result.request_id);toast(result.created?'Contoh ditambahkan tanpa biaya API baru.':'Contoh ini sudah ada. Membuka hasil tersimpan.');}catch(error){toast(error.message);}finally{button.disabled=false;}}));
async function openReview(id){
  if(state.current!==id&&!canLeave())return;clearTimeout(state.queueTimer);clearTimeout(state.detailTimer);state.current=id;state.dirty=false;state.detail=null;state.fieldErrors={};state.reviewSection='invoice';state.itemIndex=0;setMobileReviewView('data');
  $$('[data-review-guide]').forEach(panel=>{panel.hidden=true;panel.replaceChildren();delete panel.dataset.guideState;});
  $('#review-section-nav').hidden=true;$('#review-checks-section').hidden=true;$('#payment-overview').hidden=true;$('#payment-overview').replaceChildren();$('#signature-summary').replaceChildren();document.body.classList.add('reviewing');$('#queue-screen').hidden=true;$('#review-screen').hidden=false;$('#evidence-banner').hidden=true;$('#voucher-frame').removeAttribute('src');delete $('#voucher-frame').dataset.src;$('#breadcrumb').textContent='Review invoice';$('#review-title').textContent='Memuat invoice…';$('#review-form').hidden=true;$('#review-error').textContent='';$('#checks').replaceChildren();if(typeof resetRobot==='function')resetRobot();$('#edit-reason').value='';
  $('#retry-form').reset();$('#decision-error').textContent='';showDoc('invoice');switchPanel(isDirector()?'voucher':'fields');window.scrollTo({top:0});await loadDetail(id,true);
}
async function loadDetail(id,first=false){
  try{const detail=await api('/requests/'+id);if(state.current!==id)return;
    if(state.detail&&detail.current_version!==state.detail.current_version){
      if($('#sign-dialog').open)$('#sign-dialog').close();
      if(state.dirty){$('#review-error').textContent='Versi berubah di sesi lain. Salin koreksi yang diperlukan lalu buka ulang invoice.';$('#sign-open').disabled=true;clearTimeout(state.detailTimer);return;}
    }
    state.detail=detail;
    if(first){$('#pdf-preview').replaceChildren(...Array.from({length:detail.page_count},(_,i)=>{const img=document.createElement('img');img.src='/api/v1/requests/'+detail.id+'/preview/'+(i+1);img.alt='Invoice asli, halaman '+(i+1);img.loading=i?'lazy':'eager';img.addEventListener('load',updatePageIndicator);return img;}));$('#pdf-open').href=detail.document_url;$('#file-proof').hidden=!detail.original_file?.verified;$('#file-proof').textContent='Asli';$('#file-proof').setAttribute('aria-label','File asli terverifikasi tidak berubah');$('#file-proof').title='File asli tersimpan permanen di database dan hash SHA-256 masih sama dengan saat diunggah.';}
    $('#review-title').textContent=detail.draft?.invoice?.invoice_number||detail.filename;
    $('#review-status').innerHTML=statusHTML(shownStatus(detail));$('#pdf-caption').textContent=detail.original_file?.stored_in_database?'File asli tersimpan permanen di database sebagai pembanding.':`Dokumen asli tersimpan · ${detail.page_count} halaman`;const note=readerNote(detail.draft?.source);$('#reader-note').hidden=!note;$('#reader-note').textContent=note;$('#reader-note').title=detail.draft?.source?.provider?`Pembaca: ${detail.draft.source.provider} · ${detail.draft.source.model||''}`:'';
    const pending=['QUEUED','PROCESSING'].includes(detail.status);$('#processing-state').hidden=!pending;
    if(detail.draft&&!state.dirty){state.invoice=structuredClone(detail.draft.invoice);renderChecks(detail);renderFields();if(typeof renderTaxPanel==='function')renderTaxPanel(detail);renderHistory(detail.audit);$('#review-form').hidden=state.reviewSection==='checks';$('#edit-reason').disabled=!detail.can_edit;}
    else if(!pending&&!detail.draft){$('#review-form').hidden=true;$('#review-section-nav').hidden=true;$('#review-checks-section').hidden=false;$('#checks').innerHTML='<div class="check-box"><strong>Proses sudah berhenti</strong><p>File asli tetap tersedia. Periksa riwayat atau teruskan ID request ke admin untuk penanganan.</p></div>';$('#review-error').textContent=window.amigaReadFailure(detail.error_code).message;renderHistory(detail.audit);}
    renderDecision(detail);renderHistory(detail.audit);
    clearTimeout(state.detailTimer);
    const rendering=['PENDING','RENDERING'];
    if(pending||rendering.includes(detail.voucher?.render_status)||rendering.includes(detail.signature?.signed_voucher?.render_status))state.detailTimer=setTimeout(()=>loadDetail(id),1500);else updateBudget();
  }catch(error){$('#review-error').textContent=error.message;}
}
function renderGuide(){
  if(!state.detail)return;
  const guide=window.amigaReviewGuide(state.detail,state.user,state.dirty);
  const steps=['Unggah','Ekstraksi AI','Pengajuan PIC','Finance','Manajer Keuangan','Final'];
  const key=JSON.stringify([guide,state.reviewSection,state.detail.approval?.blocking_checks?.map(check=>check.code)]);
  $$('[data-review-guide]').forEach(panel=>{
    panel.hidden=false;
    if(panel.dataset.guideState===key)return;panel.dataset.guideState=key;
    if(panel.closest('#fields-panel')){
      panel.className='review-context '+guide.tone;
      const checks=window.amigaReviewChecks(state.detail),count=new Set(checks.blockers.map(c=>c.code)).size;
      const task={invoice:'Cocokkan informasi invoice',identity:'Periksa identitas dan faktur pajak',items:'Cocokkan item dengan dokumen',amounts:'Cocokkan nominal dan pilihan pajak',bank:'Periksa rekening tujuan',checks:'Hal yang perlu ditindaklanjuti'};
      const title=state.detail.can_edit&&!state.dirty&&!['RETURNED','AMIGA_REVIEWED','AMIGA_APPROVED'].includes(state.detail.status)&&state.detail.approval?.reason_code!=='UPLOADER_CANNOT_REVIEW'?(task[state.reviewSection]||guide.title):guide.title;
      panel.innerHTML=`<div><span class="review-stage">${escapeHTML(steps[guide.phase])}</span><strong>${escapeHTML(title)}</strong></div><div class="review-context-actions"><button type="button" class="review-checks-link ${count?'has-issues':''}" data-review-section-link="checks">${count?count+' kendala':'Pemeriksaan'}</button>${['copy','voucher','director_login'].includes(guide.action)?`<button type="button" class="guide-action" data-guide-action="${guide.action}">${escapeHTML(guide.actionLabel)}</button>`:''}</div>`;
      return;
    }
    panel.className='review-guide '+guide.tone;
    panel.innerHTML=`<ol class="review-steps" aria-label="Tahap invoice">${steps.map((label,i)=>`<li class="${i<guide.phase?'done':i===guide.phase?'current':''}" ${i===guide.phase?'aria-current="step"':''}><span>${i<guide.phase?'✓':i+1}</span>${label}</li>`).join('')}</ol><h2>${escapeHTML(guide.title)}</h2>${guide.message?`<p class="guide-message">${escapeHTML(guide.message)}</p>`:''}${guide.action?`<button type="button" class="guide-action" data-guide-action="${guide.action}">${escapeHTML(guide.actionLabel)}</button>`:''}`;
  });
  return guide;
}
function reviewSectionForField(path){
  if(path==='line_items'||path?.startsWith('line_items['))return 'items';
  if(path?.startsWith('payment.'))return 'bank';
  if(path?.startsWith('tax')||path?.startsWith('stated_'))return 'amounts';
  return ['vendor_npwp','buyer_name','buyer_npwp','po_number','faktur_number','faktur_date'].includes(path)?'identity':'invoice';
}
function selectReviewSection(section,resetScroll=true){
  state.reviewSection=section;
  $('#review-form').hidden=section==='checks'||!state.detail?.draft;
  $$('[data-review-section]').forEach(panel=>panel.hidden=panel.dataset.reviewSection!==section);
  $$('[data-review-section-link]').forEach(button=>{const active=button.dataset.reviewSectionLink===section;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
  if(resetScroll){
    $('#fields-panel').scrollTo({top:0});
    const first=section==='items'?`line_items[${state.itemIndex||0}].description`:$(`[data-review-section="${section}"] [data-field]`)?.dataset.field;
    if(first)showEvidence(first);
  }
  renderGuide();
}
function setMobileReviewView(view){
  $('#review-screen').dataset.mobileView=view;
  $$('[data-review-view]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.reviewView===view)));
}
$$('[data-review-view]').forEach(button=>button.addEventListener('click',()=>setMobileReviewView(button.dataset.reviewView)));
$('#fields-panel').addEventListener('click',event=>{const button=event.target.closest('[data-review-section-link]');if(button)selectReviewSection(button.dataset.reviewSectionLink);});
function selectReviewItem(index,showSource=true){
  state.itemIndex=Math.max(0,Math.min(index,state.invoice.line_items.length-1));
  $$('[data-line-index]').forEach(card=>card.hidden=Number(card.dataset.lineIndex)!==state.itemIndex);
  const select=$('#review-item-select');if(select)select.value=String(state.itemIndex);
  if($('#item-previous'))$('#item-previous').disabled=state.itemIndex===0;
  if($('#item-next'))$('#item-next').disabled=state.itemIndex>=state.invoice.line_items.length-1;
  if(showSource)showEvidence(`line_items[${state.itemIndex}].description`);
}
function jumpToField(path){
  switchPanel('fields');setMobileReviewView('data');
  if(path?.startsWith('tax_selection')||path?.startsWith('tax.')){jumpReview('tax');return;}
  selectReviewSection(reviewSectionForField(path));
  const line=/^line_items\[(\d+)\]/.exec(path||'');if(line)selectReviewItem(Number(line[1]));
  const input=$$('[data-field]').find(element=>element.dataset.field===path);
  if(input){input.scrollIntoView({block:'nearest',behavior:'smooth'});if(!input.disabled)input.focus({preventScroll:true});showEvidence(path);}
}
function openCorrectionDialog(){
  if(!state.detail?.can_edit||!state.dirty)return;
  $('#correction-error').textContent='';if(!$('#correction-dialog').open)$('#correction-dialog').showModal();
  $('#edit-reason').focus();
}
function jumpReview(action){
  if(action==='submit'){if(typeof openSubmit==='function')openSubmit();return;}
  if(action==='voucher'){switchPanel('voucher');showDoc('voucher');return;}
  if(action==='history'){switchPanel('history');return;}
  switchPanel('fields');setMobileReviewView('data');
  if(action==='reason'){openCorrectionDialog();return;}
  selectReviewSection(action==='tax'?'amounts':'checks');
  if(action==='tax'){
    const input=$('#tax-panel').querySelector('select');
    input?.scrollIntoView({block:'center',behavior:'smooth'});
    if(input&&!input.disabled)input.focus({preventScroll:true});
  }
}
$$('[data-review-guide]').forEach(panel=>panel.addEventListener('click',async event=>{
  const action=event.target.closest('[data-guide-action]')?.dataset.guideAction;if(!action)return;
  if(action==='director_login'){location.assign('/review?switch=1#request='+encodeURIComponent(state.current));return;}
  if(action==='copy'){try{await navigator.clipboard.writeText(state.current);toast('ID request disalin. Teruskan ke pihak yang memeriksa invoice ini.');}catch{toast('ID request: '+state.current);}return;}
  jumpReview(action);
}));
// Advice from window.amigaCheckHint (review-guide.js). It reads the form as it is now, so applied advice clears itself.
const PHOTO_CHECKS=new Set(['OCR_INCOMPLETE','VISUAL_REVIEW_REQUIRED','SOURCE_EVIDENCE_INVALID']);
const HINT_SECTIONS={TOTAL_MISMATCH:'amounts',SUBTOTAL_MISMATCH:'amounts',BANK_MISMATCH:'bank',POSSIBLE_DUPLICATE:'invoice'};
const hintFor=g=>window.amigaCheckHint?.(g,state.detail,state.invoice||state.detail.draft.invoice)||null;
const hintHTML=hint=>hint?`<p class="check-text">${escapeHTML(hint.text)}</p>${hint.advice?`<p class="check-advice"><strong>Saran</strong> ${escapeHTML(hint.advice)}</p>`:''}`:'';
const applyButton=(g,hint)=>hint&&(hint.fill||hint.tax)&&state.detail?.can_edit?`<button type="button" class="check-apply" data-hint="${escapeHTML(g.code)}">Pakai saran</button>`:'';
// Above a section's fields: the open checks that belong there, with the same advice as the list.
function renderSectionHints(){
  $$('[data-section-hints]').forEach(box=>{
    const found=(state.checkGroups||[]).filter(g=>(HINT_SECTIONS[g.code]||reviewSectionForField(g.fields.find(Boolean)))===box.dataset.sectionHints)
      .map(g=>[g,hintFor(g)]).filter(([,hint])=>hint);
    box.hidden=!found.length;
    box.innerHTML=found.map(([g,hint])=>`<div class="section-hint"><strong>${escapeHTML(checkTitle(g))}</strong>${hintHTML(hint)}${applyButton(g,hint)?`<div class="check-actions">${applyButton(g,hint)}</div>`:''}</div>`).join('')
      +(found.length&&state.dirty?'<p class="section-hint-note">Simpan koreksi supaya pemeriksaan dihitung ulang.</p>':'');
  });
}
// "Pakai saran" only fills the form. Finance still saves the correction with its reason, then decides.
function applyHint(code){
  const group=(state.checkGroups||[]).find(g=>g.code===code),hint=group&&hintFor(group);
  if(!hint||!state.detail?.can_edit)return;
  Object.entries(hint.fill||{}).forEach(([path,value])=>setValue(path,value));
  if(hint.tax&&typeof applyTaxHint==='function')applyTaxHint(hint.tax);
  // A suggested reason is a draft: the correction dialog always opens so Finance reads it before saving.
  if(hint.reason&&!$('#edit-reason').value.trim()){$('#edit-reason').value=hint.reason;state.reasonSuggested=true;}
  renderFields();markDirty();
  const first=Object.keys(hint.fill||{})[0];if(first)jumpToField(first);else jumpReview('tax');
  toast(state.detail.can_submit?'Saran diisi. Periksa angkanya, lalu simpan draf atau ajukan.':'Saran diisi. Periksa angkanya, lalu simpan koreksi.');
}
document.addEventListener('click',event=>{const button=event.target.closest('[data-hint]');if(button)applyHint(button.dataset.hint);});
function renderChecks(detail){let {blockers:checks,sources,notes}=window.amigaReviewChecks(detail);
  // One item per code: a photo has no text layer, so the same evidence check fails once for every field.
  const group=list=>[...list.reduce((map,c)=>{const g=map.get(c.code);if(g)g.fields.push(c.field);else map.set(c.code,{...c,fields:[c.field]});return map;},new Map()).values()];
  const where=g=>{const names=g.fields.filter(Boolean).map(fieldLabel);return names.length?` <small>(${escapeHTML(names.slice(0,5).join(', ')+(names.length>5?` dan ${names.length-5} lainnya`:''))})</small>`:'';};
  // "Panduan SOP" opens this check's card in the floating Robot Admin window (sop.js listens on #checks).
  const guide=g=>typeof window.amigaSopCard==='function'?` <button type="button" class="sop-link" data-sop-kode="${escapeHTML(g.code)}" aria-label="Panduan SOP: ${escapeHTML(checkTitle(g))}">Panduan SOP</button>`:'';
  const jump=g=>['TAX_PPN_CONFLICT','TAX_SELECTION_REQUIRED'].includes(g.code)?'<button type="button" class="check-jump" data-check-action="tax">Buka bagian pajak</button>':g.fields.find(Boolean)?` <button type="button" class="check-jump" data-check-field="${escapeHTML(g.fields.find(Boolean))}">Buka isian</button>`:'';
  // 15 Okt 2026, Aldian: each check says what is wrong in numbers and what is probably right. Finance decides.
  const item=g=>{const hint=hintFor(g);return `<li class="check-item"><strong>${escapeHTML(checkTitle(g))}</strong>${where(g)}${hint?hintHTML(hint):checkTitle(g)!==g.message?`<p class="check-text muted">${escapeHTML(g.message)}</p>`:''}<div class="check-actions">${applyButton(g,hint)}${jump(g)}${guide(g)}</div></li>`;};
  // A photo has no text layer, so its evidence checks fail on every field: one note replaces a badge on each.
  const photo=detail.media_type?.startsWith('image/'),scanned=photo?sources.filter(c=>PHOTO_CHECKS.has(c.code)):[];
  if(photo)sources=sources.filter(c=>!PHOTO_CHECKS.has(c.code));
  // Fields named by a failing check get a badge in the form, so the problem shows where it is.
  state.issueFields=new Set([...checks,...sources].map(c=>c.field).filter(Boolean));
  checks=group(checks);sources=group(sources);notes=group(notes);state.checkGroups=checks;
  const photoNote=scanned.length?`<li class="check-item"><strong>Dokumen foto</strong>${hintHTML(hintFor(scanned[0]))}<div class="check-actions">${guide({...scanned[0],fields:[]})}</div></li>`:'';
  const sourceCount=sources.length+(photoNote?1:0);
  $('#checks').innerHTML=(checks.length?`<details open class="check-box"><summary>${checks.length} kendala untuk dicek</summary><p>Saran dihitung dari angka invoice, tanpa AI. Keputusan tetap di tangan Anda.</p><ul class="check-list">${checks.map(item).join('')}</ul></details>`:'<div class="check-box good"><strong>Tidak ada kendala pada pemeriksaan data otomatis</strong><br>Finance tetap perlu memeriksa dokumen, pilihan pajak, dan kewenangan reviewer sebelum menyetujui.</div>')
    +(sourceCount?`<details ${checks.length?'':'open'} class="check-box source-review"><summary>${sourceCount} pemeriksaan sumber oleh Finance</summary><p>Cocokkan langsung dengan dokumen asli. Konfirmasi ini menjadi bagian dari pernyataan saat Finance menyetujui.</p><ul class="check-list">${photoNote}${sources.map(item).join('')}</ul></details>`:'')
    +(notes.length?`<details class="check-box review-notes"><summary>${notes.length} informasi tambahan</summary><ul class="check-list">${notes.map(item).join('')}</ul></details>`:'');
  renderSectionHints();
  if(!renderChecks.waiting&&window.amigaLabelsReady){renderChecks.waiting=true;window.amigaLabelsReady.then(()=>{if(state.detail===detail&&detail.draft)renderChecks(detail);}).catch(()=>{});}if(typeof renderRobotChecks==='function')renderRobotChecks(detail);}
$('#checks').addEventListener('click',event=>{const action=event.target.closest('[data-check-action]');if(action){jumpReview(action.dataset.checkAction);return;}const button=event.target.closest('[data-check-field]');if(button)jumpToField(button.dataset.checkField);});
function getValue(path){return path.replace(/\[(\d+)\]/g,'.$1').split('.').reduce((value,key)=>value?.[key],state.invoice);}
function setValue(path,value){const parts=path.replace(/\[(\d+)\]/g,'.$1').split('.');const last=parts.pop();let target=state.invoice;parts.forEach(p=>target=target[p]);target[last]=value.trim()===''?null:value;}
const DATE_FIELDS=new Set(['invoice_date','due_date','faktur_date']);
const blank=value=>value==null||(typeof value==='string'&&!value.trim());
const isRequired=path=>(state.detail?.required_fields||[]).includes(path);
const missingNow=()=>(state.detail?.required_fields||[]).filter(path=>blank(getValue(path)));
// A browser in English shows the picker as month/day; the Indonesian reading underneath removes the doubt.
const longDate=value=>{const d=/^(\d{4})-(\d{2})-(\d{2})$/.exec(value||'');return d?new Intl.DateTimeFormat('id-ID',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(Date.UTC(+d[1],+d[2]-1,+d[3]))):'';};
function inputField(label,path,wide=false){
  const value=getValue(path),numeric=window.amigaNumbers.isField(path),quantity=path.endsWith('.quantity');
  const currency=state.invoice.currency==='IDR'?'Rp':state.invoice.currency;
  const caption=label+(numeric&&!quantity&&currency?' ('+currency+')':'');
  const item=/^line_items\[(\d+)\]/.exec(path),accessible=caption+(item?', item '+(Number(item[1])+1):'');
  const evidence=state.detail.draft.source_evidence[path],changed=state.detail.draft.human_changed_fields.includes(path);
  const original=state.detail.original_values?.[path],display=value=>numeric?window.amigaNumbers.format(value,!quantity):value;
  const before=changed&&state.detail.original_values&&path in state.detail.original_values?`<span class="original-value">Nilai awal dari dokumen: ${escapeHTML(original==null?'kosong':display(original))}</span>`:'';
  const issue=state.issueFields?.has(path),errorId='error-'+path.replace(/[^a-z0-9]/gi,'-');
  const editable=state.detail.can_edit,required=isRequired(path);
  // Wajib/Opsional is the PIC's submission rule; Finance does not need it on every field.
  const tag=state.detail.can_submit?(required?'<span class="field-required">Wajib</span>':'<span class="field-optional">Opsional</span>'):'';
  const common=`data-field="${escapeHTML(path)}" aria-label="${escapeHTML(accessible)}" aria-describedby="${errorId}" ${required?'aria-required="true"':''} ${editable?'':'disabled'} class="${changed?'changed':''}"`;
  // 15 Okt 2026: a PIC typed 23022026 as a date. Dates and currency are picked; the server takes YYYY-MM-DD and IDR.
  const control=DATE_FIELDS.has(path)?`<input type="date" data-date ${common} value="${escapeHTML(value||'')}"><span class="date-reading">${escapeHTML(longDate(value))}</span>`
    :path==='currency'?`<select ${common}>${value?'':'<option value="" selected>Pilih mata uang</option>'}${[...new Set(['IDR',...(value?[value]:[])])].map(code=>`<option value="${escapeHTML(code)}" ${code===value?'selected':''}>${escapeHTML(code==='IDR'?'IDR · Rupiah':code)}</option>`).join('')}</select>`
    :`<input ${common} value="${escapeHTML(display(value))}" placeholder="Belum tersedia" ${numeric?'data-number inputmode="decimal"':''}>`;
  // One line of label and marks keeps both columns aligned. The source quote shows above the document on focus.
  return `<label class="${wide?'wide':''}${issue?' issue':''}"${evidence?` title="Sumber hal. ${evidence.page}: ${escapeHTML(evidence.raw_value)}"`:''}><span class="field-head"><span class="field-name">${escapeHTML(caption)}</span>${tag}${issue?'<span class="field-issue">Perlu dicek</span>':''}</span>${control}<span id="${errorId}" class="field-error" aria-live="polite" hidden></span>${before}</label>`;
}
function readFieldInput(input){
  delete state.fieldErrors[input.dataset.field];
  if(input.hasAttribute('data-date')){
    // A half-typed date reads as "" in the browser; it is shown in red instead of being saved as empty.
    if(!input.validity.badInput)setValue(input.dataset.field,input.value);
    input.parentElement.querySelector('.date-reading').textContent=longDate(input.validity.badInput?'':input.value);return;
  }
  if(!input.hasAttribute('data-number')){setValue(input.dataset.field,input.value);return;}
  const result=window.amigaNumbers.parse(input.value,valueAt(state.detail.draft.invoice,input.dataset.field));
  input.setCustomValidity(result.valid?'':'Format belum sesuai. Contoh: 25.000 atau 25.000,50.');
  if(result.valid)setValue(input.dataset.field,result.value??'');
}
// Red means the field must change before the PIC can submit. Amber "Perlu dicek" stays for checks a note can explain.
function fieldProblem(input){
  const path=input.dataset.field;
  if(input.hasAttribute('data-number')&&!input.validity.valid)return input.validationMessage;
  if(input.hasAttribute('data-date')&&input.validity.badInput)return 'Tanggal belum lengkap. Pilih dari kalender.';
  if(state.fieldErrors[path])return state.fieldErrors[path];
  return state.detail?.can_edit&&isRequired(path)&&blank(getValue(path))?'Wajib diisi.':'';
}
function showFieldErrors(){
  $$('[data-field]').forEach(input=>{
    const problem=fieldProblem(input),label=input.closest('label'),error=label?.querySelector('.field-error');
    input.setAttribute('aria-invalid',String(!!problem));label?.classList.toggle('invalid',!!problem);
    if(error){error.hidden=!problem;error.textContent=problem;}
  });
}
const formatInvalid=()=>$$('[data-number],[data-date]').filter(input=>!input.validity.valid);
function renderFields(){
  const header=[['Nama vendor','vendor_name',true],['Nomor invoice','invoice_number'],['Mata uang','currency'],['Tanggal invoice','invoice_date'],['Jatuh tempo','due_date']];
  const totals=[['Subtotal','stated_subtotal'],['Diskon','stated_discount_total'],['Biaya lain','stated_other_charges_total'],['PPN tertulis','stated_tax_total'],['Total tagihan sebelum PPh','stated_total']];
  const bank=[['Nama bank','payment.bank_name'],['Nomor rekening','payment.account_number'],['Pemilik rekening','payment.account_holder',true]];
  const identity=[['NPWP vendor','vendor_npwp'],['Nomor PO','po_number'],['Nama pembeli','buyer_name',true],['NPWP pembeli','buyer_npwp'],['Nomor faktur pajak','faktur_number'],['Tanggal faktur','faktur_date']];
  const hints=id=>`<div class="section-hints" data-section-hints="${id}" hidden></div>`;
  const group=(id,title,fields)=>`<section data-review-section="${id}" hidden><h3 class="review-section-title">${title}</h3>${hints(id)}<div class="field-grid">${fields.map(args=>inputField(...args)).join('')}</div></section>`;
  const items=state.invoice.line_items;
  const itemNav=`<div class="item-navigation"><button type="button" id="item-previous" aria-label="Item sebelumnya">←</button><label class="sr-only" for="review-item-select">Item yang dicocokkan</label><select id="review-item-select" ${items.length?'':'disabled'}>${items.length?items.map((item,i)=>`<option value="${i}">Item ${i+1} dari ${items.length}</option>`).join(''):'<option>Belum ada item</option>'}</select><button type="button" id="item-next" aria-label="Item berikutnya">→</button></div>`;
  const itemCards=items.map((item,i)=>`<div class="line-card" data-line-index="${i}" hidden><div class="line-head"><span>ITEM ${i+1}</span>${state.detail.can_edit?`<button type="button" class="line-delete" data-delete-line="${i}" aria-label="Hapus baris ${i+1}">Hapus item</button>`:''}</div><div class="field-grid">${inputField('Deskripsi',`line_items[${i}].description`,true)}${inputField('Kuantitas',`line_items[${i}].quantity`)}${inputField('Harga satuan',`line_items[${i}].unit_price`)}${inputField('Total baris',`line_items[${i}].stated_line_total`)}</div></div>`).join('');
  // Above every section: during intake, which fields hold the submission; afterwards, what the PIC handed to Finance.
  const submission=state.detail.submission,returned=state.detail.returned_to_pic;
  const intro=(returned?`<p class="intake-summary returned"><strong>Dikembalikan Finance ${escapeHTML(returned.by)}</strong> · ${dateTime(returned.at)} · Versi ${returned.version}<br>Alasan: ${escapeHTML(returned.reason)}</p>`:'')+(state.detail.can_submit?'<p class="required-legend" id="required-legend"></p>'
    :submission?`<p class="intake-summary"><strong>Diajukan PIC ${escapeHTML(submission.by)}</strong> · ${dateTime(submission.at)} · Versi ${submission.version}${submission.note?`<br>Catatan PIC: ${escapeHTML(submission.note)}`:''}</p>`:'');
  $('#invoice-fields').innerHTML=intro+group('invoice','Informasi invoice',header)+group('identity','Identitas & faktur pajak',identity.filter(args=>args[1] in state.invoice))+`<section data-review-section="items" hidden><h3 class="review-section-title">Rincian barang / jasa</h3>${hints('items')}${itemNav}${itemCards}${state.detail.can_edit?'<button type="button" class="add-line" id="add-line">+ Tambah item</button>':''}</section>`+group('bank','Rekening tujuan',bank);
  renderRequiredLegend();
  $('#amount-fields').innerHTML='<h3 class="review-section-title">Nominal pada invoice</h3>'+hints('amounts')+'<div class="field-grid">'+totals.map(args=>inputField(...args)).join('')+'</div>';
  $('#review-section-nav').hidden=false;
  $('[data-review-section-link="identity"]').hidden=!('vendor_npwp' in state.invoice);
  if(state.reviewSection==='identity'&&!('vendor_npwp' in state.invoice))state.reviewSection='invoice';
  $$('[data-field]').forEach(input=>{['input','change'].forEach(type=>input.addEventListener(type,()=>{readFieldInput(input);markDirty();}));input.addEventListener('focus',()=>showEvidence(input.dataset.field));if(input.hasAttribute('data-number'))input.addEventListener('blur',()=>{if(input.validity.valid)input.value=window.amigaNumbers.format(getValue(input.dataset.field),!input.dataset.field.endsWith('.quantity'));});});
  $$('[data-delete-line]').forEach(button=>button.addEventListener('click',()=>{state.invoice.line_items.splice(Number(button.dataset.deleteLine),1);state.invoice.line_items.forEach((item,i)=>item.line_number=i+1);state.itemIndex=Math.min(state.itemIndex,state.invoice.line_items.length-1);markDirty();renderFields();}));
  $('#add-line')?.addEventListener('click',()=>{state.invoice.line_items.push({line_number:state.invoice.line_items.length+1,description:null,quantity:null,unit_price:null,stated_line_total:null});state.itemIndex=state.invoice.line_items.length-1;markDirty();renderFields();});
  $('#item-previous').addEventListener('click',()=>selectReviewItem(state.itemIndex-1));
  $('#item-next').addEventListener('click',()=>selectReviewItem(state.itemIndex+1));
  $('#review-item-select').addEventListener('change',event=>selectReviewItem(Number(event.target.value)));
  selectReviewItem(state.itemIndex||0,false);selectReviewSection(state.reviewSection||'invoice',false);renderSectionHints();updateSave();
}
function markDirty(){state.dirty=formatInvalid().length>0||JSON.stringify(state.invoice)!==JSON.stringify(state.detail.draft.invoice)||(typeof taxDirty==='function'&&taxDirty());renderSectionHints();renderRequiredLegend();updateSave();}
// 16 Okt 2026, Aldian: name only the required fields still empty; once all are filled, just ask for a last comparison.
function renderRequiredLegend(){
  const legend=$('#required-legend');if(!legend)return;
  const missing=missingNow();
  legend.classList.toggle('has-missing',missing.length>0);
  legend.textContent=missing.length?`Isian wajib yang masih kosong: ${missing.map(fieldLabel).join(', ')}.`
    :'Cocokkan isian dengan invoice asli sebelum diajukan.';
}
function updateSave(){const detail=state.detail,invalid=formatInvalid().length>0;$('#save').disabled=!detail?.can_edit||!state.dirty||invalid;
  showFieldErrors();
  // Each section tab counts its red fields, so an empty account number shows on Rekening before anyone opens it.
  $$('#review-section-nav button').forEach(button=>{const count=$$('[data-field]').filter(input=>reviewSectionForField(input.dataset.field)===button.dataset.reviewSectionLink&&fieldProblem(input)).length;button.classList.toggle('has-invalid',count>0);button.dataset.problems=count||'';button.title=count?count+' isian perlu diperbaiki pada bagian ini':'';});
  // The action bar says why signing is not possible, so a refusal such as self-approval explains itself (brief scenario 5).
  // A failed render never finishes by itself, so it outranks "waiting for the BOD".
  const failed=detail?.voucher?.render_status==='FAILED'?detail.voucher:detail?.signature?.signed_voucher?.render_status==='FAILED'?detail.signature.signed_voucher:null;
  const blocked=detail&&!isDirector()?(failed?(failed===detail.voucher?'Draf voucher':'Voucher final')+' gagal dibuat. '+(failed.can_retry?'Ulangi dari tab Voucher & persetujuan.':'Finance perlu membuat ulang PDF.'):detail.status==='AMIGA_APPROVED'?'Selesai disetujui Manajer Keuangan AMIGA':detail.status==='AMIGA_REVIEWED'?'Menunggu persetujuan Manajer Keuangan AMIGA':detail.approval?.can_approve?'':detail.approval?.reason||''):'';
  $('#edit-state').textContent=invalid?'Periksa isian merah sebelum menyimpan':state.dirty?(detail?.can_submit?'Ada perubahan belum disimpan · ikut tersimpan saat diajukan':'Simpan koreksi dulu sebelum menyetujui'):blocked||(!detail?.can_edit?(state.user?.role==='PIC'&&detail?.stage!=='INTAKE'?'Sudah diajukan · koreksi berikutnya oleh Finance':'Akses baca · koreksi oleh Finance'):'Belum ada perubahan');updateApproval();}
$('#edit-reason').addEventListener('input',updateSave);
// The PIC's submission note explains the draft it hands over, so a PIC save needs no reason of its own. Finance still writes one.
const PIC_DRAFT_REASON='Disimpan PIC sebelum pengajuan ke Finance';
async function saveDraft(reason){
  const json={expected_version:state.detail.current_version,invoice:state.invoice,reason};
  if(typeof taxDirty==='function'&&taxDirty()){json.tax_selection=readTax($('#tax-panel .tax-controls'));const problem=taxError(json.tax_selection);if(problem)throw new Error(problem);}
  const detail=await api('/requests/'+state.current+'/draft',{method:'PATCH',json});
  state.dirty=false;state.fieldErrors={};state.reasonSuggested=false;$('#edit-reason').value='';if($('#correction-dialog').open)$('#correction-dialog').close();await loadDetail(detail.id);
  return detail;
}
function showSaveError(error){
  $('#review-error').textContent=error.message;$('#correction-error').textContent=error.message;
  if(error.code==='VERSION_CONFLICT')toast('Versi berubah di sesi lain. Salin koreksi sebelum memuat ulang.');
  // The server names the field whose format it refused, so the message sits on that field in red.
  if(error.field){state.fieldErrors={[error.field]:`Format ${fieldLabel(error.field).toLowerCase()} belum sesuai.`};$('#review-error').textContent='';if($('#correction-dialog').open)$('#correction-dialog').close();jumpToField(error.field);}
  updateSave();
}
$('#review-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const invalid=formatInvalid()[0];if(invalid){jumpToField(invalid.dataset.field);return;}
  const pic=state.detail.can_submit;
  if(!pic&&($('#edit-reason').value.trim().length<5||state.reasonSuggested)){state.reasonSuggested=false;openCorrectionDialog();return;}
  $('#save').disabled=true;$('#confirm-correction').disabled=true;$('#review-error').textContent='';$('#correction-error').textContent='';
  try{const detail=await saveDraft(pic?PIC_DRAFT_REASON:$('#edit-reason').value.trim());toast((pic?'Draf disimpan':'Koreksi disimpan')+' · versi '+detail.current_version);}
  catch(error){showSaveError(error);}
  finally{$('#confirm-correction').disabled=false;}
});
$('#correction-form').addEventListener('submit',event=>{event.preventDefault();$('#review-form').requestSubmit();});
['#close-correction','#cancel-correction'].forEach(selector=>$(selector).addEventListener('click',()=>$('#correction-dialog').close()));
function switchPanel(panel){$$('[data-panel]').forEach(b=>b.classList.toggle('active',b.dataset.panel===panel));$('#fields-panel').hidden=panel!=='fields';$('#history-panel').hidden=panel!=='history';$('#voucher-panel').hidden=panel!=='voucher';}
$$('[data-panel]').forEach(button=>button.addEventListener('click',()=>switchPanel(button.dataset.panel)));
function renderHistory(events){const labels={BATCH_RECEIVED:'Invoice masuk melalui batch',UPLOADED:'Invoice diunggah',EXTRACTED:'Ekstraksi selesai',DRAFT_EDITED:'Data invoice dikoreksi',INTAKE_SUBMITTED:'Diajukan PIC ke Finance',VENDOR_REGISTERED:'Vendor baru didaftarkan PIC',EXTRACTION_FAILED:'Ekstraksi dihentikan',PROCESS_INTERRUPTED:'Proses terputus',REVIEW_APPROVED:'Review Finance disetujui',APPROVAL_INVALIDATED:'Approval perlu diperbarui',VOUCHER_READY:'Draf voucher tersedia',VOUCHER_FAILED:'Pembuatan draf voucher gagal',VOUCHER_RETRY:'Draf voucher dibuat ulang',SIGN_FAILED:'Persetujuan ditolak: password salah',DIRECTOR_APPROVED:'Disetujui manajer keuangan',DIRECTOR_RETURNED:'Dikembalikan manajer keuangan ke Finance',SIGNED_VOUCHER_READY:'Voucher final tersedia',SIGNED_VOUCHER_FAILED:'Pembuatan voucher final gagal',SIGNED_VOUCHER_RETRY:'Voucher final dibuat ulang',VOUCHER_SENT:'Voucher final dikirim ke klien lewat Telegram',VOUCHER_SEND_FAILED:'Pengiriman voucher ke klien belum berhasil'};const show=(value,path)=>displayField(path,value);$('#history-panel').innerHTML=events.map(e=>`<article class="audit-item"><strong>${escapeHTML(labels[e.action]||e.action)}</strong><small>${escapeHTML(e.actor)} · ${dateTime(e.created_at)}${e.version?' · Versi '+e.version:''}</small><p>${escapeHTML(e.reason)}</p>${e.action==='DRAFT_EDITED'?'<dl>'+Object.entries(e.changes).map(([key,value])=>`<dt>${escapeHTML(fieldLabel(key))}</dt><dd>${escapeHTML(show(value.before,key))} → ${escapeHTML(show(value.after,key))}</dd>`).join('')+'</dl>':''}</article>`).join('')||'<p class="muted">Belum ada perubahan.</p>';}

// Stage 8: both approvals live in the "Voucher & persetujuan" tab, and the sticky action bar opens the approval dialog.

function paymentSummaryHTML(detail,dirty=false,compact=false){
  const summary=window.amigaPaymentSummary(detail,dirty);
  const rows=summary.rows.map(row=>`<div><dt>${escapeHTML(row.label)}</dt><dd>${row.sign||''}${money(row.value)}</dd></div>`).join('');
  const note=summary.note?`<p class="payment-note">${escapeHTML(summary.note)}</p>`:'';
  if(compact)return `<section class="payment-overview compact ${summary.ready?'':'pending'}" aria-label="Ringkasan nominal"><div class="payment-total"><span>${escapeHTML(summary.label)}</span><strong>${summary.ready?money(summary.amount):escapeHTML(summary.pendingText)}</strong></div><details class="payment-details"><summary>Rincian perhitungan</summary>${summary.ready?`<dl class="payment-breakdown">${rows}</dl>`:`<p>Total tagihan pada dokumen: <strong>${money(summary.invoiceTotal)}</strong></p>`}${note}</details></section>`;
  return `<section class="payment-overview ${summary.ready?'':'pending'}" aria-label="Ringkasan nominal"><div class="payment-total"><span>${escapeHTML(summary.label)}</span><strong>${summary.ready?money(summary.amount):escapeHTML(summary.pendingText)}</strong></div>${summary.ready?`<dl class="payment-breakdown">${rows}</dl>`:`<p>Total tagihan pada dokumen: <strong>${money(summary.invoiceTotal)}</strong></p>`}${note}</section>`;
}
function renderPaymentOverview(){
  const root=$('#payment-overview');root.hidden=!state.detail?.draft;
  if(root.hidden){root.replaceChildren();return;}
  root.innerHTML=paymentSummaryHTML(state.detail,state.dirty,true);
  $('#signature-summary').innerHTML=signatureHTML(state.detail);
}
function updateRobotClearance(){
  if(!document.body.classList.contains('reviewing'))return;
  const bar=$('.action-bar').getBoundingClientRect();
  document.documentElement.style.setProperty('--review-action-clearance',(bar.height?Math.max(0,Math.ceil(innerHeight-bar.top)):0)+'px');
}
$('.action-buttons').appendChild($('#robot-dock'));
new ResizeObserver(updateRobotClearance).observe($('.action-bar'));
window.addEventListener('resize',updateRobotClearance);

// A vendor the PIC registered while submitting is labelled wherever Finance and the director check the payee.
const vendorIsNew=detail=>(detail.draft?.validation?.checks||[]).some(check=>check.code==='VENDOR_NEW');
// Finance signed with checks still open: the director sees which ones and Finance's review note, from the audit.
function signedOverHTML(detail){
  if(!detail.signature?.reviewer)return '';
  const event=(detail.audit||[]).filter(e=>e.action==='REVIEW_APPROVED').sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)))[0];
  const open=[...new Set((event?.changes?.open_checks||[]).map(check=>check.code))];
  return open.length?`<div class="check-box signed-over"><strong>Disetujui Finance dengan ${open.length} kendala terbuka</strong><ul>${open.map(code=>`<li>${escapeHTML(checkTitle({code,message:code}))}</li>`).join('')}</ul><p>Catatan review: ${escapeHTML(event.reason||'-')}</p></div>`:'';
}
function signatureHTML(detail){
  const sign=detail.signature||{},draft=detail.draft,invoice=draft?.invoice||{},payment=invoice.payment||{};
  const step=(title,signed,waiting)=>signed?`<li class="sign-step done"><span>${title}</span><strong>${escapeHTML(signed.signer_name)}</strong><small>${escapeHTML(signed.signer_title)} · ${dateTime(signed.signed_at)}</small></li>`:`<li class="sign-step"><span>${title}</span><strong>${escapeHTML(waiting)}</strong></li>`;
  const changes=Object.entries(detail.original_values||{}).map(([path,before])=>`<li>${escapeHTML(fieldLabel(path))}: ${escapeHTML(displayField(path,before))} → ${escapeHTML(displayField(path,valueAt(invoice,path)))}</li>`).join('');
  // The PIC's submission comes before both signatures: who answered for the data, when, and why open checks stayed.
  const submission=detail.submission,intake=submission?`<li class="sign-step done"><span>Diajukan PIC</span><strong>${escapeHTML(submission.by)}</strong><small>${dateTime(submission.at)} · Versi ${submission.version}</small>${submission.note?`<small>Catatan PIC: ${escapeHTML(submission.note)}</small>`:''}</li>`:'<li class="sign-step"><span>Diajukan PIC</span><strong>Belum diajukan</strong></li>';
  // The holder is read from the document, where it often already starts with "a.n."; print the prefix once.
  const holder=String(payment.account_holder||'-').replace(/^\s*a\.?\s*n\.?\s+/i,'');
  return paymentSummaryHTML(detail,state.dirty)+`<p class="payment-destination"><span class="destination-label">Rekening tujuan</span>${escapeHTML(payment.bank_name||'-')} ${escapeHTML(payment.account_number||'')} a.n. ${escapeHTML(holder)}${vendorIsNew(detail)?' <span class="vendor-new">Vendor baru, didaftarkan PIC</span>':''}</p>`
    +`<ol class="sign-steps" aria-label="Jejak persetujuan">${intake}${step('Diperiksa Finance',sign.reviewer,'Belum disetujui')}${step('Disetujui Manajer Keuangan',sign.director,detail.status==='AMIGA_REVIEWED'?'Menunggu persetujuan':'Belum disetujui')}</ol>`
    +signedOverHTML(detail)
    +(sign.returned?`<div class="check-box"><strong>Dikembalikan manajer keuangan</strong><p>${escapeHTML(sign.returned.reason)}</p><small>${escapeHTML(sign.returned.signer_name)} · ${dateTime(sign.returned.signed_at)}</small></div>`:'')
    +(changes?`<details class="old-vouchers" open><summary>Koreksi PIC dan Finance terhadap hasil baca AI</summary><ul>${changes}</ul></details>`:'')
    +(sign.verify_url?`<p class="verify-link"><a href="${escapeHTML(sign.verify_url)}" target="_blank" rel="noopener">Halaman verifikasi ↗</a></p>`:'');
}
function renderDecision(detail){
  const voucher=detail.voucher,approval=detail.approval,sign=detail.signature||{},director=isDirector();
  $('#signature-summary').innerHTML=detail.draft?signatureHTML(detail):'';
  $('#decision-info').textContent=director?(detail.status==='AMIGA_APPROVED'?'Sudah disetujui. Voucher final ada di bawah, siap dicetak untuk tanda tangan basah.'
      :detail.status==='RETURNED'?'Sudah dikembalikan ke Finance dengan alasan Anda.':sign.director_block_reason||'Periksa voucher dan invoice asli, lalu setujui bila sesuai.')
    :detail.status==='AMIGA_APPROVED'?'Disetujui Manajer Keuangan AMIGA. Voucher final memakai data yang sama dengan persetujuan Finance.'
    :detail.status==='AMIGA_REVIEWED'?'Sudah disetujui Finance. Draf voucher menunggu persetujuan Manajer Keuangan AMIGA.'
    :approval.can_approve?'Cocokkan data dengan dokumen, lalu setujui dari tombol di bawah.':approval.reason;
  if(!director&&approval.can_approve&&approval.source_checks.length)$('#decision-info').textContent+=` Ada ${approval.source_checks.length} pemeriksaan sumber yang perlu Anda konfirmasi sendiri.`;
  const open=new Set(approval.blocking_checks.map(check=>check.code)).size;
  if(!director&&approval.can_approve&&open)$('#decision-info').textContent+=` Masih ada ${open} kendala. Anda tetap bisa menyetujui dengan catatan review.`;
  const draftLabels={PENDING:'Menyiapkan draf voucher…',RENDERING:'Membuat draf voucher…',FAILED:'Draf belum berhasil dibuat. Persetujuan Finance tetap tersimpan.',READY:'Draf resmi, disetujui Finance'};
  const finalLabels={PENDING:'Menyiapkan voucher final…',RENDERING:'Membuat voucher final…',FAILED:'Voucher final belum berhasil dibuat. Persetujuan tetap tersimpan.',READY:'Disetujui Finance dan manajer keuangan'};
  const card=(title,status,url,label)=>`<div class="voucher-card"><span class="file-icon">▤</span><div><strong>${escapeHTML(title)}</strong><small>${escapeHTML(status)}</small></div>${url?`<a class="primary" href="${escapeHTML(url)}">${label}</a>`:''}</div>`;
  const signed=sign.signed_voucher;
  $('#voucher-current').innerHTML=voucher?card(voucher.number+' · draf',draftLabels[voucher.render_status],voucher.download_url,'Unduh draf ↓')+(signed?card(voucher.number+' · final',finalLabels[signed.render_status],signed.download_url,'Unduh voucher final ↓'):''):'';
  $('#retry-form').hidden=!(voucher?.can_retry||signed?.can_retry);
  const old=detail.voucher_history.filter(v=>!v.active);
  $('#voucher-history').innerHTML=old.length?`<details class="old-vouchers"><summary>${old.length} voucher versi lama · tidak aktif</summary>${old.map(v=>`<p>${escapeHTML(v.number)} · versi ${v.invoice_version}<br><small>Digantikan oleh koreksi atau pengembalian. Dokumen arsip tetap disimpan.</small></p>`).join('')}</details>`:'';
  $('#doc-tabs').hidden=!voucher?.download_url;$('#doc-voucher-tab').textContent=signed?.download_url?'Voucher final':'Draf voucher';
  $('#return-open').hidden=!director;$('#return-open').disabled=detail.status!=='AMIGA_REVIEWED';
  // The PIC submits instead of approving; Finance and the Manajer Keuangan keep their approval button (shown by updateApproval).
  const pic=state.user?.role==='PIC';$('#submit-open').hidden=!pic;$('#save').textContent=detail.can_submit?'Simpan draf':'Simpan koreksi';
  if(director)$('#edit-state').textContent=detail.status==='AMIGA_APPROVED'?'Selesai disetujui':sign.director_block_reason||'Siap disetujui';
  // A voucher already on screen switches to the newest copy, for example the final one right after signing.
  if(!$('#voucher-frame').hidden)showDoc('voucher');
  updateApproval();
}
function updateApproval(){
  const detail=state.detail;if(!detail)return;
  // Only what can be done now: unsaved edits show Simpan alone, a clean draft shows the decisions without a dead Simpan.
  const director=isDirector(),pic=state.user?.role==='PIC';
  $('#save').hidden=director||!state.dirty;
  $('#pic-return-open').hidden=!detail.can_return_to_pic||state.dirty;
  $('#sign-open').hidden=pic||(!director&&state.dirty&&!!detail.can_edit);
  if(!director&&['AMIGA_REVIEWED','AMIGA_APPROVED'].includes(detail.status))$('#sign-open').hidden=true;
  $('#sign-open').disabled=isDirector()?!detail.signature?.can_director_act:(!detail.approval?.can_approve||state.dirty);
  $('#sign-open').title=isDirector()?(detail.signature?.director_block_reason||''):state.dirty?'Simpan koreksi sebelum menyetujui versi terbaru.':(detail.approval?.can_approve?'':detail.approval?.reason||'');
  // Submitting stays clickable: it saves unsaved edits first, and points at red fields instead of staying silent.
  const missing=missingNow();
  $('#submit-open').disabled=!detail.can_submit;
  $('#submit-open').title=!detail.can_submit?'Invoice ini sudah diajukan ke Finance.':missing.length?'Lengkapi isian wajib: '+missing.map(fieldLabel).join(', '):'';
  renderPaymentOverview();updateRobotClearance();const guide=renderGuide();if(!state.dirty&&guide){const count=new Set((detail.approval?.blocking_checks||[]).map(check=>check.code)).size;
    // During intake open checks may stay, with a note; only the required fields hold the submission.
    $('#edit-state').textContent=detail.can_submit?(missing.length?`Lengkapi ${missing.length} isian wajib sebelum mengajukan`:count?count+' kendala terbuka · bisa diajukan dengan catatan':''):count&&detail.approval?.can_approve?count+' kendala untuk dicek · keputusan di tangan Anda':count&&state.user?.role==='FINANCE_REVIEWER'&&!['AMIGA_REVIEWED','AMIGA_APPROVED'].includes(detail.status)&&detail.approval?.reason?detail.approval.reason:'';}
}
function showDoc(kind){
  const url=state.detail?.signature?.signed_voucher?.download_url||state.detail?.voucher?.download_url;const voucher=kind==='voucher'&&!!url;
  $$('[data-doc]').forEach(b=>b.classList.toggle('active',b.dataset.doc===(voucher?'voucher':'invoice')));
  $('#pdf-preview').hidden=voucher;$('#voucher-frame').hidden=!voucher;$('#page-indicator').hidden=voucher;$('#doc-zoom').hidden=voucher;$('#evidence-banner').hidden=true;
  if(voucher&&$('#voucher-frame').dataset.src!==url){$('#voucher-frame').dataset.src=url;$('#voucher-frame').src=url+'&inline=1';}
  $('#doc-title').textContent=voucher?$('#doc-voucher-tab').textContent:'Invoice asli';
}
// 16 Okt 2026, Aldian: the original must be easy to read next to the fields. Zoom scales the page images inside the
// scrolling preview; Lebarkan gives the document panel most of the width while the fields stay beside it.
const DOC_ZOOMS=[100,125,150,200,300];
function setDocZoom(level){
  state.docZoom=level;$('#pdf-preview').style.setProperty('--doc-zoom',level+'%');$('#doc-zoom-level').textContent=level+'%';
  $('#doc-zoom-out').disabled=level===DOC_ZOOMS[0];$('#doc-zoom-in').disabled=level===DOC_ZOOMS[DOC_ZOOMS.length-1];
}
$('#doc-zoom-in').addEventListener('click',()=>setDocZoom(DOC_ZOOMS[Math.min(DOC_ZOOMS.length-1,DOC_ZOOMS.indexOf(state.docZoom)+1)]));
$('#doc-zoom-out').addEventListener('click',()=>setDocZoom(DOC_ZOOMS[Math.max(0,DOC_ZOOMS.indexOf(state.docZoom)-1)]));
$('#doc-expand').addEventListener('click',()=>{
  const wide=!$('.review-grid').classList.contains('doc-wide');$('.review-grid').classList.toggle('doc-wide',wide);
  $('#doc-expand').setAttribute('aria-pressed',String(wide));$('#doc-expand').textContent=wide?'Kembalikan':'Lebarkan';
});
setDocZoom(100);
$$('[data-doc]').forEach(button=>button.addEventListener('click',()=>showDoc(button.dataset.doc)));
// Focus on a field: the preview jumps to the cited page and shows the quote the value came from.
function showEvidence(path){
  const evidence=state.detail?.draft?.source_evidence?.[path];if(!evidence){$('#evidence-banner').hidden=true;return;}
  showDoc('invoice');const page=$('#pdf-preview').children[evidence.page-1];
  if(page)$('#pdf-preview').scrollTo({top:page.offsetTop-12,behavior:'smooth'});
  $('#evidence-banner').textContent=`${fieldLabel(path)} · Hal. ${evidence.page}: “${evidence.raw_value}”`;$('#evidence-banner').hidden=false;
}
function updatePageIndicator(){
  // A single page needs no counter; the header stays on one line.
  const preview=$('#pdf-preview'),pages=[...preview.children];if(pages.length<2){$('#page-indicator').textContent='';return;}
  const index=pages.findIndex(page=>page.offsetTop+page.offsetHeight/2>preview.scrollTop);
  $('#page-indicator').textContent=`Hal. ${Math.max(0,index)+1} dari ${pages.length}`;
}
$('#pdf-preview').addEventListener('scroll',updatePageIndicator);
// Fit-to-page needs the preview's real height; a CSS percentage does not resolve inside the scroll box.
new ResizeObserver(([entry])=>$('#pdf-preview').style.setProperty('--page-height',Math.max(240,Math.floor(entry.contentRect.height))+'px')).observe($('#pdf-preview'));
function openSign(){
  const detail=state.detail,director=isDirector(),invoice=detail.draft?.invoice||{};
  $('#sign-form').reset();$('#sign-error').textContent='';
  $('#sign-title').textContent=director?'Setujui voucher':'Setujui review';
  $('#sign-summary').innerHTML=[['Vendor',invoice.vendor_name+(vendorIsNew(detail)?' · vendor baru, didaftarkan PIC':'')],['Nomor invoice',invoice.invoice_number],['Nominal ke vendor',money(window.amigaPaymentSummary(detail,state.dirty).amount)],['Rekening tujuan',`${invoice.payment?.bank_name||'-'} ${invoice.payment?.account_number||''}`],...(Object.keys(detail.original_values||{}).length?[['Data dikoreksi manual',Object.keys(detail.original_values).length+' isian']]:[])].map(([key,value])=>`<dt>${escapeHTML(key)}</dt><dd>${escapeHTML(value??'-')}</dd>`).join('');
  const adjusted=detail.draft?.tax?.ppn_origin==='INTERNAL_ADJUSTMENT';$('#sign-tax-adjustment-label').hidden=director||!adjusted;
  if(adjusted)$('#sign-summary').innerHTML+=`<dt>Total invoice sumber</dt><dd>${money(invoice.stated_total)}</dd><dt>Tambahan PPN internal</dt><dd>${money(detail.draft.tax.ppn_adjustment_amount)}</dd>`;
  $('#sign-reason-label').hidden=director;$('#sign-consent-text').textContent=detail.signature?.consent_text||'';
  // Finance may sign with checks still open; it sees them here and its review note says why.
  const open=director?[]:[...new Map((detail.approval?.blocking_checks||[]).map(check=>[check.code,check])).values()];
  $('#sign-open-checks').hidden=!open.length;
  $('#sign-open-checks').innerHTML=open.length?`<strong>Masih ada ${open.length} kendala</strong><ul>${open.map(check=>`<li>${escapeHTML(checkTitle(check))}</li>`).join('')}</ul><p>Tulis di catatan review kenapa tetap disetujui. Kendala ini tercatat di riwayat dan terlihat Manajer Keuangan.</p>`:'';
  $('#approval-reason').placeholder=open.length?'Contoh: total sudah dicocokkan dengan dokumen, selisihnya biaya tools.':'Tuliskan hasil pemeriksaan dokumen.';
  updateSignSubmit();$('#sign-dialog').showModal();$('#sign-consent').focus();
}
function updateSignSubmit(){$('#sign-submit').disabled=!$('#sign-consent').checked||!$('#sign-password').value||(!isDirector()&&($('#approval-reason').value.trim().length<5||(!$('#sign-tax-adjustment-label').hidden&&!$('#sign-tax-adjustment').checked)));}
['#sign-consent','#sign-password','#approval-reason','#sign-tax-adjustment'].forEach(selector=>{$(selector).addEventListener('input',updateSignSubmit);$(selector).addEventListener('change',updateSignSubmit);});
$('#sign-open').addEventListener('click',openSign);
$('#close-sign').addEventListener('click',()=>$('#sign-dialog').close());$('#cancel-sign').addEventListener('click',()=>$('#sign-dialog').close());
$('#sign-form').addEventListener('submit',async event=>{
  event.preventDefault();const director=isDirector();$('#sign-submit').disabled=true;$('#sign-error').textContent='';
  const json=director?{expected_version:state.detail.approved_version,password:$('#sign-password').value,consent:true}
    :{expected_version:state.detail.current_version,source_reviewed:true,consent:true,tax_adjustment_confirmed:$('#sign-tax-adjustment').checked,password:$('#sign-password').value,reason:$('#approval-reason').value.trim()};
  try{await api('/requests/'+state.current+(director?'/director-approval':'/review'),{method:'POST',json});$('#sign-dialog').close();await loadDetail(state.current);toast(director?'Voucher disetujui. Voucher final sedang dibuat.':'Review disetujui. Draf voucher disiapkan untuk manajer keuangan.');}
  catch(error){$('#sign-error').textContent=error.message;$('#sign-password').value='';updateSignSubmit();
    // A conflict means the request moved on in another session: show its new state instead of a stale screen.
    if(error.status===409){$('#sign-dialog').close();toast(error.message);await loadDetail(state.current);}}
});
$('#return-open').addEventListener('click',()=>{$('#return-form').reset();$('#return-error').textContent='';$('#return-dialog').showModal();});
$('#close-return').addEventListener('click',()=>$('#return-dialog').close());$('#cancel-return').addEventListener('click',()=>$('#return-dialog').close());
$('#return-form').addEventListener('submit',async event=>{
  event.preventDefault();$('#return-submit').disabled=true;$('#return-error').textContent='';
  try{await api('/requests/'+state.current+'/director-return',{method:'POST',json:{expected_version:state.detail.approved_version,reason:$('#return-reason').value.trim()}});$('#return-dialog').close();await loadDetail(state.current);toast('Dikembalikan ke Finance dengan alasan Anda.');}
  catch(error){$('#return-error').textContent=error.message;if(error.status===409){$('#return-dialog').close();toast(error.message);await loadDetail(state.current);}}finally{$('#return-submit').disabled=false;}
});
// Finance's second decision next to signing: back to the PIC with a reason, which the PIC reads first.
function openPicReturn(){if(!state.detail?.can_return_to_pic||state.dirty)return;$('#pic-return-form').reset();delete $('#pic-return-form').dataset.tried;$('#pic-return-error').textContent='';updatePicReturn();$('#pic-return-dialog').showModal();$('#pic-return-reason').focus();}
function updatePicReturn(){
  const text=$('#pic-return-form').dataset.tried==='1'&&$('#pic-return-reason').value.trim().length<5?'Tulis alasan minimal 5 karakter, supaya PIC tahu apa yang harus diperbaiki.':'';
  $('#pic-return-reason-error').hidden=!text;$('#pic-return-reason-error').textContent=text;$('#pic-return-label').classList.toggle('invalid',!!text);
}
$('#pic-return-open').addEventListener('click',openPicReturn);$('#pic-return-reason').addEventListener('input',updatePicReturn);
['#close-pic-return','#cancel-pic-return'].forEach(selector=>$(selector).addEventListener('click',()=>$('#pic-return-dialog').close()));
$('#pic-return-form').addEventListener('submit',async event=>{
  event.preventDefault();$('#pic-return-form').dataset.tried='1';updatePicReturn();
  const reason=$('#pic-return-reason').value.trim();if(reason.length<5){$('#pic-return-reason').focus();return;}
  $('#pic-return-submit').disabled=true;$('#pic-return-error').textContent='';
  try{await api('/requests/'+state.current+'/finance-return',{method:'POST',json:{expected_version:state.detail.current_version,reason}});$('#pic-return-dialog').close();await loadDetail(state.current);toast('Dikembalikan ke PIC dengan alasan Anda.');}
  catch(error){$('#pic-return-error').textContent=error.message;if(error.status===409){$('#pic-return-dialog').close();toast(error.message);await loadDetail(state.current);}}finally{$('#pic-return-submit').disabled=false;}
});
$('#retry-form').addEventListener('submit',async event=>{
  event.preventDefault();$('#retry-voucher').disabled=true;$('#decision-error').textContent='';
  try{await api('/requests/'+state.current+'/voucher/retry',{method:'POST',json:{expected_version:state.detail.approved_version,reason:$('#retry-reason').value.trim()}});$('#retry-form').reset();await loadDetail(state.current);toast('PDF dibuat ulang dari data yang sama.');}
  catch(error){$('#decision-error').textContent=error.message;}finally{$('#retry-voucher').disabled=false;}
});
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});
// Wait until all deferred feature scripts are registered before restoring a session.
window.addEventListener('DOMContentLoaded',()=>{if(new URLSearchParams(location.search).get('switch')==='1'){showLogin();return;}enter().catch(error=>{showLogin();if(error.status!==401)$('#login-error').textContent='Server belum siap. Coba masuk beberapa saat lagi.';});});
