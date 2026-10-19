"""PostgreSQL transaction boundary for demo accounts and invoice review."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from pathlib import Path
import secrets

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .specimen import synthetic_specimen


DEMO_VENDOR_NPWP = '99.123.456.7-012.000'
# Portfolios (15 Oct): each team's PIC and Finance reviewer hold the same ten clients; AMIGA's director holds all twenty.
# Invented companies. Tuples on purpose: knowledge-base/tools/bangun_korpus.py reads the values of any dict key named
# 'code' as app error codes.
CLIENTS = [
    ('client_a', 'PT Arunika Sejahtera', 'ARS', 'Jakarta Selatan', 'Distribusi alat kesehatan', 'A'),
    ('client_a02', 'PT Sinar Kalingga Logistik', 'SKL', 'Bekasi', 'Logistik dan pergudangan', 'A'),
    ('client_a03', 'CV Dapur Nusa Rasa', 'DNR', 'Depok', 'Katering', 'A'),
    ('client_a04', 'PT Tirta Mandala Abadi', 'TMA', 'Bogor', 'Air minum dalam kemasan', 'A'),
    ('client_a05', 'PT Griya Cipta Konstruksi', 'GCK', 'Tangerang Selatan', 'Kontraktor bangunan', 'A'),
    ('client_a06', 'PT Medika Sehat Bersama', 'MSB', 'Bandung', 'Klinik', 'A'),
    ('client_a07', 'PT Cahaya Printindo Grafika', 'CPG', 'Jakarta Barat', 'Percetakan', 'A'),
    ('client_a08', 'PT Edukasi Cerdas Nusantara', 'ECN', 'Jakarta Timur', 'Lembaga kursus', 'A'),
    ('client_a09', 'CV Kopi Lembah Priangan', 'KLP', 'Garut', 'Sangrai kopi', 'A'),
    ('client_a10', 'PT Karya Digital Solusindo', 'KDS', 'Jakarta Pusat', 'Pengembang perangkat lunak', 'A'),
    ('client_b', 'PT Bumi Persada', 'BMP', 'Semarang', 'Konstruksi sipil', 'B'),
    ('client_b02', 'PT Samudra Hasil Bahari', 'SHB', 'Surabaya', 'Pengolahan hasil laut', 'B'),
    ('client_b03', 'PT Agro Tani Lestari', 'ATL', 'Malang', 'Sarana pertanian', 'B'),
    ('client_b04', 'CV Batik Sekar Laweyan', 'BSL', 'Surakarta', 'Kerajinan batik', 'B'),
    ('client_b05', 'PT Andalas Energi Teknik', 'AET', 'Medan', 'Jasa teknik kelistrikan', 'B'),
    ('client_b06', 'PT Pesona Wisata Dewata', 'PWD', 'Denpasar', 'Biro perjalanan', 'B'),
    ('client_b07', 'PT Mahakam Alat Berat', 'MAB', 'Balikpapan', 'Sewa alat berat', 'B'),
    ('client_b08', 'CV Rumah Kayu Jepara', 'RKJ', 'Jepara', 'Mebel kayu', 'B'),
    ('client_b09', 'PT Celebes Niaga Sentosa', 'CNS', 'Makassar', 'Distribusi barang konsumsi', 'B'),
    ('client_b10', 'PT Tugu Rasa Nusantara', 'TRN', 'Yogyakarta', 'Restoran', 'B'),
]
# The first two clients were seeded under these names; each is renamed once, only while it still carries its old name.
OLD_CLIENT_NAMES = {'client_a': 'Arunika Sejahtera', 'client_b': 'Bumi Persada'}
# Printed as the buyer on the stage 6 demo invoices.
CLIENT_NPWP = {'client_a': '99.765.432.1-098.000'}


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 210_000).hex()
    return salt + ':' + digest


def password_matches(password, stored):
    return hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Database:
    def __init__(self, settings):
        self.settings = settings

    def open(self):
        conn = psycopg.connect(self.settings.database_url, row_factory=dict_row, connect_timeout=5)
        conn.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(self.settings.schema)))
        conn.commit()
        return conn

    @contextmanager
    def transaction(self):
        with self.open() as conn:
            yield conn

    def initialize(self):
        with psycopg.connect(self.settings.database_url, connect_timeout=5) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.settings.schema)))
        with self.transaction() as conn:
            conn.execute(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
            for identifier, name, code, city, sector, team in CLIENTS:
                conn.execute('INSERT INTO clients(id,name) VALUES (%s,%s) ON CONFLICT DO NOTHING', (identifier, name))
                if identifier in OLD_CLIENT_NAMES:
                    conn.execute('UPDATE clients SET name=%s WHERE id=%s AND name=%s',
                                 (name, identifier, OLD_CLIENT_NAMES[identifier]))
                # Only fills missing values, so a later change by the team stays.
                conn.execute('UPDATE clients SET code=coalesce(code,%s),city=coalesce(city,%s),sector=coalesce(sector,%s),'
                             'npwp=coalesce(npwp,%s),team=coalesce(team,%s) WHERE id=%s',
                             (code, city, sector, CLIENT_NPWP.get(identifier), team, identifier))
                conn.execute('INSERT INTO vendors VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                             (identifier, 'vendor_demo', 'PT Contoh Demo', Jsonb(['00123456'])))
                # Synthetic NPWP printed on the stage 6 demo invoices; only fills a missing value.
                conn.execute("UPDATE vendors SET npwp=%s WHERE client_id=%s AND id='vendor_demo' AND npwp IS NULL",
                             (DEMO_VENDOR_NPWP, identifier))
            accounts = [('pic_a', 'Dian Pratama', 'pic@amiga.local', 'PIC', 'A'),
                        ('pic_b', 'Sari Utami', 'pic.b@amiga.local', 'PIC', 'B'),
                        ('finance_a', 'Nadia Putri', 'finance@amiga.local', 'FINANCE_REVIEWER', 'A'),
                        ('finance_b', 'Raka Bumi', 'finance.b@amiga.local', 'FINANCE_REVIEWER', 'B'),
                        # AMIGA's Manajer Keuangan gives the final approval for every client; the client pays outside.
                        # The role code stays AMIGA_DIRECTOR, since signed history refers to it.
                        ('direksi_a', 'Bagas Wiratama', 'manajer.keuangan@amiga.local', 'AMIGA_DIRECTOR', None)]
            titles = {'pic_a': 'Admin Intake AMIGA', 'pic_b': 'Admin Intake AMIGA', 'finance_a': 'Finance Reviewer AMIGA',
                      'finance_b': 'Finance Reviewer AMIGA', 'direksi_a': 'Manajer Keuangan AMIGA'}
            # The first stage 8 design had one director per client company. The id stays, so any step signed under it
            # stays linked; the account becomes AMIGA's BOD, and the other client director loses its client.
            moved = conn.execute("UPDATE users SET email='direksi@amiga.local',title='Direktur Utama AMIGA' "
                                 "WHERE id='direksi_a' AND email='direksi.a@klien.local' RETURNING id").fetchone()
            if moved:  # once, in the same start that moves the account; a later assignment stays
                conn.execute("DELETE FROM assignments WHERE user_id='direksi_b'")
            # 15 Okt 2026, Aldian: the final approver is AMIGA's Manajer Keuangan, not the BOD, and the PIC signs the
            # printed voucher as Admin Intake. Same ids, so every step already signed stays linked; runs once.
            conn.execute("UPDATE users SET email='manajer.keuangan@amiga.local',title='Manajer Keuangan AMIGA' "
                         "WHERE id='direksi_a' AND email='direksi@amiga.local'")
            conn.execute("UPDATE users SET title='Admin Intake AMIGA' WHERE role='PIC' AND title='PIC Klien'")
            for identifier, name, email, role, team in accounts:
                conn.execute('INSERT INTO users VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                             (identifier, name, email, password_hash(self.settings.demo_password), role))
                if team:
                    conn.execute('UPDATE users SET team=%s WHERE id=%s AND team IS NULL', (team, identifier))
                # A team holds its ten clients; the BOD, without a team, holds every client.
                for client, *_, client_team in CLIENTS:
                    if team is None or client_team == team:
                        conn.execute('INSERT INTO assignments VALUES (%s,%s) ON CONFLICT DO NOTHING', (identifier, client))
                # The job title printed under each signature; only fills a missing value, like the NPWP above.
                conn.execute('UPDATE users SET title=%s WHERE id=%s AND title IS NULL', (titles[identifier], identifier))
                # Signers get a made-up specimen once; a real one would be registered by its owner.
                if role != 'PIC' and not conn.execute('SELECT 1 FROM signature_specimens WHERE user_id=%s',
                                                      (identifier,)).fetchone():
                    png = synthetic_specimen(name)
                    conn.execute("INSERT INTO signature_specimens(sha256,user_id,image_png,source) "
                                 "VALUES (%s,%s,%s,'SYNTHETIC_DEMO')", (hashlib.sha256(png).hexdigest(), identifier, png))

    def verify_password(self, user_id, password):
        """A signature re-checks the stored hash, so it needs the password at that moment, not only a session."""
        with self.transaction() as conn:
            row = conn.execute('SELECT password_hash FROM users WHERE id=%s', (user_id,)).fetchone()
        return bool(row) and password_matches(password, row['password_hash'])

    def login(self, email, password):
        with self.transaction() as conn:
            user = conn.execute('SELECT * FROM users WHERE email=%s', (email,)).fetchone()
            # A closed account gets the same answer as a wrong password, so the reply does not reveal it.
            if not user or not password_matches(password, user['password_hash']) or user['disabled_at']:
                return None
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            conn.execute('INSERT INTO sessions VALUES (%s,%s,%s,%s)',
                         (token_hash(token), user['id'], csrf, datetime.now(timezone.utc) + timedelta(hours=8)))
            return token, csrf

    def session(self, token):
        with self.transaction() as conn:
            user = conn.execute('SELECT u.id,u.name,u.email,u.role,u.team,s.csrf FROM sessions s JOIN users u '
                                'ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at>now() '
                                'AND u.disabled_at IS NULL',
                                (token_hash(token),)).fetchone()
            if not user:
                return None
            user['clients'] = conn.execute('SELECT c.id,c.name,c.code,c.city,c.sector,c.team FROM assignments a '
                                           'JOIN clients c ON c.id=a.client_id WHERE a.user_id=%s '
                                           'ORDER BY c.team NULLS LAST,c.name', (user['id'],)).fetchall()
            return user

    def logout(self, token):
        with self.transaction() as conn:
            # Expire sessions, without deleting business history.
            conn.execute('UPDATE sessions SET expires_at=now() WHERE token_hash=%s', (token_hash(token),))

    @staticmethod
    def scoped_request(conn, request_id, user, lock=False):
        return conn.execute('SELECT r.* FROM requests r JOIN assignments a ON a.client_id=r.client_id '
                            'AND a.user_id=%s WHERE r.id=%s' + (' FOR UPDATE OF r' if lock else ''),
                            (user['id'], request_id)).fetchone()

    @staticmethod
    def audit(conn, request_id, actor, action, reason, changes, version):
        conn.execute('INSERT INTO audit_events(request_id,actor_id,action,reason,changes,version) '
                     'VALUES (%s,%s,%s,%s,%s,%s)', (request_id, actor, action, reason, Jsonb(changes), version))

    def locked_request(self, conn, request_id, user):
        row = self.scoped_request(conn, request_id, user)
        if row:
            # The same order is used by intake, draft edits, extraction and approval.
            conn.execute('SELECT id FROM clients WHERE id=%s FOR UPDATE', (row['client_id'],))
            row = self.scoped_request(conn, request_id, user, lock=True)
        return row
