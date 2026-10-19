'use strict';
// SOP labels and cards for Robot Admin on the review screen. Robot Admin is one window, the chat in chat-dock.js: it
// lists the open checks of the invoice on screen and opens their SOP cards without AI (Aldian, 16 Okt 2026).

const sopLabels={map:{},loaded:false,pending:null,failedAt:0};
// Card parts that explain rather than guide. They stay one click away under "Detail lain di kartu".
const SOP_DETAIL=new Set(['Pesan di layar','Istilah lain','Bedanya dengan','Status aturan']);

// Plain titles per check code from GET /sop/label, fetched once per session. A call before login gets 401 and leaves
// the next call free to try again. Raw fetch, because api() treats any 401 as a logout.
function loadSopLabels(){
  if(sopLabels.loaded||sopLabels.pending)return sopLabels.pending||Promise.resolve(sopLabels.map);
  if(Date.now()-sopLabels.failedAt<10000)return Promise.resolve(sopLabels.map);
  sopLabels.pending=fetch('/api/v1/sop/label',{credentials:'same-origin'})
    .then(response=>response.ok?response.json():Promise.reject(new Error('HTTP '+response.status)))
    .then(data=>{sopLabels.map=data.labels||{};sopLabels.loaded=true;return sopLabels.map;})
    .catch(()=>{sopLabels.failedAt=Date.now();return sopLabels.map;})
    .finally(()=>{sopLabels.pending=null;});
  return sopLabels.pending;
}
const SOP_FALLBACK_LABELS={TAX_NOT_COMPUTED:'Nominal pajak belum dapat dihitung',TAX_SELECTION_REQUIRED:'Jenis pajak belum dipilih',TAX_PPN_CONFLICT:'Pilihan pajak belum sesuai dengan nominal invoice',TAX_PPN_MISSING:'Nominal PPN belum ditemukan',TAX_PPN_DIFFERENT:'Nominal PPN perlu dicocokkan',TAX_FAKTUR_NOT_FOUND:'Nomor faktur pajak belum ditemukan'};
function sopHumanCode(code){if(SOP_FALLBACK_LABELS[code])return SOP_FALLBACK_LABELS[code];const text=String(code||'').toLowerCase().replace(/_/g,' ').trim();return text.charAt(0).toUpperCase()+text.slice(1);}
// For app.js: the card title for a check code, or a readable fallback while labels load or when a code has no card.
function amigaLabel(code){if(!sopLabels.loaded)loadSopLabels();return sopLabels.map[code]||sopHumanCode(code);}
window.amigaLabel=amigaLabel;
// Read after login: each read starts the fetch if needed and resolves to the label map. It never rejects.
Object.defineProperty(window,'amigaLabelsReady',{configurable:true,get:loadSopLabels});

