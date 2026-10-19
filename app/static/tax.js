'use strict';
// Tax choices come from the server table; the browser never computes an amount.

function presetOf(selection){return state.taxRules?.presets.find(p=>p.pph===selection?.pph&&p.ppn===Boolean(selection?.ppn));}
// Stage 6: the faktur number is read from the document. Only the review panel offers a manual override.
function taxControlsHTML(review=false){
  const options=(state.taxRules?.presets||[]).map(p=>`<option value="${escapeHTML(p.id)}">${escapeHTML(p.label)}</option>`).join('');
  return `<label>Pajak invoice<select class="tax-preset"><option value="">Pilih jenis pajak…</option>${options}</select></label>`+
    (review?'<label class="tax-faktur-field" hidden>Nomor faktur pajak, isi hanya kalau tidak terbaca dari dokumen<input class="tax-faktur" inputmode="numeric" maxlength="40" placeholder="Contoh: 010.000-26.00000005"></label><div class="tax-adjustment-field" hidden><label>PPN tidak tercantum di invoice<select class="tax-adjustment"><option value="NONE">Ikuti angka invoice; belum menambah PPN</option><option value="ADD_ON">Tambahkan PPN di atas total invoice</option></select></label><label class="tax-adjustment-note" hidden>Alasan tambahan PPN<textarea class="tax-adjustment-reason" minlength="5" maxlength="500" placeholder="Contoh: jasa dari vendor PKP; mohon konfirmasi invoice revisi dan faktur pajaknya."></textarea></label><p class="evidence">Pilih tambahan hanya bila total sumber belum termasuk PPN. Status PKP dan perlakuan pajak perlu diperiksa; invoice asli tetap utuh.</p></div>':'')+
    '<label class="tax-check"><input class="tax-npwp" type="checkbox" checked> Penerima punya NPWP/NIK</label>'+
    (review?'<details class="tax-rule-details"><summary>Penjelasan pilihan pajak</summary><p class="tax-hint" aria-live="polite"></p></details>':'<p class="tax-hint" aria-live="polite"></p>');
}
function taxParts(root){return {preset:root.querySelector('.tax-preset'),faktur:root.querySelector('.tax-faktur'),
  fakturField:root.querySelector('.tax-faktur-field'),npwp:root.querySelector('.tax-npwp'),hint:root.querySelector('.tax-hint'),
  adjustment:root.querySelector('.tax-adjustment'),adjustmentField:root.querySelector('.tax-adjustment-field'),
  adjustmentNote:root.querySelector('.tax-adjustment-note'),adjustmentReason:root.querySelector('.tax-adjustment-reason')};}
