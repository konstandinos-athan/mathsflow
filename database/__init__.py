"""SQLite storage, checksummed migrations and explicit data import.

No database is created or modified merely by importing the web application.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / 'instance' / 'mathsflow.sqlite3'


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


def connect(path, *, create=False):
    path = Path(path).resolve()
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.is_file():
        raise RuntimeError('Database missing. Run: python -m database init')
    connection = sqlite3.connect(path.as_uri() + ('?mode=rwc' if create else '?mode=rw'), uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA busy_timeout=10000')
    return connection


def statements(sql):
    buffer = ''
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            yield buffer
            buffer = ''
    if buffer.strip():
        raise ValueError('Incomplete migration statement')


def migrate(connection, directory=None):
    directory = Path(directory or ROOT / 'migrations')
    files = sorted(directory.glob('[0-9][0-9][0-9]_*.sql'))
    if not files:
        raise ValueError('No migrations found')
    connection.execute('BEGIN IMMEDIATE')
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL)')
        applied = dict(connection.execute('SELECT name, checksum FROM schema_migrations'))
        if set(applied) - {p.name for p in files}:
            raise ValueError('Database contains unknown migrations')
        for file in files:
            checksum = hashlib.sha256(file.read_bytes()).hexdigest()
            if file.name in applied:
                if applied[file.name] != checksum:
                    raise ValueError('Applied migration changed: ' + file.name)
                continue
            for statement in statements(file.read_text(encoding='utf-8')):
                connection.execute(statement)
            connection.execute('INSERT INTO schema_migrations VALUES (?,?)', (file.name, checksum))
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def check(connection):
    integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
    if integrity != 'ok' or list(connection.execute('PRAGMA foreign_key_check')):
        raise ValueError('Database integrity check failed')
    applied = dict(connection.execute('SELECT name, checksum FROM schema_migrations'))
    expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'migrations').glob('[0-9][0-9][0-9]_*.sql')}
    if applied != expected:
        raise ValueError('Database migrations do not match the application')
    return {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('courses', 'units', 'theory_versions', 'questions', 'question_versions', 'quiz_attempts', 'responses')}


def copy_database(source_path, destination_path):
    """Online consistent backup or restore to a NEW file; never overwrite data."""
    source_path, destination_path = Path(source_path).resolve(), Path(destination_path).resolve()
    if source_path == destination_path:
        raise ValueError('Source and destination must differ')
    source = connect(source_path)
    try:
        check(source)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        # Reserve exclusively, preventing accidental replacement of an existing DB.
        with destination_path.open('xb'):
            pass
        destination = connect(destination_path)
        try:
            source.backup(destination)
            result = check(destination)
        finally:
            destination.close()
        return result
    finally:
        source.close()
