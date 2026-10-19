"""Hubungi klien: a PIC hands the final voucher to the client's Telegram through n8n.

Only a PIC sends, and only vouchers the Manajer Keuangan approved (Aldian, 16 Okt 2026). The PIC picks a recipient the
team registered for that client and confirms. A send never changes the invoice status: it is recorded in
voucher_deliveries and in the invoice trail, as SENT only with Telegram's message id as proof.
"""

import base64
import hashlib
from html import escape
import logging
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from psycopg import errors
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from . import handover_n8n
from .chat_search import WIB, money
from .service import AppError
from .settings import ROOT
from .voucher_pdf import tanggal
from amiga_ocr.openai_live import read_dotenv  # importable once .settings has put prototype/ on the path

CHAT_ID = re.compile(r'-?[0-9]{5,20}')  # a person's id, or a group's with a leading minus
CAPTION_LIMIT = 1024  # Telegram's limit for a document caption
# Written for the person who opens it on a phone (Aldian, 16 Okt 2026). Only the template carries HTML tags.
# web/app/hubungi-klien/page.tsx previews the same lines; keep the two in step.
CAPTION_LINES = ('Halo, tim {client}.', '',
                 'Voucher final untuk invoice {invoice} dari {vendor} sudah disetujui. File PDF-nya terlampir.', '',
                 '<b>Nomor voucher</b>', '{number}', '',
                 '<b>Nilai bayar</b>', '{amount}', '',
                 '<b>Disetujui</b>', 'Manajer Keuangan AMIGA, {approved}', '',
                 'Mohon diperiksa, lalu lanjutkan pembayaran ke vendor sesuai proses di tim Anda.', '',
                 'Salam,', '{sender}', '{title}')
# Every client starts with the chat Aldian prepared in Telegram for the demo (16 Okt 2026), named like this.
DEFAULT_RECIPIENT = 'Aldian (demo)'
# A send that never came back (a restart, a lost connection) stops blocking the next one after this long.
STALE_MINUTES = 2
# Final vouchers the user's clients hold, with the Manajer Keuangan's approval; the payload's approved_at is Finance's.
VOUCHERS = ('SELECT r.id AS request_id,r.client_id,r.approved_version,c.name AS client_name,c.code AS client_code,'
            'v.id AS voucher_id,v.number,v.payload,st.signed_at AS approved_at '
            'FROM requests r JOIN assignments a ON a.client_id=r.client_id AND a.user_id=%s '
            'JOIN clients c ON c.id=r.client_id '
            'JOIN vouchers v ON v.request_id=r.id AND v.invoice_version=r.approved_version AND v.superseded_at IS NULL '
            "JOIN voucher_signoffs s ON s.voucher_id=v.id AND s.render_status='READY' "
            "JOIN approval_steps st ON st.id=s.director_step_id WHERE r.status='AMIGA_APPROVED'")
log = logging.getLogger(__name__)


class NewContact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_id: str = Field(min_length=1, max_length=100)
    name: str = Field(max_length=200)
    telegram_chat_id: str = Field(max_length=40)