function syncTax(root){
  const parts=taxParts(root),choice=readTax(root),rules=state.taxRules,row=rules?.pph.find(item=>item.id===choice?.pph);
  if(parts.faktur){parts.fakturField.hidden=!choice?.ppn;if(!choice?.ppn)parts.faktur.value='';}
  if(parts.adjustmentField){parts.adjustmentField.hidden=!choice?.ppn||(root.dataset.missingPpn!=='true'&&parts.adjustment.value!=='ADD_ON');
    parts.adjustmentNote.hidden=parts.adjustment.value!=='ADD_ON';}
  if(!choice||!rules){parts.hint.textContent='';return;}
  const pph=!row||row.id==='TANPA'?'Tanpa potongan PPh.':`${row.rate_text} · ${row.basis}. Contoh: ${money(row.example.gross)} → potongan ${money(row.example.withheld)} → nominal ke vendor ${money(row.example.net)}.`;
  parts.hint.textContent=`${pph}${choice.ppn?' PPN sesuai faktur.':''} Aturan demo; perlu konfirmasi Finance. Cocokkan status NPWP/NIK penerima dengan dokumen.`;
}
function bindTaxControls(root,onChange){
  const parts=taxParts(root);
  [parts.preset,parts.npwp].forEach(input=>input.addEventListener('change',()=>{syncTax(root);onChange();}));
  parts.faktur?.addEventListener('input',onChange);syncTax(root);
  parts.adjustment?.addEventListener('change',()=>{syncTax(root);onChange();});
  parts.adjustmentReason?.addEventListener('input',onChange);
}
function readTax(root){
  const parts=taxParts(root);if(!parts.preset?.value)return null;
  // A draft saved with an id the dropdown no longer offers keeps that exact choice.
  const choice=parts.preset.value==='LEGACY'?JSON.parse(root.dataset.legacy):state.taxRules.presets.find(p=>p.id===parts.preset.value);
  const selection={pph:choice.pph,ppn:choice.ppn,recipient_has_npwp:parts.npwp.checked,faktur_number:choice.ppn?(parts.faktur?.value.trim()||null):null};
  if(choice.ppn&&parts.adjustment?.value==='ADD_ON')Object.assign(selection,{ppn_adjustment:'ADD_ON',ppn_adjustment_reason:parts.adjustmentReason.value.trim()});
  return selection;
}
function writeTax(root,selection,editable){
  const parts=taxParts(root),preset=presetOf(selection);
  parts.preset.querySelector('.tax-legacy')?.remove();delete root.dataset.legacy;
  if(selection&&!preset){
    root.dataset.legacy=JSON.stringify({pph:selection.pph,ppn:Boolean(selection.ppn)});
    const option=document.createElement('option');option.className='tax-legacy';option.value='LEGACY';
    option.textContent='Pilihan lama: '+taxLabel(selection);parts.preset.append(option);
  }
  parts.preset.value=preset?preset.id:(selection?'LEGACY':'');parts.npwp.checked=selection?selection.recipient_has_npwp:true;
  if(parts.adjustment){parts.adjustment.value=selection?.ppn_adjustment||'NONE';parts.adjustmentReason.value=selection?.ppn_adjustment_reason||'';}
  syncTax(root);if(parts.faktur)parts.faktur.value=selection?.faktur_number||'';
  Object.values(parts).forEach(element=>{if(element&&'disabled' in element)element.disabled=!editable;});
}
function taxError(selection){
  if(!selection)return 'Pilih jenis pajak invoice.';
  if(selection.ppn_adjustment==='ADD_ON'&&(selection.ppn_adjustment_reason||'').length<5)return 'Tuliskan alasan tambahan PPN minimal 5 karakter.';
  return '';
}
function taxLabel(selection){
  if(!selection)return 'Pajak belum dipilih';
  const preset=presetOf(selection),row=state.taxRules?.pph.find(item=>item.id===selection.pph);
  return (preset?.label||(row?.short||selection.pph)+(selection.ppn?' + PPN':''))+(selection.recipient_has_npwp?'':' · tanpa NPWP/NIK');
}

async function loadTaxRules(){
  try{state.taxRules=await api('/tax/rules');}
  catch(error){state.taxRules=null;toast('Aturan pajak belum termuat. Muat ulang halaman sebelum mengunggah.');}
  resetTaxForm(false);
}
function resetTaxForm(resume){
  const root=$('#tax-fields');root.innerHTML='<legend>Pilih perlakuan pajak sebelum unggah</legend>'+taxControlsHTML();root.disabled=Boolean(resume);
  bindTaxControls(root,()=>{$('#upload-error').textContent='';});
  if(resume)taxParts(root).hint.textContent='Pilihan pajak mengikuti batch awal.';
}
function readTaxForm(){return readTax($('#tax-fields'));}

