"""Render entry point: gunicorn --preload wsgi:app."""
import os
import secrets
from pathlib import Path
from database import DEFAULT_PATH, is_postgres
from database.bootstrap import bootstrap

database_path = os.environ.get('DATABASE_URL') or os.environ.get('MATHSFLOW_DATABASE', str(DEFAULT_PATH))
if is_postgres(database_path) and not os.environ.get('SECRET_KEY'):
    raise RuntimeError('PostgreSQL deployment requires a stable SECRET_KEY in the environment')
bootstrap(database_path)
if not os.environ.get('SECRET_KEY'):
    # Stable on the same filesystem, shared by workers; never committed or served.
    key_path = Path(database_path).parent / '.session-key'
    if not key_path.exists():
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(secrets.token_hex(32))
    os.environ['SECRET_KEY'] = key_path.read_text().strip()
os.environ['MATHSFLOW_ENV'] = 'production'
from app import app
