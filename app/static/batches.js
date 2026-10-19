'use strict';
const batchState={files:[],key:null,active:null,result:null,busy:false,timer:null};
// Stage 6: invoices may be photos too. The server checks the bytes again; this only labels the choice.
const UPLOAD_TYPES={'.pdf':'application/pdf','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png'};
function uploadType(file){const name=file.name.toLowerCase();return UPLOAD_TYPES[name.slice(name.lastIndexOf('.'))]||'';}

function resetBatchWorkspace(){
  clearTimeout(batchState.timer);batchState.files=[];batchState.key=null;batchState.active=null;batchState.result=null;
  $('#batch-list').replaceChildren();$('#batch-items').replaceChildren();$('#selected-files').replaceChildren();
  $('#upload-dialog').close();$('#batch-dialog').close();
}

async function loadBatches(){
  const client=state.client,actor=state.user?.id;if(!actor)return;
  // The batch history is kept per client; with every client shown it waits for one.
  if(!client){$('#batch-list').innerHTML='<p class="muted">Pilih satu klien di kanan atas untuk melihat riwayat batch.</p>';return;}
  try{
    const data=await api('/intake-batches?client_id='+encodeURIComponent(client));
    if(client!==state.client||actor!==state.user?.id)return;
    $('#batch-list').innerHTML=data.items.length?data.items.map(b=>`<button class="batch-row" data-batch="${escapeHTML(b.id)}"><span class="file-icon">▤</span><span><strong>${b.total} file · ${b.mode==='REPLAY'?'Contoh sintetis':'Unggahan'}</strong><small>${escapeHTML(b.uploader)} · ${date(b.created_at)} · ${escapeHTML(b.id.slice(0,8))}</small></span><span class="batch-counts">${b.accepted} diterima · ${b.rejected} ditolak${b.pending?' · '+b.pending+' belum terkirim':''} <b>↗</b></span></button>`).join(''):'<p class="muted">Belum ada batch. Pilih beberapa invoice atau coba batch campuran.</p>';
    $$('[data-batch]').forEach(button=>button.addEventListener('click',()=>openBatch(button.dataset.batch)));
  }catch(error){if(actor===state.user?.id)$('#batch-list').textContent=error.message;}
}

function setBatchFiles(files){
  if(batchState.busy)return;
  batchState.files=[...files];if(!batchState.active)batchState.key=crypto.randomUUID();
  $('#file-label').textContent=files.length?`${files.length} file dipilih`:'Klik untuk memilih atau tarik beberapa file ke sini';
  $('#selected-files').innerHTML=batchState.files.map(file=>`<li><span>${escapeHTML(file.name)}</span><small>${(file.size/1000000).toFixed(2)} MB${file.size>5000000?' · melebihi 5 MB':''}${!uploadType(file)?' · bukan PDF, JPG, atau PNG':''}</small></li>`).join('');
  $('#upload-error').textContent=files.length>5?'Maksimal lima file per batch. Pilih ulang file.':'';
}

function openUpload(resume=null){
  batchState.active=resume;batchState.key=null;batchState.files=[];
  $('#upload-form').reset();setBatchFiles([]);$('#upload-error').textContent='';$('#upload-progress').textContent='';
  // The uploader names the client on purpose; only a single-client account or a resumed batch is filled in.
  const clients=state.user?.clients||[];
  $('#upload-client').replaceChildren(optionOf('','Pilih klien…'),...clients.map(c=>optionOf(c.id,c.name)));
  $('#upload-client').value=resume?resume.client_id:clients.length===1?clients[0].id:'';$('#upload-client').disabled=Boolean(resume);
  // A PIC may open a new client right here, for example the eleventh of the team (clients.js).
  $('#client-new').hidden=state.user?.role!=='PIC'||Boolean(resume);
  if(typeof resetTaxForm==='function')resetTaxForm(Boolean(resume));
  $('#resume-note').hidden=!resume;
  $('#resume-note').textContent=resume?'Pilih ulang file yang belum terkirim dengan nama dan isi yang sama. File yang sudah diterima tidak diproses ulang.':'';
  $('#upload-submit').textContent=resume?'Lanjutkan unggahan':'Unggah & proses';$('#upload-dialog').showModal();
}
$('#open-upload').addEventListener('click',()=>openUpload());
$('#close-upload').addEventListener('click',()=>{if(!batchState.busy)$('#upload-dialog').close();});
$('#upload-dialog').addEventListener('cancel',event=>{if(batchState.busy)event.preventDefault();});
$('#pdf-file').addEventListener('change',()=>setBatchFiles($('#pdf-file').files));
$('#dropzone').addEventListener('dragover',event=>event.preventDefault());
$('#dropzone').addEventListener('drop',event=>{
  event.preventDefault();if(batchState.busy)return;
  if(event.dataTransfer.files.length){$('#pdf-file').files=event.dataTransfer.files;setBatchFiles(event.dataTransfer.files);}
});

