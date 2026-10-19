"""A PIC opens a new client for the team: the PIC, the team's Finance reviewer and AMIGA's director get it at once."""

import re
from string import ascii_uppercase

from psycopg.types.json import Jsonb

from .database import DEMO_VENDOR_NPWP
from .service import AppError
from amiga_ocr.validation import identity

# A client is a business: its name starts with the legal form, as printed on invoices and vouchers.
LEGAL_FORMS = ('PT', 'CV', 'UD', 'KOPERASI', 'YAYASAN', 'FIRMA')
NAME_PATTERN = re.compile(r'(?:PT|CV|UD|Koperasi|Yayasan|Firma)\.?\s+\S.*')


def suggest_code(name, taken):
    """Three letters from the initials of the words after the legal form, then from the name itself, then the first
    two initials with a running letter, so a new client always gets a code no other client uses."""
    words = [word.upper() for word in re.findall(r'[A-Za-z]+', name) if word.upper() not in LEGAL_FORMS]
    initials, letters = ''.join(word[0] for word in words), ''.join(words)
    candidates = [initials[:3], letters[:3]] + [(initials if len(initials) > 1 else letters)[:2] + letter
                                               for letter in ascii_uppercase]
    return next((code for code in candidates if len(code) == 3 and code not in taken), None)


class ClientService:
    def __init__(self, db):
        self.db = db

    def create(self, user, name, city=None, sector=None, npwp=None, code=None):
        if user['role'] != 'PIC':
            raise AppError('FORBIDDEN', 'Klien baru hanya dibuat oleh PIC Intake.', 403)
        name, city, sector = (' '.join((value or '').split()) or None for value in (name, city, sector))
        if not name or not NAME_PATTERN.fullmatch(name):
            raise AppError('INVALID_PAYLOAD', 'Tulis nama klien lengkap dengan bentuk usahanya, misalnya CV Sinar Baru Teknik.', 422)
        npwp = (npwp or '').strip() or None
        if npwp and len(re.sub(r'\D', '', npwp)) not in (15, 16):
            raise AppError('INVALID_PAYLOAD', 'NPWP klien berisi 15 atau 16 angka.', 422)
        code = (code or '').strip().upper() or None
        if code and not re.fullmatch(r'[A-Z]{3}', code):
            raise AppError('INVALID_PAYLOAD', 'Kode klien tiga huruf, misalnya SBT.', 422)
        with self.db.transaction() as conn:
            # One new client at a time, so two PICs cannot take the same name or code in the same moment.
            conn.execute('LOCK TABLE clients IN SHARE ROW EXCLUSIVE MODE')
            existing = conn.execute('SELECT name,code FROM clients').fetchall()
            if any(identity(row['name']) == identity(name) for row in existing):
                raise AppError('CLIENT_EXISTS', f'Klien {name} sudah ada, jadi tidak didaftarkan lagi. Pilih dari daftar '
                               'Klien, atau minta admin AMIGA menghubungkan akun Anda.', 409)
            taken = {row['code'] for row in existing if row['code']}
            if code in taken:
                raise AppError('CLIENT_EXISTS', f'Kode {code} sudah dipakai klien lain. Pilih kode lain.', 409)
            code = code or suggest_code(name, taken)
            if not code:
                raise AppError('INVALID_PAYLOAD', 'Isi kode klien tiga huruf.', 422)
            identifier, team = 'client_' + code.lower(), user.get('team')
            conn.execute('INSERT INTO clients(id,name,code,city,sector,npwp,team,created_by,created_at) '
                         'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())',
                         (identifier, name, code, city, sector, npwp, team, user['id']))
            # The creator, the rest of the team and every active director, so the client is reviewed and signed.
            members = conn.execute("SELECT id,name FROM users WHERE disabled_at IS NULL AND (id=%s OR "
                                   "(team IS NOT NULL AND team=%s) OR role='AMIGA_DIRECTOR') ORDER BY id",
                                   (user['id'], team)).fetchall()
            for member in members:
                conn.execute('INSERT INTO assignments VALUES (%s,%s)', (member['id'], identifier))
            # The demo vendor keeps the sample buttons working for the new client too.
            conn.execute('INSERT INTO vendors(client_id,id,name,verified_accounts,npwp) VALUES (%s,%s,%s,%s,%s)',
                         (identifier, 'vendor_demo', 'PT Contoh Demo', Jsonb(['00123456']), DEMO_VENDOR_NPWP))
            client = {'id': identifier, 'name': name, 'code': code, 'city': city, 'sector': sector, 'npwp': npwp,
                      'team': team}
            conn.execute('INSERT INTO client_events(client_id,actor_id,action,changes) VALUES (%s,%s,%s,%s)',
                         (identifier, user['id'], 'CLIENT_CREATED', Jsonb(client | {'members': [m['id'] for m in members]})))
        return {'client': client, 'members': [member['name'] for member in members]}
