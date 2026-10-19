"""Conservative, persistent accounting for this experiment, not the whole account."""

from datetime import datetime, timezone
from contextlib import closing, contextmanager
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

USER_CEILING_USD = Decimal('10.00')
OPERATIONAL_CEILING_USD = Decimal('8.00')
# Every POST permanently consumes $0.30 of authorization, even on failure.
# GPT-6 Luna full 1.05M context at long-context cache-write rates + 8192 output
# tokens is $0.268644 at verified 2026-10-12 prices. $0.30 still covers that worst case;
# measured runs cost $0.0004 to $0.001 (lowered from $1 on 14 Okt for the 7 real-case invoices).
RESERVATION_MICRO_USD = 300_000


class BudgetError(ValueError):
    pass


class BudgetLedger:
    def __init__(self, path: Path, stop_usd=OPERATIONAL_CEILING_USD, reservation_micro_usd=RESERVATION_MICRO_USD):
        self.path = Path(path).resolve()
        if not stop_usd.is_finite() or not Decimal('0') < stop_usd <= OPERATIONAL_CEILING_USD:
            raise BudgetError('AMIGA_STOP_USD must be positive and at most 8.00.')
        if type(reservation_micro_usd) is not int or not 0 < reservation_micro_usd <= RESERVATION_MICRO_USD:
            raise BudgetError('A reservation must be a positive whole micro-dollar amount, at most 0.30 USD.')
        self.limit = int(stop_usd * 1_000_000)
        # The Bedrock ledger reserves less per call than OpenAI: its worst case is priced separately.
        self.reservation = reservation_micro_usd

    def initialize(self):
        """One-time provisioning only. Never reset an existing ledger."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('xb'):
            pass
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute('CREATE TABLE attempts (id TEXT PRIMARY KEY, created TEXT NOT NULL, '
                             'case_id TEXT NOT NULL, reserved INTEGER NOT NULL, state TEXT NOT NULL, '
                             'usage_json TEXT, cost_upper_usd TEXT)')

    @contextmanager
    def _connect(self):
        if not self.path.is_file():
            raise BudgetError('Budget ledger missing; refusing to reset or start spending.')
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)) as conn:
            with conn:
                yield conn

    def reserve(self, case_id: str) -> str:
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows = conn.execute('SELECT reserved, state FROM attempts').fetchall()
            if any(state in ('PENDING', 'UNCERTAIN', 'COST_BREACH') for _, state in rows):
                raise BudgetError('Unreconciled request exists; stop and inspect the ledger.')
            if sum(value for value, _ in rows) + self.reservation > self.limit:
                raise BudgetError('Operational budget exhausted; no request was sent.')
            run_id = str(uuid4())
            conn.execute('INSERT INTO attempts VALUES (?, ?, ?, ?, ?, NULL, NULL)',
                         (run_id, datetime.now(timezone.utc).isoformat(), case_id,
                          self.reservation, 'PENDING'))
        return run_id

    def finish(self, run_id: str, state: str, usage=None, cost_upper=None):
        if state not in ('COMPLETED', 'HTTP_ERROR', 'UNCERTAIN', 'COST_BREACH'):
            raise BudgetError('Unknown terminal budget state.')
        with self._connect() as conn:
            changed = conn.execute('UPDATE attempts SET state=?, usage_json=?, cost_upper_usd=? '
                                   "WHERE id=? AND state='PENDING'",
                                   (state, json.dumps(usage) if usage is not None else None,
                                    str(cost_upper) if cost_upper is not None else None, run_id)).rowcount
            if changed != 1:
                raise BudgetError('Attempt absent or already finalized.')

    def snapshot(self):
        with self._connect() as conn:
            rows = conn.execute('SELECT id, state, reserved, cost_upper_usd FROM attempts ORDER BY created').fetchall()
        reserved = sum(row[2] for row in rows)
        return {'scope': 'AMIGA_LOCAL_HARNESS_ONLY', 'user_ceiling_usd': '10.00',
                'operational_ceiling_usd': str(Decimal(self.limit) / 1_000_000),
                'attempt_count': len(rows), 'reserved_authorization_usd': str(Decimal(reserved) / 1_000_000),
                'remaining_authorization_usd': str(Decimal(max(0, self.limit-reserved)) / 1_000_000),
                'remaining_calls': max(0, self.limit-reserved) // self.reservation,
                'usage_cost_upper_estimate_usd': str(sum((Decimal(row[3]) for row in rows if row[3] is not None), Decimal(0))),
                'unknown_cost_attempts': sum(row[3] is None for row in rows),
                'states': [row[1] for row in rows]}
