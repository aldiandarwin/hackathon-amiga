"""OpenAI Responses for the Robot Admin chat, with a spend ledger of its own.

Aldian approved on 15 Oct 2026 that the chat uses his OpenAI key under a separate US$2 cap, so it no longer queues behind
the Titan throttling that other students' traffic causes. The extraction ledger in prototype/.local is another budget;
this module never reads or writes it. Every call sends store:false, so OpenAI keeps no response history.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_UP, Decimal
import json
import logging
import sys
import time

import httpx
from psycopg import sql

from .settings import ROOT
from amiga_ocr.openai_live import read_dotenv

MODEL = 'gpt-6-luna'
# Standard tier, short context, read from developers.openai.com/api/docs/pricing on 15 Oct 2026. Re-verify before expiry.
PRICE_VERIFIED = '2026-10-15'
PRICE_EXPIRES = date(2026, 10, 22)
INPUT_USD, CACHED_USD, OUTPUT_USD = Decimal('0.10'), Decimal('0.01'), Decimal('0.50')
CAP_CEILING = Decimal('2.00')
# Reasoning tokens count inside max_output_tokens, so the cap leaves room for both thinking and the answer.
MAX_OUTPUT_TOKENS = 3000
# Short-context prices end at 272K input tokens. A chat turn stays far below; anything above is unpriced and refused.
MAX_INPUT_TOKENS = 272_000
LEDGER = ('public', 'chat_usage')
# Measured on 15 Oct 2026: most calls answer in 2 to 3 s, but now and then one stalls 9 to 15 s while the next is quick
# again. A stalled call is cut here and retried once.
CALL_SECONDS = 15
log = logging.getLogger(__name__)


class ChatUnavailable(Exception):
    """The turn falls back to plain search. reason: NO_KEY, PRICE_EXPIRED, BUDGET, TIMEOUT or UPSTREAM."""

    def __init__(self, reason, detail=''):
        super().__init__(f'{reason} {detail}'.strip())
        self.reason = reason


@dataclass(frozen=True)
class ChatConfig:
    api_key: str = field(repr=False)
    stop_usd: Decimal = CAP_CEILING

    @classmethod
    def load(cls, path=ROOT / '.env'):
        """None when the key is missing or live calls are switched off in .env; the chat then answers by search only."""
        values = read_dotenv(path) if path.is_file() else {}
        key = values.get('OPENAI_API_KEY', '')
        if values.get('AMIGA_LIVE_ENABLED') != 'true' or not key.startswith('sk-') or any(c.isspace() for c in key):
            return None
        stop = Decimal(values.get('AMIGA_CHAT_STOP_USD', str(CAP_CEILING)))
        if not stop.is_finite() or not Decimal(0) < stop <= CAP_CEILING:
            raise ValueError('AMIGA_CHAT_STOP_USD must be above 0 and at most 2.00.')
        return cls(key, stop)


def usage_cost(usage):
    """Price one call from its reported usage. Reasoning tokens are billed as output and already sit in output_tokens."""
    total, output = usage.get('input_tokens'), usage.get('output_tokens')
    cached = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
    if type(total) is not int or type(output) is not int or type(cached) is not int:
        raise ValueError('usage without token counts')
    if not 0 <= cached <= total <= MAX_INPUT_TOKENS or not 0 <= output <= MAX_OUTPUT_TOKENS:
        raise ValueError('usage outside the priced bounds')
    cost = ((total - cached) * INPUT_USD + cached * CACHED_USD + output * OUTPUT_USD) / 1_000_000
    return cost.quantize(Decimal('0.000001'), ROUND_UP)


class Ledger:
    """Reserve before a call leaves, settle after it returns. A failed or unsettled call keeps its reservation."""

    def __init__(self, db, table=LEDGER):
        self.db, self.table = db, sql.Identifier(*table)

    def _used(self, conn):
        return conn.execute(sql.SQL("SELECT coalesce(sum(CASE WHEN state='DONE' THEN cost_usd ELSE reserved_usd END),0) "
                                    'AS used FROM {}').format(self.table)).fetchone()['used']

    def spent(self):
        with self.db.transaction() as conn:
            return self._used(conn)

    def reserve(self, user_id, reserve_usd, stop_usd):
        with self.db.transaction() as conn:
            # One writer at a time, so two users cannot both pass the check with the last cent of the cap.
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('amiga_chat_usage'))")
            if self._used(conn) + reserve_usd > stop_usd:
                raise ChatUnavailable('BUDGET')
            return conn.execute(sql.SQL("INSERT INTO {} (schema_name,user_id,model,state,reserved_usd) "
                                        "VALUES (%s,%s,%s,'PENDING',%s) RETURNING id").format(self.table),
                                (self.db.settings.schema, user_id, MODEL, reserve_usd)).fetchone()['id']

    def finish(self, row_id, state, usage=None, cost=None, duration_ms=None):
        usage = usage or {}
        with self.db.transaction() as conn:
            conn.execute(sql.SQL('UPDATE {} SET state=%s,cost_usd=%s,input_tokens=%s,cached_tokens=%s,output_tokens=%s,'
                                 'duration_ms=%s WHERE id=%s').format(self.table),
                         (state, cost, usage.get('input_tokens'), (usage.get('input_tokens_details') or {}).get('cached_tokens'),
                          usage.get('output_tokens'), duration_ms, row_id))


def output_text(response):
    return ''.join(part.get('text', '') for item in response.get('output') or [] if item.get('type') == 'message'
                   for part in item.get('content') or [] if part.get('type') == 'output_text').strip()


def replayable(item):
    """An output item sent back as input on the next round. store:false needs the encrypted reasoning, not the status."""
    return {key: value for key, value in item.items() if key != 'status'}


class OpenAIChat:
    def __init__(self, config, ledger, transport=None):
        self.config, self.ledger = config, ledger
        self.http = httpx.Client(base_url='https://api.openai.com/v1/', transport=transport, follow_redirects=False,
                                 headers={'Authorization': 'Bearer ' + config.api_key})

    def ready(self):
        """Whether a turn may try the model now: prices still verified and some budget left."""
        return date.today() <= PRICE_EXPIRES and self.ledger.spent() < self.config.stop_usd

    def respond(self, payload, user_id, deadline):
        """One Responses call inside the turn's deadline. One retry on a stall, 429 or 5xx, only while 8 s or more remain."""
        if date.today() > PRICE_EXPIRES:
            raise ChatUnavailable('PRICE_EXPIRED')
        body = json.dumps({**payload, 'model': MODEL, 'store': False, 'service_tier': 'default',
                           'max_output_tokens': MAX_OUTPUT_TOKENS}, ensure_ascii=False).encode('utf-8')
        # Two bytes per input token is far above the real ratio, so the reservation always covers the call.
        reserve = ((Decimal(len(body)) / 2 * INPUT_USD + MAX_OUTPUT_TOKENS * OUTPUT_USD) / 1_000_000).quantize(
            Decimal('0.000001'), ROUND_UP)
        for attempt in (1, 2):
            remaining = deadline - time.monotonic()
            if remaining < 2:
                raise ChatUnavailable('TIMEOUT')
            row = self.ledger.reserve(user_id, reserve, self.config.stop_usd)
            started = time.monotonic()
            try:
                response = self.http.post('responses', content=body, headers={'Content-Type': 'application/json'},
                                          timeout=httpx.Timeout(min(remaining, CALL_SECONDS), connect=5))
            except httpx.TimeoutException:
                self.ledger.finish(row, 'FAILED')
                if attempt == 1 and deadline - time.monotonic() >= 8:
                    continue
                raise ChatUnavailable('TIMEOUT') from None
            except httpx.HTTPError as error:
                self.ledger.finish(row, 'FAILED')
                raise ChatUnavailable('UPSTREAM', type(error).__name__) from None
            duration = round((time.monotonic() - started) * 1000)
            if response.status_code == 200:
                break
            self.ledger.finish(row, 'FAILED', duration_ms=duration)
            log.warning('OpenAI HTTP %s: %s', response.status_code, response.text[:300])
            retry = response.status_code == 429 or response.status_code >= 500
            if not retry or attempt == 2 or deadline - time.monotonic() < 8:
                raise ChatUnavailable('UPSTREAM', f'HTTP {response.status_code}')
        try:
            result = response.json()
            cost = usage_cost(result.get('usage') or {})
        except ValueError:
            self.ledger.finish(row, 'FAILED', duration_ms=duration)
            raise ChatUnavailable('UPSTREAM', 'unpriced response') from None
        self.ledger.finish(row, 'DONE', result['usage'], cost, duration)
        result['_cost_usd'], result['_duration_ms'] = cost, duration
        return result