function sopInline(text){return escapeHTML(text).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');}
function sopMarkdown(text){
  // Cards and answers are escaped first; only headings, bold labels and lists get formatting.
  let html='',list=null;
  const close=()=>{if(list){html+=`</${list}>`;list=null;}};
  text.split('\n').forEach(raw=>{
    const line=raw.trim();
    if(!line){close();return;}
    if(line.startsWith('# ')){close();html+=`<h4>${escapeHTML(line.slice(2))}</h4>`;return;}
    const ordered=/^\d+\.\s+(.*)$/.exec(line),bullet=/^-\s+(.*)$/.exec(line);
    if(ordered||bullet){
      const kind=ordered?'ol':'ul';
      if(list!==kind){close();html+=`<${kind}>`;list=kind;}
      html+=`<li>${sopInline((ordered||bullet)[1])}</li>`;return;
    }
    close();html+=`<p>${sopInline(line)}</p>`;
  });
  close();return html;
}

function sopCardBody(text){
  // A card is one heading, then parts that each open with a bold label such as **Ringkasnya.** or **Langkah penanganan**.
  const parts=[{label:'',lines:[]}];
  text.split('\n').forEach(raw=>{
    const line=raw.trim();
    if(line.startsWith('# '))return;
    const label=/^\*\*([^*]+?)\.?\*\*\s*(.*)$/.exec(line);
    if(label){parts.push({label:label[1].trim(),lines:label[2]?[label[2]]:[]});return;}
    if(/^Aturan:/.test(line)){parts.push({label:'Status aturan',lines:[line]});return;}
    parts[parts.length-1].lines.push(raw);
  });
  const html=part=>`<div class="sop-part">${part.label?`<h5>${escapeHTML(part.label)}</h5>`:''}${sopMarkdown(part.lines.join('\n'))}</div>`;
  const filled=parts.filter(part=>part.lines.join('').trim());
  const main=filled.filter(part=>!SOP_DETAIL.has(part.label)),more=filled.filter(part=>SOP_DETAIL.has(part.label));
  return main.map(html).join('')+(more.length?`<details class="sop-more"><summary>Detail lain di kartu</summary>${more.map(html).join('')}</details>`:'');
}

// The open checks go to the chat, which lists them in its greeting. The Manajer Keuangan only signs, so gets none.
function renderRobotChecks(detail){
  // Approval re-runs the checks, so a duplicate that arrived later blocks it without showing on the draft.
  const open=detail.draft.validation.checks.filter(c=>c.status!=='PASSED').concat(detail.approval?.blocking_checks||[]);
  const groups=document.body.classList.contains('role-director')?robotGroups({},[]):robotGroups(detail,open);
  robotDock(groups.kendala.length);shareChecks(groups);
  // The first review after login can render before the labels arrive; share again once they do, for the titles.
  if(!sopLabels.loaded)loadSopLabels().then(()=>shareChecks(groups));
}
// Kendala are counted as the bar under the form counts them, so the clover and the bar agree (Aldian, 16 Okt 2026).
// The other open checks stay one click away: the source checks Finance matches against the document, then notes.
function robotGroups(detail,open){
  const codes=list=>[...new Set((list||[]).map(c=>c.code))];
  const kendala=codes(detail.approval?.blocking_checks);
  const cocokkan=codes(detail.approval?window.amigaReviewChecks(detail).sources:[]).filter(code=>!kendala.includes(code));
  const catatan=codes(open).filter(code=>!kendala.includes(code)&&!cocokkan.includes(code));
  return {kendala,cocokkan,catatan};
}
// Polling renders the same checks every few seconds; the chat hears only a real change.
function shareChecks(groups){
  const key=JSON.stringify(groups)+'|'+sopLabels.loaded;if(shareChecks.key===key)return;shareChecks.key=key;
  window.amigaRobotCheckGroups=groups;window.amigaRobotChecks=[...groups.kendala,...groups.cocokkan,...groups.catatan];
  document.dispatchEvent(new CustomEvent('amiga:checks'));
}
// One SOP card for the chat: title, id, and the body formatted and escaped by sopCardBody.
window.amigaSopCard=async query=>{
  const card=await api('/sop/kartu?'+new URLSearchParams(query));
  return {title:card.label||(card.kode?amigaLabel(card.kode):card.judul),sop_id:card.sop_id,kode:card.kode||null,
    html:sopCardBody(card.teks_layar||card.teks)};
};
function robotDock(count){
  $('#robot-dock').hidden=false;const badge=$('#robot-badge');badge.hidden=!count;badge.textContent=count||'';
  $('#robot-launcher').setAttribute('aria-label',count?`Robot Admin, ${count} kendala`:'Robot Admin');
}
function resetRobot(){$('#robot-dock').hidden=true;shareChecks(robotGroups({},[]));}
// The clover opens and closes the chat; chat-dock.js keeps its aria-expanded in step.
$('#robot-launcher').addEventListener('click',()=>window.amigaChat?.toggle());
// "Panduan SOP" on each check opens that check's card in the chat. renderChecks rebuilds #checks, so listen once here.
$('#checks').addEventListener('click',event=>{
  const link=event.target.closest('[data-sop-kode]');if(!link)return;
  window.amigaChat?.open();window.amigaChat?.showCard({kode:link.dataset.sopKode},amigaLabel(link.dataset.sopKode));
});
