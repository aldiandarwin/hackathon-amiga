"""Robot Admin chat on every screen. A conversation belongs to one user; no other account can list or read it.

The browser sends a question, the thread it continues, and the invoice open on screen. The answer comes back with the
invoice cards and SOP references the server built from tool results, and both are stored with the message.
"""

from contextlib import contextmanager
import logging
import threading
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from . import chat_agent, chat_llm, chat_search
from .service import AppError

# Six exchanges: enough to say "yang pertama" about an earlier answer, small enough to stay cheap.
HISTORY_MESSAGES = 12
log = logging.getLogger(__name__)
_busy, _busy_lock = set(), threading.Lock()


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pesan: str = Field(min_length=1, max_length=2000)
    thread_id: UUID | None = None
    request_id: UUID | None = None


def make_llm(db):
    """The OpenAI client, or None for search-only answers. Tests replace this function."""
    try:
        config = chat_llm.ChatConfig.load()
    except ValueError as error:
        log.warning('Chat AI off: %s', error)
        return None
    return chat_llm.OpenAIChat(config, chat_llm.Ledger(db)) if config else None


@contextmanager
def one_turn(user_id):
    """One answer at a time per user, so a double click cannot spend twice or interleave a thread."""
    with _busy_lock:
        if user_id in _busy:
            raise AppError('CHAT_BUSY', 'Robot Admin masih menjawab pesan Anda sebelumnya.', 409)
        _busy.add(user_id)
    try:
        yield
    finally:
        with _busy_lock:
            _busy.discard(user_id)


def owned(conn, thread_id, user):
    thread = conn.execute('SELECT id,title FROM chat_threads WHERE id=%s AND user_id=%s', (thread_id, user['id'])).fetchone()
    if not thread:
        raise AppError('NOT_FOUND', 'Percakapan tidak ditemukan.', 404)
    return thread


def title_of(text):
    line = ' '.join(text.split())
    return line if len(line) <= 60 else line[:59].rstrip() + '…'


def fresh_cards(conn, user, rows):
    """A card is stored as the user saw it, so an invoice approved since would still read "Menunggu manajer keuangan"
    next to its final voucher. The ones the queue still shows this user are read again; the rest keep the stored card."""
    ids = list({card.get('id') for row in rows if row['role'] == 'assistant'
                for card in (row['refs'] or {}).get('invoice') or [] if card.get('id')})
    if not ids:
        return {}
    return {str(row['id']): {key: card.get(key) for key in chat_agent.CARD_KEYS}
            for row in chat_search.visible_rows(conn, user, ids) for card in [chat_search.invoice_card(row)]}


def cards_of(row, fresh):
    return [fresh.get(card.get('id'), card) for card in (row['refs'] or {}).get('invoice') or []]


def history_text(row, fresh=None):
    """An earlier answer as the model sees it again: its text plus the cards the user saw under it, so "yang pertama"
    can name an invoice without searching again. The cards are the allowlisted fields the server built."""
    text, cards = row['content'][:4000], cards_of(row, fresh or {})
    if row['role'] == 'assistant' and cards:
        text += '\n[Kartu invoice yang tampil: ' + '; '.join(
            f"{card.get('nomor')} · {card.get('vendor')} · {card.get('total_teks')} · {card.get('status_label')} · "
            f"id {card.get('id')}" for card in cards[:6]) + ']'
    return text


def message_view(row, fresh=None):
    refs = row['refs'] or {}
    return {'id': row['id'], 'peran': row['role'], 'isi': row['content'], 'mode': refs.get('mode'),
            'invoice': cards_of(row, fresh or {}), 'sop': refs.get('sop', []), 'peringatan': refs.get('peringatan', []),
            'dibuat': row['created_at'].isoformat()}


def chat_router(actor, db):
    router = APIRouter(prefix='/api/v1/chat')

    @router.get('/threads')
    def threads(user=Depends(actor)):
        llm = make_llm(db)
        ready = llm is not None and llm.ready()
        with db.transaction() as conn:
            rows = conn.execute('SELECT id,title,updated_at FROM chat_threads WHERE user_id=%s '
                                'ORDER BY updated_at DESC LIMIT 50', (user['id'],)).fetchall()
        return {'mode': 'ai' if ready else 'cari',
                'threads': [{'id': str(row['id']), 'judul': row['title'], 'diubah': row['updated_at'].isoformat()}
                            for row in rows]}

    @router.get('/threads/{thread_id}')
    def thread(thread_id: UUID, user=Depends(actor)):
        with db.transaction() as conn:
            found = owned(conn, thread_id, user)
            rows = conn.execute('SELECT id,role,content,refs,created_at FROM chat_messages WHERE thread_id=%s ORDER BY id',
                                (thread_id,)).fetchall()
            fresh = fresh_cards(conn, user, rows)
        return {'thread': {'id': str(found['id']), 'judul': found['title']},
                'pesan': [message_view(row, fresh) for row in rows]}

    @router.post('/messages')
    def send(body: ChatMessage, user=Depends(actor)):
        question = body.pesan.strip()
        if not question:
            raise AppError('INVALID_PAYLOAD', 'Tulis pertanyaan Anda dulu.', field='pesan')
        with one_turn(user['id']):
            with db.transaction() as conn:
                history, title = [], title_of(question)
                if body.thread_id:
                    title = owned(conn, body.thread_id, user)['title']
                    rows = conn.execute('SELECT role,content,refs FROM chat_messages WHERE thread_id=%s ORDER BY id DESC '
                                        'LIMIT %s', (body.thread_id, HISTORY_MESSAGES)).fetchall()
                    fresh = fresh_cards(conn, user, rows)
                    history = [{'role': row['role'], 'content': history_text(row, fresh)} for row in reversed(rows)]
                # The open invoice counts only when the queue would show it to this user.
                rows = chat_search.visible_rows(conn, user, [str(body.request_id)]) if body.request_id else []
                context = chat_search.invoice_card(rows[0]) if rows else None
            result = chat_agent.answer(db, make_llm(db), user, question, history, context)
            with db.transaction() as conn:
                thread_id = body.thread_id or uuid4()
                if body.thread_id:
                    conn.execute('UPDATE chat_threads SET updated_at=now() WHERE id=%s', (thread_id,))
                else:
                    conn.execute('INSERT INTO chat_threads(id,user_id,title) VALUES (%s,%s,%s)', (thread_id, user['id'], title))
                conn.execute("INSERT INTO chat_messages(thread_id,role,content,request_id) VALUES (%s,'user',%s,%s)",
                             (thread_id, question, context and context['id']))
                row = conn.execute("INSERT INTO chat_messages(thread_id,role,content,refs) VALUES (%s,'assistant',%s,%s) "
                                   'RETURNING id,role,content,refs,created_at',
                                   (thread_id, result['isi'], Jsonb({key: result[key] for key in
                                                                    ('mode', 'invoice', 'sop', 'peringatan')}))).fetchone()
        return {'thread': {'id': str(thread_id), 'judul': title}, 'pesan': message_view(row)}

    return router