function taxSummaryHTML(draft){
  // Drafts saved before the tax step have no tax block; they wait for a choice like NOT_SELECTED.
  const tax=draft.tax;
  if(!tax||tax.status==='NOT_SELECTED')return '<p class="tax-warning">Jenis potongan pajak belum dipilih. Finance memilih di sini sebelum persetujuan.</p>';
  const notices=draft.validation.checks.filter(c=>c.code.startsWith('TAX_')&&c.status!=='PASSED'&&!c.blocking&&c.code!=='TAX_SELECTION_REQUIRED').map(c=>c.message).concat(tax.warnings);
  const warnings=notices.map(text=>`<p class="tax-warning">${escapeHTML(text)}</p>`).join('');
  const faktur=tax.ppn_applied?`<p class="evidence">Nomor faktur pajak: ${tax.faktur_number?escapeHTML(tax.faktur_number)+(tax.faktur_source==='DOKUMEN'?' · dibaca dari dokumen':' · diisi manual'):'belum ada'}</p>`:'';
  if(tax.status!=='COMPUTED')return faktur+warnings+'<p class="tax-warning">Pajak belum dihitung. Cocokkan pilihan pajak, PPN tertulis, dan total tagihan.</p>';
  const adjustment=tax.ppn_origin==='INTERNAL_ADJUSTMENT'?`<div class="check-box tax-adjustment-summary"><strong>Tambahan PPN: ${money(tax.ppn_adjustment_amount)}</strong><p>Invoice sumber ${money(tax.invoice_total)} → tagihan setelah penyesuaian ${money(tax.gross_total)}. Invoice asli tidak diubah.</p><p>Alasan: ${escapeHTML(tax.adjustment_reason)}</p><details><summary>Catatan konfirmasi vendor</summary><p>${escapeHTML(tax.vendor_reminder)}</p></details></div>`:'';
  return adjustment+faktur+warnings+'<details class="tax-calculation"><summary>Rincian hitungan dan dasar hukum</summary><table class="tax-table"><tbody>'+tax.steps.map(step=>`<tr><th>${escapeHTML(step.label==='Jumlah dibayarkan'?'Nominal ke vendor':step.label==='Total invoice'?'Total tagihan sebelum PPh':step.label)}</th><td>${money(step.value)}</td></tr>`).join('')+'</tbody></table>'+
    '<ul class="tax-notes">'+tax.assumptions.map(text=>`<li>${escapeHTML(text)}</li>`).join('')+'</ul>'+taxSourcesHTML(tax)+'</details>';
}
function taxSourcesHTML(tax){
  const rules=state.taxRules,row=rules?.pph.find(item=>item.id===tax.pph_id);
  const sources=[row?.source,tax.ppn_applied?rules?.ppn.source:null,rules?.rounding_source].filter(Boolean);
  const links=sources.map(s=>`<a href="${escapeHTML(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(s.label)}</a>`).join(' · ');
  return `<p class="evidence">Dasar hukum: ${links||escapeHTML(tax.basis)} · Versi ${escapeHTML(tax.rules_version||'')}</p>`;
}
function renderTaxPanel(detail){
  const panel=$('#tax-panel'),draft=detail.draft;
  if(!draft){panel.hidden=true;panel.replaceChildren();return;}
  panel.hidden=false;
  panel.innerHTML='<div class="section-heading">Perhitungan pajak <span class="evidence">Aturan demo · konfirmasi Finance</span></div>'+
    `<div class="tax-controls">${taxControlsHTML(true)}</div><p class="tax-dirty" hidden>Pilihan berubah. Simpan koreksi untuk menghitung ulang.</p>`+taxSummaryHTML(draft);
  const root=panel.querySelector('.tax-controls');
  root.dataset.missingPpn=String(draft.invoice.stated_tax_total==null||Number(draft.invoice.stated_tax_total)===0);
  writeTax(root,draft.tax_selection,detail.can_edit);
  bindTaxControls(root,()=>{panel.querySelector('.tax-dirty').hidden=!taxDirty();markDirty();});
}
// "Pakai saran" for a PPN conflict: the same PPh with PPN, through the dropdown so the form marks itself changed.
function applyTaxHint(change){
  const root=$('#tax-panel .tax-controls'),now=root&&readTax(root),preset=now&&presetOf({...now,...change});
  if(!preset||root.querySelector('.tax-preset').disabled)return;
  const select=root.querySelector('.tax-preset');select.value=preset.id;select.dispatchEvent(new Event('change'));
}
function taxDirty(){
  const root=$('#tax-panel .tax-controls'),saved=state.detail?.draft?.tax_selection;
  if(!root||!state.detail?.can_edit)return false;
  const now=readTax(root);if(!now)return false;if(!saved)return true;
  // Field by field: jsonb does not keep key order, so a JSON string comparison would report false changes.
  return ['pph','ppn','recipient_has_npwp','faktur_number','ppn_adjustment','ppn_adjustment_reason'].some(key=>(now[key]??null)!==(saved[key]??null));
}