def smoke(schema='amiga_qa_chat'):
    """One real two-round function call on the QA schema, to prove the store:false replay before the chat relies on it."""
    from .database import Database
    from .settings import Settings
    local = Settings.load()
    db = Database(Settings(local.database_url, 'test-password-only', ROOT / 'app/test-output' / schema, schema, False))
    db.initialize()
    config = ChatConfig.load()
    if config is None:
        raise SystemExit('OPENAI_API_KEY atau AMIGA_LIVE_ENABLED belum siap di .env.')
    llm, deadline = OpenAIChat(config, Ledger(db)), time.monotonic() + 25
    tool = {'type': 'function', 'name': 'jumlah_invoice', 'description': 'Hitung invoice per vendor.', 'strict': True,
            'parameters': {'type': 'object', 'properties': {'vendor': {'type': 'string'}}, 'required': ['vendor'],
                           'additionalProperties': False}}
    common = {'instructions': 'Jawab satu kalimat dalam bahasa Indonesia.', 'tools': [tool], 'reasoning': {'effort': 'low'},
              'include': ['reasoning.encrypted_content']}
    items = [{'role': 'user', 'content': 'Ada berapa invoice dari vendor Studio Garis Kreatif? Pakai tool.'}]
    first = llm.respond({**common, 'input': items}, 'smoke', deadline)
    calls = [item for item in first['output'] if item.get('type') == 'function_call']
    if not calls:
        raise SystemExit('Model tidak memanggil tool: ' + output_text(first)[:200])
    items += [replayable(item) for item in first['output']]
    items += [{'type': 'function_call_output', 'call_id': call['call_id'],
               'output': json.dumps({'vendor': 'Studio Garis Kreatif', 'jumlah': 3})} for call in calls]
    second = llm.respond({**common, 'input': items, 'tool_choice': 'none'}, 'smoke', deadline)
    for label, result in (('ronde 1', first), ('ronde 2', second)):
        usage = result['usage']
        print(f"{label}: {result['_duration_ms']} ms, input {usage['input_tokens']} "
              f"(cached {(usage.get('input_tokens_details') or {}).get('cached_tokens', 0)}), "
              f"output {usage['output_tokens']}, US${result['_cost_usd']}")
    print('item ronde 1:', [item.get('type') for item in first['output']])
    print('jawaban:', output_text(second))
    print(f"total chat_usage semua schema: US${Ledger(db).spent()} dari cap US${config.stop_usd}")


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    if sys.argv[1:2] != ['--smoke']:
        raise SystemExit('Pakai: python -B -m app.chat_llm --smoke [schema]')
    smoke(*sys.argv[2:3])
