"""Prepare local demo credentials without touching OpenAI settings or its ledger."""

from pathlib import Path
import secrets
from .settings import ROOT
from amiga_ocr.openai_live import read_dotenv


def main():
    path = ROOT / '.env'
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    values = read_dotenv(path) if path.exists() else {}
    additions = {}
    db_password = values.get('AMIGA_DB_PASSWORD')
    if not db_password:
        db_password = secrets.token_hex(24)
        additions['AMIGA_DB_PASSWORD'] = db_password
    if not values.get('AMIGA_DATABASE_URL'):
        additions['AMIGA_DATABASE_URL'] = f'postgresql://amiga:{db_password}@127.0.0.1:15432/amiga'
    if not values.get('AMIGA_DEMO_PASSWORD'):
        additions['AMIGA_DEMO_PASSWORD'] = secrets.token_urlsafe(18)
    if additions:
        path.write_text(existing.rstrip()+'\n'+''.join(f'{k}={v}\n' for k,v in additions.items()),encoding='utf-8')
    values.update(additions)
    private = ROOT / '.appdata'
    private.mkdir(exist_ok=True)
    (private/'demo-access.txt').write_text(
        'AMIGA local demo: http://127.0.0.1:8787\n\n'
        'Finance client A: finance@amiga.local\nPIC client A: pic@amiga.local\n'
        'Finance client B: finance.b@amiga.local\nPIC client B: pic.b@amiga.local\n'
        'Manajer Keuangan AMIGA (semua klien): manajer.keuangan@amiga.local\n\nPassword: '
        +values['AMIGA_DEMO_PASSWORD']+'\n',encoding='utf-8')
    print('Local demo configuration ready. Credentials: .appdata/demo-access.txt. OpenAI ledger unchanged.')


if __name__ == '__main__':
    main()
