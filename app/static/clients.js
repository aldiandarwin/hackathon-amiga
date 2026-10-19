'use strict';
// A PIC opens a new client from the upload dialog. The server gives it to the PIC's team and AMIGA's director, and
// checks the name, code and NPWP again; this only collects them.
$('#client-new').addEventListener('click',()=>{$('#client-form').reset();$('#client-error').textContent='';$('#client-dialog').showModal();$('#client-name').focus();});
['#close-client','#cancel-client'].forEach(selector=>$(selector).addEventListener('click',()=>$('#client-dialog').close()));
$('#client-form').addEventListener('submit',async event=>{
  event.preventDefault();$('#client-submit').disabled=true;$('#client-error').textContent='';
  const field=selector=>$(selector).value.trim()||null;
  try{
    const result=await api('/clients',{method:'POST',json:{name:field('#client-name'),city:field('#client-city'),sector:field('#client-sector'),npwp:field('#client-npwp'),code:field('#client-code')}});
    // The session lists the new client from now on; both client lists are rebuilt from it.
    state.user=await api('/session');fillClientSelect();
    $('#upload-client').replaceChildren(optionOf('','Pilih klien…'),...state.user.clients.map(c=>optionOf(c.id,c.name)));$('#upload-client').value=result.client.id;
    $('#client-dialog').close();toast(`Klien ${result.client.name} (kode ${result.client.code}) dibuat. Akses: ${result.members.join(', ')}.`);
  }catch(error){$('#client-error').textContent=error.message;}
  finally{$('#client-submit').disabled=false;}
});