async function fileManifest(file){
  // Files known to be rejected are never read into memory just to calculate a hash.
  let sha256='0'.repeat(64);
  if(file.size<=5000000&&uploadType(file)){
    const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
    sha256=[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');
  }
  return {filename:file.name,byte_size:file.size,sha256};
}

$('#upload-form').addEventListener('submit',async event=>{
  event.preventDefault();if(batchState.busy)return;
  if(!batchState.files.length||batchState.files.length>5){$('#upload-error').textContent='Pilih satu hingga lima file.';return;}
  if(!$('#upload-client').value){$('#upload-error').textContent='Pilih klien dulu.';$('#upload-client').focus();return;}
  // A resumed batch keeps the tax choice stored with its first manifest.
  const selection=batchState.active?null:readTaxForm(),problem=batchState.active?'':taxError(selection);
  if(problem){$('#upload-error').textContent=problem;return;}
  const actor=state.user?.id,client=$('#upload-client').value,files=[...batchState.files];
  batchState.busy=true;$('#upload-submit').disabled=true;$('#pdf-file').disabled=true;$('#close-upload').disabled=true;
  $('#upload-error').textContent='';$('#upload-progress').textContent='Memeriksa pilihan file…';
  try{
    const manifests=[];
    for(const file of files)manifests.push(await fileManifest(file));
    if(!batchState.active){
      batchState.active=await api('/intake-batches',{method:'POST',headers:{'Idempotency-Key':batchState.key},json:{client_id:client,items:manifests.map(manifest=>({...manifest,tax_selection:selection}))}});
    }
    let batch=batchState.active,matched=0;
    for(const item of batch.items.filter(item=>item.status==='PENDING')){
      const index=manifests.findIndex(file=>file.filename===item.filename&&file.byte_size===item.byte_size&&file.sha256===item.sha256);
      if(index<0)continue;
      matched++;
      $('#upload-progress').textContent=`Mengirim file ${item.position} dari ${batch.items.length}: ${item.filename}`;
      try{
        batch=await api(`/intake-batches/${batch.id}/items/${item.position}`,{method:'POST',headers:{'Content-Type':uploadType(files[index])||'application/octet-stream'},body:files[index]});
        batchState.active=batch;
      }catch(error){
        if(error.status===401||error.status===403||error.status===404)throw error;
        // A lost response is ambiguous. Continue the other files and inspect durable results next.
        $('#upload-progress').textContent='Satu pengiriman belum terkonfirmasi; melanjutkan file lainnya.';
      }
    }
    batch=await api('/intake-batches/'+batch.id);batchState.active=batch;
    if(actor!==state.user?.id)return;
    // The queue follows the client the files went to, unless it already shows every client.
    if(state.client&&client!==state.client){state.client=client;$('#client-select').value=client;}
    if(batch.counts.pending&&!matched)throw new Error('Pilihan file belum cocok. Gunakan nama dan isi file awal untuk melanjutkan.');
    $('#upload-dialog').close();await showQueue(false);await openBatch(batch.id);updateBudget();
    toast(batch.counts.pending?'Sebagian file belum terkirim. Hasil yang sudah diterima tetap tersimpan.':`${batch.counts.accepted} file diterima, ${batch.counts.rejected} ditolak. Lihat hasil per file.`);
  }catch(error){if(actor===state.user?.id)$('#upload-error').textContent=error.message;}
  finally{
    batchState.busy=false;$('#upload-submit').disabled=false;$('#pdf-file').disabled=false;$('#close-upload').disabled=false;
    $('#upload-submit').textContent=batchState.active?'Lanjutkan unggahan':'Unggah & proses';$('#upload-progress').textContent='';
  }
});

async function openBatch(identifier){
  clearTimeout(batchState.timer);batchState.result=identifier;$('#batch-error').textContent='';$('#batch-items').replaceChildren();
  $('#batch-title').textContent='Hasil batch';$('#resume-batch').hidden=true;
  $('#batch-summary').textContent='Memuat hasil batch…';if(!$('#batch-dialog').open)$('#batch-dialog').showModal();
  await refreshBatch();
}
async function refreshBatch(){
  clearTimeout(batchState.timer);const identifier=batchState.result,actor=state.user?.id;
  if(!identifier||!actor||!$('#batch-dialog').open)return;
  try{
    const batch=await api('/intake-batches/'+identifier);
    if(batchState.result!==identifier||actor!==state.user?.id)return;
    $('#batch-title').textContent='Batch '+String(batch.id).slice(0,8);
    $('#batch-summary').textContent=`${batch.items.length} file · ${batch.counts.accepted} diterima · ${batch.counts.rejected} ditolak · ${batch.counts.pending} belum terkirim`;
    $('#batch-items').innerHTML=batch.items.map(item=>`<article class="batch-file"><div class="batch-file-heading"><strong>${item.position}. ${escapeHTML(item.filename)}<small class="tax-label">${escapeHTML(taxLabel(item.tax_selection))}</small></strong><span class="status ${item.status==='REJECTED'?'exception':item.status==='PENDING'?'processing':'ready'}">${{ACCEPTED:'Diterima',REJECTED:'Ditolak',PENDING:'Belum terkirim'}[item.status]}</span></div>${item.status==='ACCEPTED'?`<p>${item.request_created?'Invoice diterima dan sedang dibaca AI.':'File yang sama sudah pernah diunggah. Hasil sebelumnya dibuka.'}</p><div class="batch-file-footer">${statusHTML(item.request_status)}<button class="review-link" data-batch-request="${escapeHTML(item.request_id)}">Buka invoice ↗</button></div>${item.processing_error?'<p class="form-error">AI belum selesai membaca file ini. Buka invoice untuk melihat penyebabnya.</p>':''}`:`<p>${escapeHTML(item.error_message||'File belum diterima server. Pengunggah dapat memilih ulang file yang sama.')}</p>`}</article>`).join('');
    $$('[data-batch-request]').forEach(button=>button.addEventListener('click',()=>{$('#batch-dialog').close();openReview(button.dataset.batchRequest);}));
    $('#resume-batch').hidden=!batch.can_upload||!batch.counts.pending;
    $('#resume-batch').onclick=()=>{$('#batch-dialog').close();openUpload(batch);};
    if(batch.items.some(item=>['QUEUED','PROCESSING'].includes(item.request_status)))batchState.timer=setTimeout(refreshBatch,1500);
  }catch(error){if(actor===state.user?.id)$('#batch-error').textContent=error.message;}
}
$('#close-batch').addEventListener('click',()=>$('#batch-dialog').close());
$('#batch-dialog').addEventListener('close',()=>{clearTimeout(batchState.timer);loadBatches();});
$('#demo-batch').addEventListener('click',async()=>{
  const button=$('#demo-batch'),client=state.client,actor=state.user?.id;
  button.disabled=true;
  try{
    const batch=await api('/demo-batches/mixed?client_id='+encodeURIComponent(client),{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()}});
    if(client!==state.client||actor!==state.user?.id)return;
    await loadQueue();await loadBatches();await openBatch(batch.id);toast('Batch sintetis dibuat tanpa panggilan API baru.');
  }catch(error){toast(error.message);}finally{button.disabled=false;}
});
