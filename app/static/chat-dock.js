// Robot Admin chat on every screen: the Next.js dashboard loads this file through next/script, the review page through
// a script tag. One file, no framework, and no inline style or script, because FastAPI pages send script-src 'self'.
// Everything stays inside this function: app.js declares top-level $, state and api, so any top-level name here clashes.
(function(){
  'use strict';
  const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const CITE=/\[([A-Z]+-[A-Z0-9_-]+)\]/g;
  const EXAMPLES={
    PIC:['Invoice jasa desain apa saja?','Invoice mana yang dikembalikan Finance ke saya?','Rekening vendor beda dengan data, saya harus apa?'],
    FINANCE_REVIEWER:['Invoice mana yang siap saya periksa?','Tampilkan invoice jasa desain dan totalnya','Kenapa invoice ini dikembalikan?'],
    AMIGA_DIRECTOR:['Invoice mana yang menunggu persetujuan akhir?','Invoice jasa desain yang sudah disetujui apa saja?','Berapa total invoice sewa kendaraan?'],
  };
  // Card chips take the dashboard's tones (web/lib/status.ts), plus the return to the PIC that chat_search shows apart.
  const TONES={QUEUED:'processing',PROCESSING:'processing',INTAKE:'processing',RETURNED_TO_PIC:'rejected',READY_FOR_REVIEW:'ready',
    EXCEPTION:'exception',AMIGA_REVIEWED:'ready',AMIGA_APPROVED:'done',RETURNED:'rejected'};

  // Pure helpers, also read by app/tests/test_chat_dock.js through window.amigaChatView.
  function requestFromHash(hash){const match=/(?:^#|&)request=([0-9a-f-]{36})(?:&|$)/.exec(hash||'');return match&&UUID.test(match[1])?match[1]:null;}
  function reviewHref(id){return typeof id==='string'&&UUID.test(id)?'/review#request='+id:null;}
  function segments(line){
    const parts=[];let last=0;const text=line.replace(/\*\*/g,'');
    for(const match of text.matchAll(CITE)){if(match.index>last)parts.push({text:text.slice(last,match.index)});parts.push({cite:match[1]});last=match.index+match[0].length;}
    if(last<text.length)parts.push({text:text.slice(last)});
    return parts;
  }
  // Model text to blocks: numbered lines become an ordered list, dashes a bullet list, the rest paragraphs.
  function parseAnswer(text){
    const blocks=[];
    for(const raw of String(text||'').split(/\r?\n/)){
      const line=raw.trim();if(!line)continue;
      const ordered=/^\d+[.)]\s+(.*)$/.exec(line),bullet=/^[-*•]\s+(.*)$/.exec(line);
      const kind=ordered?'ol':bullet?'ul':'p',body=ordered?ordered[1]:bullet?bullet[1]:line;
      const previous=blocks[blocks.length-1];
      if(kind!=='p'&&previous&&previous.kind===kind)previous.items.push(segments(body));
      else blocks.push({kind,items:[segments(body)]});
    }
    return blocks;
  }
  function examples(role){return EXAMPLES[role]||EXAMPLES.PIC;}
  function tone(status){return TONES[status]||'processing';}
  // The invoice's open checks in three groups from sop.js. Only kendala are counted as kendala, the same number as the
  // bar under the review form; the rest is named apart so the two never disagree (Aldian, 16 Okt 2026).
  const CHECK_GROUPS=[['kendala','Kendala untuk dicek'],['cocokkan','Cocokkan dengan dokumen'],['catatan','Catatan']];
  function checksSummary(groups){
    const n=groups.kendala.length,others=groups.cocokkan.length+groups.catatan.length,rest=[];
    if(groups.cocokkan.length)rest.push(groups.cocokkan.length+' hal untuk dicocokkan dengan dokumen');
    if(groups.catatan.length)rest.push(groups.catatan.length+' catatan');
    return {lead:n?`Invoice ini punya ${n} kendala.`:others?'Tidak ada kendala yang menahan keputusan.':'',
      more:rest.length?(n?'Ada juga ':'Ada ')+rest.join(' dan ')+'.':'',
      bar:n?`Lihat ${n} kendala`+(others?` dan ${others} hal lain`:' invoice ini'):others?`Lihat ${others} hal untuk dicek`:''};
  }
  // Cards carry ISO dates; people read "21 Sep 2026". Anything else is shown as it came.
  function shortDate(iso){
    const match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(iso||'');if(!match)return iso||null;
    return new Intl.DateTimeFormat('id-ID',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(Date.UTC(+match[1],match[2]-1,+match[3])));
  }
  window.amigaChatView={requestFromHash,reviewHref,segments,parseAnswer,examples,tone,tones:{...TONES},shortDate,checksSummary};
  if(typeof document==='undefined')return;

  const state={user:null,threadId:null,mode:'ai',busy:false,open:false,booted:false};
  const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=text;return node;};
  const storeKey=()=>state.user?'amigaChat:'+state.user.id:null;
  function remember(){const key=storeKey();if(!key)return;try{sessionStorage.setItem(key,JSON.stringify({open:state.open,threadId:state.threadId}));}catch(error){}}
  function recall(){const key=storeKey();if(!key)return{};try{return JSON.parse(sessionStorage.getItem(key)||'{}')||{};}catch(error){return{};}}

  async function call(path,options={}){
    const headers={'Accept':'application/json'};
    if(options.json){headers['Content-Type']='application/json';headers['X-CSRF-Token']=state.user?.csrf||'';}
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),options.timeout||15000);
    try{
      const response=await fetch('/api/v1'+path,{method:options.method||'GET',credentials:'same-origin',headers,signal:controller.signal,
        body:options.json?JSON.stringify(options.json):undefined});
      const data=await response.json().catch(()=>({}));
      if(response.status===401){signOut();}
      if(!response.ok){const error=new Error(data.message||'Robot Admin sedang tidak bisa dihubungi.');error.status=response.status;throw error;}
      return data;
    }catch(error){
      if(error.name==='AbortError')throw new Error('Robot Admin terlalu lama menjawab. Coba lagi sebentar lagi.');
      if(error instanceof TypeError)throw new Error('Koneksi ke server terputus. Periksa jaringan Anda.');
      throw error;
    }finally{clearTimeout(timer);}
  }

  // Static markup only, no value from the server. The clover is the amiga.id mark as index.html draws it, under its own id.
  const svg=(paths,cls='amiga-chat-icon',box='0 0 24 24')=>`<svg class="${cls}" viewBox="${box}" aria-hidden="true" focusable="false">${paths}</svg>`;
  const ICON={
    history:svg('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>'),
    plus:svg('<path d="M12 5v14M5 12h14"/>'),
    close:svg('<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>'),
    send:svg('<path d="M20.5 3.5L3.5 10.2l7 3.3 3.3 7z"/><path d="M10.5 13.5l10-10"/>'),
    search:svg('<circle cx="11" cy="11" r="6"/><path d="M15.5 15.5L20 20"/>'),
    arrow:svg('<path d="M5 12h14M13 6l6 6-6 6"/>'),
    back:svg('<path d="M19 12H5M11 6l-6 6 6 6"/>'),
    chat:svg('<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4A2.5 2.5 0 0 1 4 13.5z"/>'),
  };
  const PETAL='M0 0l-1.45-1.32C-6.6-5.99-10-9.07-10-12.85-10-15.93-7.58-18.35-4.5-18.35c1.74 0 3.41.81 4.5 2.09C1.09-17.54 2.76-18.35 4.5-18.35 7.58-18.35 10-15.93 10-12.85c0 3.78-3.4 6.86-8.55 11.54L0 0z';
  const CLOVER=svg('<path class="amiga-chat-ribbon" d="M3 62C12 52.5 24 49 35 52.5C44 55.5 52 57 58 50.5C61 47 62 42.5 59.5 38.5C59.5 43 57 46.5 52.5 48.5C46 51 40 49.5 34 48C23 45 11 50 3 62Z"/><g class="amiga-chat-petals">'+
    [-45,45,135,-135].map(turn=>`<use href="#amiga-chat-petal" transform="translate(32 27) rotate(${turn}) translate(0 -1.5)"/>`).join('')+'</g>','amiga-chat-clover','0 0 64 64');

  // Built once. Every value from the server goes in through textContent, except an SOP card body: sop.js escapes it.
  // This is Robot Admin's only window (Aldian, 16 Okt 2026): on the review page it also lists the invoice's open checks.
  const root=el('div','amiga-chat');root.hidden=true;
  root.innerHTML='<svg class="amiga-chat-defs" aria-hidden="true" focusable="false"><defs><path id="amiga-chat-petal" d="'+PETAL+'"/></defs></svg>'+
    '<button type="button" class="amiga-chat-launcher" aria-expanded="false" aria-controls="amiga-chat-panel">'+
    '<span class="amiga-chat-avatar">'+CLOVER+'</span><span class="amiga-chat-launcher-text">Tanya Robot Admin</span></button>'+
    '<section id="amiga-chat-panel" class="amiga-chat-panel" role="dialog" aria-modal="false" aria-label="Robot Admin" hidden>'+
    '<header class="amiga-chat-head"><span class="amiga-chat-avatar">'+CLOVER+'</span>'+
    '<div class="amiga-chat-heading"><h2 id="amiga-chat-title">Robot Admin</h2><p>Asisten invoice dan SOP AMIGA</p></div>'+
    '<div class="amiga-chat-tools">'+
    '<button type="button" data-act="list" aria-label="Riwayat percakapan" title="Riwayat percakapan">'+ICON.history+'</button>'+
    '<button type="button" data-act="new" aria-label="Percakapan baru" title="Percakapan baru">'+ICON.plus+'</button>'+
    '<button type="button" data-act="close" aria-label="Tutup Robot Admin" title="Tutup">'+ICON.close+'</button></div></header>'+
    '<button type="button" class="amiga-chat-kendala" data-act="checks" hidden></button>'+
    '<p class="amiga-chat-notice" hidden></p>'+
    '<div class="amiga-chat-list" hidden></div>'+
    '<div class="amiga-chat-log" aria-live="polite"></div>'+
    '<form class="amiga-chat-form"><label class="amiga-chat-sr" for="amiga-chat-input">Pertanyaan untuk Robot Admin</label>'+
    '<textarea id="amiga-chat-input" rows="1" maxlength="2000" placeholder="Tanya soal invoice atau SOP"></textarea>'+
    '<button type="submit" aria-label="Kirim" title="Kirim">'+ICON.send+'</button></form></section>';
  const $=selector=>root.querySelector(selector);
  const launcher=$('.amiga-chat-launcher'),panel=$('.amiga-chat-panel'),log=$('.amiga-chat-log'),list=$('.amiga-chat-list');
  const form=$('.amiga-chat-form'),input=$('#amiga-chat-input'),notice=$('.amiga-chat-notice'),kendala=$('.amiga-chat-kendala');

  function setOpen(open){
    state.open=open;panel.hidden=!open;launcher.setAttribute('aria-expanded',String(open));root.classList.toggle('is-open',open);remember();
    document.getElementById('robot-launcher')?.setAttribute('aria-expanded',String(open));
    if(open){showChat();if(!log.childElementCount)loadThread();input.focus({preventScroll:true});}
  }
  function showChat(){list.hidden=true;log.hidden=false;form.hidden=false;syncChecks();}
  function scrollDown(){log.scrollTop=log.scrollHeight;syncChecks();}

  // The open checks of the invoice on the review page, shared by sop.js; none elsewhere.
  const checks=()=>Array.isArray(window.amigaRobotChecks)?window.amigaRobotChecks:[];
  const groups=()=>{const shared=window.amigaRobotCheckGroups;return shared&&Array.isArray(shared.kendala)?shared:{kendala:checks(),cocokkan:[],catatan:[]};};
  const checkLabel=code=>typeof window.amigaLabel==='function'?window.amigaLabel(code):code;
  function checksList(){
    const box=el('div','amiga-chat-checks'),all=groups(),shown=CHECK_GROUPS.filter(([key])=>all[key].length);
    for(const [key,title] of shown){
      // A single group needs no heading; with more, each says what kind of check it holds.
      if(shown.length>1)box.append(el('p','amiga-chat-checks-group',title));
      for(const code of all[key]){
        const item=el('button','is-'+key,checkLabel(code));item.type='button';
        item.addEventListener('click',()=>showCard({kode:code},checkLabel(code)));box.append(item);
      }
    }
    return box;
  }
  // Mid-conversation the greeting is gone, so a bar under the header brings the checks back without clearing anything.
  function syncChecks(){
    kendala.hidden=!checks().length||!!log.querySelector('.amiga-chat-welcome')||log.hidden;
    kendala.textContent=checksSummary(groups()).bar;
  }
  function showChecks(){
    if(log.querySelector('.amiga-chat-welcome'))return;
    const box=el('div','amiga-chat-msg is-bot'),summary=checksSummary(groups());
    box.append(el('p',null,[summary.lead,summary.more].filter(Boolean).join(' ')),
      el('p',null,'Pilih satu untuk melihat langkahnya dari SOP.'),checksList());
    log.append(box);scrollDown();
  }
  // An SOP card opens straight from sop.js, without AI. "Tanya soal ini" is where AI comes in.
  async function showCard(query,title){
    if(typeof window.amigaSopCard!=='function')return;
    if(log.querySelector('.amiga-chat-welcome'))log.replaceChildren();
    showChat();
    if(title)log.append(questionNode(title));
    const box=el('div','amiga-chat-msg is-bot is-sop');box.append(el('p','amiga-chat-muted','Membuka kartu SOP…'));
    log.append(box);scrollDown();
    try{
      const card=await window.amigaSopCard(query);
      const body=el('div','amiga-chat-sop-body');body.innerHTML=card.html;
      box.replaceChildren(el('p','amiga-chat-sop-title',card.title),el('span','amiga-chat-sop-id','Panduan SOP'),body);
      const actions=el('div','amiga-chat-sop-actions');
      if(card.kode){
        const ask=el('button',null,'Tanya soal ini');ask.type='button';
        ask.addEventListener('click',()=>send(`Kendala "${card.title}" (kode ${card.kode}): apa yang harus saya lakukan sekarang?`));
        actions.append(ask);
      }
      if(checks().length>1){const more=el('button',null,'Kendala lain');more.type='button';more.addEventListener('click',showChecks);actions.append(more);}
      if(actions.childElementCount)box.append(actions);
    }catch(error){box.replaceChildren(el('p','amiga-chat-error',error.message));}
    // The card is read from its top, not from its last line.
    log.scrollTop+=box.getBoundingClientRect().top-log.getBoundingClientRect().top-8;
  }
  // On the review page the clover may be the only door left, because chat-dock.css hides this launcher there.
  function closeToDoor(){
    setOpen(false);
    const door=getComputedStyle(launcher).display==='none'?document.getElementById('robot-launcher'):launcher;
    door?.focus();
  }

  function welcome(){
    const box=el('div','amiga-chat-welcome'),count=checks().length,summary=checksSummary(groups());
    box.append(el('p','amiga-chat-hello','Halo'+(state.user?', '+state.user.name.split(' ')[0]:'')+'.'));
    if(count){
      box.append(el('p','amiga-chat-lead',summary.lead));
      if(summary.more)box.append(el('p',null,summary.more));
      box.append(el('p',null,'Pilih satu untuk melihat langkahnya dari SOP.'),checksList(),el('p','amiga-chat-or','Atau tanya hal lain:'));
    }
    else box.append(el('p','amiga-chat-lead','Mau dibantu apa hari ini?'),
      el('p',null,'Saya bisa carikan invoice lama, cek sudah sampai mana, atau jelaskan langkahnya dari SOP.'));
    const chips=el('div','amiga-chat-examples');
    for(const text of examples(state.user?.role)){
      const chip=el('button');chip.type='button';chip.innerHTML=ICON.search;chip.append(text);
      chip.addEventListener('click',()=>send(text));chips.append(chip);
    }
    box.append(chips);log.replaceChildren(box);syncChecks();
  }

  function cardFor(card){
    const href=reviewHref(card.id);const link=el(href?'a':'div','amiga-chat-card');
    if(href){link.href=href;link.addEventListener('click',event=>{
      remember();
      // app.js reads #request only on load, so on the review page a new invoice needs a reload, not a hash change.
      if(location.pathname==='/review'){event.preventDefault();location.hash='request='+card.id;location.reload();}
    });}
    const top=el('div','amiga-chat-card-top');top.append(el('strong',null,card.nomor||'Tanpa nomor'));
    if(card.status_label)top.append(el('span','amiga-chat-badge is-'+tone(card.status),card.status_label));
    link.append(top,el('span','amiga-chat-card-vendor',card.vendor||'Vendor belum terbaca'));
    const meta=[card.klien,shortDate(card.tanggal)].filter(Boolean).join(' · ');if(meta)link.append(el('span','amiga-chat-card-meta',meta));
    const foot=el('div','amiga-chat-card-foot');
    if(card.total_teks)foot.append(el('span','amiga-chat-card-total',card.total_teks));
    if(href){const go=el('span','amiga-chat-card-go','Buka');go.insertAdjacentHTML('beforeend',ICON.arrow);foot.append(go);}
    if(foot.childElementCount)link.append(foot);
    return link;
  }

  function sopChip(ref){
    const canOpen=typeof window.amigaSopCard==='function';
    const chip=el(canOpen?'button':'span','amiga-chat-sop',ref.label||ref.sop_id);
    if(canOpen){chip.type='button';chip.addEventListener('click',()=>showCard({sop_id:ref.sop_id}));}
    return chip;
  }

  function answerNode(message){
    const labels=Object.fromEntries((message.sop||[]).map(ref=>[ref.sop_id,ref.label]));
    const box=el('div','amiga-chat-msg is-bot');
    for(const block of parseAnswer(message.isi)){
      const holder=block.kind==='p'?null:el(block.kind);
      for(const parts of block.items){
        const line=el(block.kind==='p'?'p':'li');
        for(const part of parts)line.append(part.cite?el('span','amiga-chat-cite',labels[part.cite]||part.cite):document.createTextNode(part.text));
        (holder||box).append(line);
      }
      if(holder)box.append(holder);
    }
    for(const warning of message.peringatan||[])box.append(el('p','amiga-chat-warn',warning));
    if((message.invoice||[]).length){const cards=el('div','amiga-chat-cards');for(const card of message.invoice)cards.append(cardFor(card));box.append(cards);}
    if((message.sop||[]).length){const refs=el('div','amiga-chat-refs');refs.append(el('span',null,'Sumber SOP:'));for(const ref of message.sop)refs.append(sopChip(ref));box.append(refs);}
    return box;
  }
  function questionNode(text){return el('div','amiga-chat-msg is-me',text);}
  function render(messages){
    log.replaceChildren();
    for(const message of messages)log.append(message.peran==='user'?questionNode(message.isi):answerNode(message));
    if(!messages.length)welcome();
    scrollDown();
  }

  async function loadThread(){
    if(!state.threadId){welcome();return;}
    try{const data=await call('/chat/threads/'+state.threadId);render(data.pesan);}
    catch(error){state.threadId=null;remember();welcome();}
  }
  async function showList(){
    log.hidden=true;form.hidden=true;list.hidden=false;
    const back=el('button','amiga-chat-back');back.type='button';back.innerHTML=ICON.back;back.append('Kembali');back.addEventListener('click',showChat);
    const head=el('div','amiga-chat-list-head');head.append(back,el('h3',null,'Riwayat percakapan'));
    const items=el('div');items.append(el('p','amiga-chat-muted','Memuat riwayat…'));
    list.replaceChildren(head,items);
    try{
      const data=await call('/chat/threads');setMode(data.mode);items.replaceChildren();
      if(!data.threads.length){items.append(el('p','amiga-chat-muted','Belum ada percakapan. Mulai dengan bertanya.'));}
      const when=new Intl.DateTimeFormat('id-ID',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
      for(const thread of data.threads){
        const item=el('button','amiga-chat-thread');item.type='button';item.innerHTML=ICON.chat;
        const text=el('span','amiga-chat-thread-text');text.append(el('strong',null,thread.judul),el('span',null,when.format(new Date(thread.diubah))));
        item.append(text);
        item.addEventListener('click',()=>{state.threadId=thread.id;remember();showChat();loadThread();});
        items.append(item);
      }
    }catch(error){items.replaceChildren(el('p','amiga-chat-error',error.message));}
  }
  function setMode(mode){
    state.mode=mode;notice.hidden=mode!=='cari';
    notice.textContent='Mode cari: AI sedang tidak dipakai, jadi Robot Admin menampilkan hasil pencarian langsung tanpa ringkasan.';
  }

  async function send(text){
    const question=String(text||'').trim();if(!question||state.busy)return;
    if(log.querySelector('.amiga-chat-welcome'))log.replaceChildren();
    state.busy=true;form.querySelector('button').disabled=true;showChat();
    log.append(questionNode(question));
    const typing=el('div','amiga-chat-msg is-bot is-typing');
    typing.innerHTML='<span class="amiga-chat-dots" aria-hidden="true"><span></span><span></span><span></span></span>';
    typing.append(el('span',null,'Robot Admin sedang mencari…'));log.append(typing);scrollDown();
    input.value='';
    try{
      const requestId=location.pathname==='/review'?requestFromHash(location.hash):null;
      const body={pesan:question};if(state.threadId)body.thread_id=state.threadId;if(requestId)body.request_id=requestId;
      const data=await call('/chat/messages',{method:'POST',json:body,timeout:60000});
      state.threadId=data.thread.id;remember();typing.replaceWith(answerNode(data.pesan));
      if(data.pesan.mode)setMode(data.pesan.mode);
    }catch(error){
      typing.replaceWith(el('div','amiga-chat-msg is-bot amiga-chat-error',error.status===409?'Robot Admin masih menjawab pesan Anda sebelumnya.':error.message));
      if(!input.value)input.value=question;
    }finally{state.busy=false;form.querySelector('button').disabled=false;scrollDown();input.focus({preventScroll:true});}
  }

  function signOut(){state.user=null;state.threadId=null;state.open=false;root.hidden=true;panel.hidden=true;log.replaceChildren();}
  async function boot(){
    try{state.user=await call('/session');}catch(error){signOut();return;}
    const saved=recall();state.threadId=saved.threadId||null;root.hidden=false;log.replaceChildren();
    if(saved.open)setOpen(true);
  }

  launcher.addEventListener('click',()=>setOpen(panel.hidden));
  root.addEventListener('click',event=>{
    const act=event.target.closest('[data-act]')?.dataset.act;
    if(act==='close')closeToDoor();
    if(act==='new'){state.threadId=null;remember();showChat();welcome();input.focus({preventScroll:true});}
    if(act==='list')showList();
    if(act==='checks')showChecks();
  });
  root.addEventListener('keydown',event=>{if(event.key==='Escape'&&!event.isComposing&&state.open){event.preventDefault();closeToDoor();}});
  form.addEventListener('submit',event=>{event.preventDefault();send(input.value);});
  input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();send(input.value);}});

  // The review page's doors: the clover toggles this window, and "Panduan SOP" on a check opens its card here.
  window.amigaChat={
    open(options={}){
      if(root.hidden)return false;
      setOpen(true);if(options.prefill){if(options.send)send(options.prefill);else input.value=options.prefill;}
      return true;
    },
    close(){if(state.open)setOpen(false);},
    toggle(){if(root.hidden)return false;setOpen(!state.open);return true;},
    showCard(query,title){if(!root.hidden)showCard(query,title);},
  };

  function mount(){
    if(!document.querySelector('link[href="/static/chat-dock.css"]')){const css=document.createElement('link');css.rel='stylesheet';css.href='/static/chat-dock.css';document.head.append(css);}
    document.body.append(root);
    // sop.js shares a new set of checks: a greeting on screen is redrawn with them, a conversation only updates its bar.
    document.addEventListener('amiga:checks',()=>{if(log.querySelector('.amiga-chat-welcome'))welcome();else syncChecks();});
    // The review page signs in and out without reloading, so follow its workspace instead of the page load.
    const workspace=document.getElementById('workspace');
    if(workspace){new MutationObserver(()=>{if(workspace.hidden)signOut();else boot();}).observe(workspace,{attributes:true,attributeFilter:['hidden']});if(!workspace.hidden)boot();}
    else boot();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
