"""PostgreSQL transport for existing parameterized repository queries.

Explicit write transactions use one advisory lock to preserve the SQLite single-writer
contract during the first migration. This is conservative, not a scaling strategy.
"""
import hashlib
import sqlite3
from pathlib import Path


def parameters(sql):
    """Convert qmark parameters, never interpolate values or alter quoted literals."""
    result = []
    quote = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote:
            result.append('%%' if char == '%' else char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    result.append(quote)
                    index += 1
                else:
                    quote = None
        elif char in ('"', "'"):
            quote = char
            result.append(char)
        elif char == '?':
            result.append('%s')
        elif char == '%':
            result.append('%%')
        elif sql[index:index+2] in ('--', '/*') or char == '$':
            raise ValueError('Parameterized application SQL does not support comments or dollar quoting')
        else:
            result.append(char)
        index += 1
    if quote:
        raise ValueError('Unterminated SQL literal')
    return ''.join(result)


class Row:
    def __init__(self, names, values):
        self.names, self.values = names, values

    def keys(self):
        return self.names

    def __getitem__(self, key):
        return self.values[self.names.index(key)] if isinstance(key, str) else self.values[key]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


def row_factory(cursor):
    names = tuple(column.name for column in cursor.description) if cursor.description else ()
    return lambda values: Row(names, values)


class Connection:
    dialect = 'postgres'

    def __init__(self, url):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        self.driver = psycopg
        try:
            options = conninfo_to_dict(url)
            if options.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
                raise ValueError('PostgreSQL requires an explicitly encrypted connection')
            self.raw = psycopg.connect(url, autocommit=True, connect_timeout=15,
                                      row_factory=row_factory, prepare_threshold=None)
            self.raw.execute("SET statement_timeout = '30s'")
            self.raw.execute("SET lock_timeout = '10s'")
            self.raw.execute("SET idle_in_transaction_session_timeout = '60s'")
        except (psycopg.Error, ValueError):
            # Driver messages may include a DSN or credentials. Never echo those.
            raise RuntimeError('PostgreSQL connection failed; verify credentials, TLS and availability') from None

    def execute(self, sql, values=None):
        try:
            if sql.strip().upper() == 'BEGIN IMMEDIATE':
                self.raw.execute('BEGIN')
                try:
                    return self.raw.execute('SELECT pg_advisory_xact_lock(731904261)')
                except Exception:
                    self.raw.rollback()
                    raise
            if sql.strip().upper() == 'BEGIN':
                return self.raw.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            return self.raw.execute(parameters(sql) if values is not None else sql, values)
        except self.driver.IntegrityError:
            raise sqlite3.IntegrityError('Database integrity constraint rejected the operation') from None
        except self.driver.Error:
            raise RuntimeError('PostgreSQL operation failed') from None

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def migration_files():
    return sorted((Path(__file__).resolve().parents[1] / 'migrations_postgres').glob('[0-9][0-9][0-9]_*.sql'))


def migrate(db):
    files = migration_files()
    if not files:
        raise RuntimeError('PostgreSQL schema migrations missing')
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL)')
        applied = dict(db.execute('SELECT name,checksum FROM schema_migrations'))
        if sorted(applied) != [file.name for file in files][:len(applied)]:
            raise ValueError('PostgreSQL migration history is not a known prefix')
        for file in files:
            checksum = hashlib.sha256(file.read_bytes()).hexdigest()
            if file.name in applied:
                if applied[file.name] != checksum:
                    raise ValueError('Applied PostgreSQL migration changed')
                continue
            db.execute(file.read_text(encoding='utf-8'))
            db.execute('INSERT INTO schema_migrations VALUES (?,?)', (file.name, checksum))
        db.commit()
    except Exception:
        db.rollback()
        raise


def check(db):
    expected = {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in migration_files()}
    if dict(db.execute('SELECT name,checksum FROM schema_migrations')) != expected:
        raise ValueError('PostgreSQL migration checksums differ')
    return {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('courses', 'units', 'theory_versions', 'questions', 'question_versions', 'quiz_attempts', 'responses')}
