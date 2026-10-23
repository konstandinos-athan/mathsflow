"""Real HTTP checks in a disposable database; never writes to the user's DB."""
import re
import sys
import tempfile
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode
from urllib.request import urlopen
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from database import ROOT, connect, migrate
from database.importer import import_data

scratch = ROOT / 'instance' / 'http-tests'
scratch.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=scratch) as folder:
    path = Path(folder) / 'http.sqlite3'
    connection = connect(path, create=True)
    migrate(connection)
    import_data(connection)
    connection.close()
    application = create_app({'DATABASE': str(path), 'SECRET_KEY': 'http-test-only-key'})
    server = make_server('127.0.0.1', 0, application)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        for route in ('/', '/school/gel/g-gel', '/school/epal/g-epal', '/study/gel/a-gel/algebra/1', '/quiz/gel/a-gel/algebra/1', '/static/css/style.css'):
            with urlopen(base + route, timeout=10) as response:
                assert response.status == 200, route
                assert response.read(), route
            print('PASS', route)
        with urlopen(base + '/quiz/gel/a-gel/algebra/1') as response:
            token = re.search(rb'name="attempt_token" value="([^"]+)"', response.read())[1].decode()
        with urlopen(base + '/quiz/gel/a-gel/algebra/1', data=urlencode({'attempt_token': token}).encode()) as response:
            assert response.status == 200
            assert b'0 / 30' in response.read()
        connection = connect(path)
        try:
            assert connection.execute('SELECT COUNT(*) FROM quiz_attempts WHERE submitted_at IS NOT NULL').fetchone()[0] == 1
            assert connection.execute('SELECT COUNT(*) FROM responses').fetchone()[0] == 30
        finally:
            connection.close()
        print('PASS real HTTP submission and durable result')
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