class Send(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    contact_id: UUID


def make_sender():
    """The n8n client, or None until .env names the webhook. Tests replace this function."""
    try:
        config = handover_n8n.HandoverConfig.load()
    except ValueError as error:
        log.warning('Hubungi klien off: %s', error)
        return None
    return handover_n8n.N8nSender(config) if config else None


def default_chat_id(path=ROOT / '.env'):
    """AMIGA_TELEGRAM_DEFAULT_CHAT_ID from .env, or None when it is unset or not a Telegram id. Tests replace this."""
    try:
        values = read_dotenv(path) if path.is_file() else {}
    except ValueError as error:
        log.warning('Default recipient off: %s', error)
        return None
    chat_id = values.get('AMIGA_TELEGRAM_DEFAULT_CHAT_ID', '').strip()
    return chat_id if CHAT_ID.fullmatch(chat_id) else None


def pic_only(user):
    if user['role'] != 'PIC':
        raise AppError('FORBIDDEN', 'Hubungi klien hanya untuk PIC.', 403)


def masked(chat_id):
    """Finance and the Manajer read the invoice trail too, so it keeps only the last digits."""
    return '••••' + chat_id[-4:]


def approved_text(moment):
    local = moment.astimezone(WIB)
    return f'{tanggal(local)}, {local:%H.%M} WIB'


def caption(fields):
    """Lines for Telegram's HTML mode. Every value is escaped, and the longest one shortened until it fits."""
    values = {key: ' '.join(str(value).split()) for key, value in fields.items()}
    while True:
        safe = {key: escape(value, quote=False) for key, value in values.items()}
        text = '\n'.join(line.format(**safe) for line in CAPTION_LINES)
        if len(text) <= CAPTION_LIMIT:
            return text
        longest = max(values, key=lambda key: len(values[key]))
        values[longest] = values[longest][:len(values[longest]) * 3 // 4].rstrip() + '…'


def details(row):
    invoice, tax = row['payload'].get('invoice') or {}, row['payload'].get('tax') or {}
    return {'number': row['number'], 'invoice': invoice.get('invoice_number') or '-',
            'vendor': invoice.get('vendor_name') or '-',
            'amount': money(tax.get('net_payable'), invoice.get('currency')) or '-',
            'approved': approved_text(row['approved_at'])}


def contact_view(row):
    return {'id': str(row['id']), 'client_id': row['client_id'], 'name': row['name'],
            'chat_id_masked': masked(row['telegram_chat_id'])}


def voucher_view(row, last):
    info = details(row)
    return {'request_id': str(row['request_id']), 'client_id': row['client_id'], 'client_name': row['client_name'],
            'number': info['number'], 'invoice': info['invoice'], 'vendor': info['vendor'],
            'net_payable_text': info['amount'], 'approved_at': row['approved_at'].astimezone(WIB).isoformat(),
            'approved_at_text': info['approved'], 'file_name': info['number'] + '-final.pdf',
            'last_delivery': last and {'status': last['status'], 'contact_name': last['contact_name'],
                                       'at': (last['finished_at'] or last['created_at']).astimezone(WIB).isoformat(),
                                       'message_id': last['provider_message_id']}}


def overview(db, user, connected, default_chat=None):
    with db.transaction() as conn:
        if default_chat:
            # Once per client: a client that ever had this chat, even turned off by its PIC, is left as it is.
            added = conn.execute(
                'INSERT INTO client_contacts(id,client_id,name,telegram_chat_id,created_by) '
                'SELECT gen_random_uuid(),a.client_id,%s,%s,%s FROM assignments a WHERE a.user_id=%s AND NOT EXISTS '
                '(SELECT 1 FROM client_contacts k WHERE k.client_id=a.client_id AND k.telegram_chat_id=%s) '
                'ON CONFLICT (client_id,telegram_chat_id) WHERE active DO NOTHING RETURNING id,client_id',
                (DEFAULT_RECIPIENT, default_chat, user['id'], user['id'], default_chat)).fetchall()
            for row in added:
                conn.execute('INSERT INTO client_events(client_id,actor_id,action,changes) VALUES (%s,%s,%s,%s)',
                             (row['client_id'], user['id'], 'CONTACT_ADDED',
                              Jsonb({'contact_id': str(row['id']), 'name': DEFAULT_RECIPIENT,
                                     'chat_id': masked(default_chat), 'default': True})))
        rows = conn.execute(VOUCHERS + ' ORDER BY st.signed_at DESC LIMIT 100', (user['id'],)).fetchall()
        ids = [row['request_id'] for row in rows]
        last = {row['request_id']: row for row in conn.execute(
            'SELECT DISTINCT ON (d.request_id) d.request_id,d.status,d.provider_message_id,d.created_at,d.finished_at,'
            'k.name AS contact_name FROM voucher_deliveries d JOIN client_contacts k ON k.id=d.contact_id '
            'WHERE d.request_id=ANY(%s) ORDER BY d.request_id,d.created_at DESC', (ids,))} if ids else {}
        contacts = conn.execute('SELECT k.id,k.client_id,k.name,k.telegram_chat_id FROM client_contacts k '
                                'JOIN assignments a ON a.client_id=k.client_id AND a.user_id=%s WHERE k.active '
                                'ORDER BY k.client_id,k.name', (user['id'],)).fetchall()
    return {'connected': connected, 'vouchers': [voucher_view(row, last.get(row['request_id'])) for row in rows],
            'contacts': [contact_view(row) for row in contacts]}


def add_contact(db, user, body):
    name, chat_id = ' '.join(body.name.split()), body.telegram_chat_id.strip()
    if not 2 <= len(name) <= 80:
        raise AppError('INVALID_PAYLOAD', 'Tulis nama penerima, 2 sampai 80 karakter.', field='name')
    if not CHAT_ID.fullmatch(chat_id):
        raise AppError('INVALID_PAYLOAD', 'ID Telegram berisi 5 sampai 20 angka. ID grup diawali tanda minus.',
                       field='telegram_chat_id')
    with db.transaction() as conn:
        if not conn.execute('SELECT 1 FROM assignments WHERE user_id=%s AND client_id=%s',
                            (user['id'], body.client_id)).fetchone():
            raise AppError('NOT_FOUND', 'Klien tidak ditemukan.', 404)
        row = conn.execute('INSERT INTO client_contacts(id,client_id,name,telegram_chat_id,created_by) '
                           'VALUES (%s,%s,%s,%s,%s) ON CONFLICT (client_id,telegram_chat_id) WHERE active DO NOTHING '
                           'RETURNING id,client_id,name,telegram_chat_id',
                           (uuid4(), body.client_id, name, chat_id, user['id'])).fetchone()
        if row:
            conn.execute('INSERT INTO client_events(client_id,actor_id,action,changes) VALUES (%s,%s,%s,%s)',
                         (body.client_id, user['id'], 'CONTACT_ADDED',
                          Jsonb({'contact_id': str(row['id']), 'name': name, 'chat_id': masked(chat_id)})))
        else:  # the same chat is already registered for this client
            row = conn.execute('SELECT id,client_id,name,telegram_chat_id FROM client_contacts '
                               'WHERE client_id=%s AND telegram_chat_id=%s AND active', (body.client_id, chat_id)).fetchone()
    return {'contact': contact_view(row)}


def disable_contact(db, user, contact_id):
    with db.transaction() as conn:
        row = conn.execute('UPDATE client_contacts k SET active=false FROM assignments a WHERE k.id=%s AND k.active '
                           'AND a.client_id=k.client_id AND a.user_id=%s RETURNING k.id,k.client_id,k.telegram_chat_id',
                           (contact_id, user['id'])).fetchone()
        if not row:
            raise AppError('NOT_FOUND', 'Penerima tidak ditemukan.', 404)
        conn.execute('INSERT INTO client_events(client_id,actor_id,action,changes) VALUES (%s,%s,%s,%s)',
                     (row['client_id'], user['id'], 'CONTACT_DISABLED',
                      Jsonb({'contact_id': str(row['id']), 'chat_id': masked(row['telegram_chat_id'])})))
    return {'ok': True}


def finish(db, user, row, contact, delivery_id, status, message_id=None, code=None, detail=None):
    with db.transaction() as conn:
        conn.execute('UPDATE voucher_deliveries SET status=%s,provider_message_id=%s,error_code=%s,detail=%s,'
                     'finished_at=now() WHERE id=%s', (status, message_id, code, detail, delivery_id))
        changes = {'contact_id': str(contact['id']), 'contact': contact['name'],
                   'chat_id': masked(contact['telegram_chat_id']), 'status': status}
        if message_id:
            changes['telegram_message_id'] = message_id
        reason = {'SENT': 'Voucher final dikirim ke klien lewat Telegram.',
                  'UNCERTAIN': 'Status kiriman voucher ke klien belum pasti.'}.get(
                      status, 'Pengiriman voucher ke klien belum berhasil.')
        db.audit(conn, row['request_id'], user['id'], 'VOUCHER_SENT' if status == 'SENT' else 'VOUCHER_SEND_FAILED',
                 reason, changes, row['approved_version'])


def send(db, review, user, body, sender):
    if sender is None:
        raise AppError('HANDOVER_NOT_CONFIGURED', 'Pengiriman Telegram belum aktif. Hubungi admin AMIGA.', 409)
    data, filename = review.download_signed(body.request_id, user, None)  # final, ready and unchanged, or refused
    delivery_id = uuid4()
    with db.transaction() as conn:
        row = db.locked_request(conn, body.request_id, user) and conn.execute(
            VOUCHERS + ' AND r.id=%s', (user['id'], body.request_id)).fetchone()
        if not row:
            raise AppError('NOT_FOUND', 'Voucher tidak tersedia.', 404)
        contact = conn.execute('SELECT id,name,telegram_chat_id FROM client_contacts WHERE id=%s AND client_id=%s '
                               'AND active', (body.contact_id, row['client_id'])).fetchone()
        if not contact:
            raise AppError('NOT_FOUND', 'Penerima tidak ditemukan.', 404)
        conn.execute("UPDATE voucher_deliveries SET status='UNCERTAIN',error_code=%s,detail=%s,finished_at=now() "
                     "WHERE request_id=%s AND status='SENDING' AND created_at < now() - %s * interval '1 minute'",
                     ('HANDOVER_UNCERTAIN', 'no answer', body.request_id, STALE_MINUTES))
        busy = AppError('HANDOVER_BUSY', 'Voucher ini sedang dikirim. Tunggu sebentar, lalu muat ulang halaman.', 409)
        if conn.execute("SELECT 1 FROM voucher_deliveries WHERE request_id=%s AND status='SENDING'",
                        (body.request_id,)).fetchone():
            raise busy
        try:
            conn.execute('INSERT INTO voucher_deliveries(id,request_id,voucher_id,invoice_version,contact_id,pdf_sha256,'
                         "status,sent_by) VALUES (%s,%s,%s,%s,%s,%s,'SENDING',%s)",
                         (delivery_id, body.request_id, row['voucher_id'], row['approved_version'], contact['id'],
                          hashlib.sha256(data).hexdigest(), user['id']))
        except errors.UniqueViolation:
            raise busy from None
        sender_row = conn.execute('SELECT name,title FROM users WHERE id=%s', (user['id'],)).fetchone()
    info, title = details(row), sender_row['title'] or 'Admin Intake AMIGA'
    text = caption({'number': info['number'], 'client': row['client_name'], 'invoice': info['invoice'],
                    'vendor': info['vendor'], 'amount': info['amount'], 'approved': info['approved'],
                    'sender': sender_row['name'], 'title': title})
    payload = {'event': 'amiga.voucher_final', 'delivery_id': str(delivery_id), 'chat_id': contact['telegram_chat_id'],
               'recipient': contact['name'], 'client': {'code': row['client_code'], 'name': row['client_name']},
               'voucher': {'number': info['number'], 'invoice': info['invoice'], 'vendor': info['vendor'],
                           'net_payable_text': info['amount'], 'approved_at': row['approved_at'].astimezone(WIB).isoformat(),
                           'approved_at_text': info['approved']},
               'sender': {'name': sender_row['name'], 'title': title}, 'caption': text,
               'file': {'name': filename, 'mime': 'application/pdf', 'base64': base64.b64encode(data).decode('ascii')}}
    try:
        message_id = sender.send(payload)
    except handover_n8n.DeliveryFailed as failure:
        if failure.uncertain:
            finish(db, user, row, contact, delivery_id, 'UNCERTAIN', code='HANDOVER_UNCERTAIN', detail=failure.detail)
            raise AppError('HANDOVER_UNCERTAIN', 'Status kiriman belum pasti. Cek Telegram penerima sebelum mengirim '
                           'ulang.', 424) from None
        finish(db, user, row, contact, delivery_id, 'FAILED', code='HANDOVER_FAILED', detail=failure.detail)
        raise AppError('HANDOVER_FAILED', 'Telegram belum menerima voucher. Coba lagi, atau hubungi admin AMIGA.',
                       424) from None
    finish(db, user, row, contact, delivery_id, 'SENT', message_id=message_id)
    return {'status': 'SENT', 'message_id': message_id, 'contact_name': contact['name']}


def handover_router(actor, db, review):
    router = APIRouter(prefix='/api/v1/handover')

    @router.get('')
    def listing(user=Depends(actor)):
        pic_only(user)
        sender = make_sender()
        if sender:
            sender.close()
        return overview(db, user, sender is not None, default_chat_id())

    @router.post('/contacts')
    def contacts(body: NewContact, user=Depends(actor)):
        pic_only(user)
        return add_contact(db, user, body)

    @router.post('/contacts/{contact_id}/disable')
    def disable(contact_id: UUID, user=Depends(actor)):
        pic_only(user)
        return disable_contact(db, user, contact_id)

    @router.post('/send')
    def deliver(body: Send, user=Depends(actor)):
        pic_only(user)
        sender = make_sender()
        try:
            return send(db, review, user, body, sender)
        finally:
            if sender:
                sender.close()

    return router
