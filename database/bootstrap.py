"""Initialize a deployment from versioned content, never from a personal DB."""
import json
import re
import uuid
from pathlib import Path
from . import ROOT, check, connect, copy_database, digest, migrate
from .importer import import_data, stable
from .theory_content import apply_release, validate_release
from .question_content import deploy_releases


def bootstrap(path):
    path = Path(path)
    if path.exists():
        copy_database(path, path.parent / 'backups' / ('before-start-' + uuid.uuid4().hex + '.sqlite3'))
    db = connect(path, create=True)
    try:
        migrate(db)
        import_data(db)
        latest = {}
        files = sorted((ROOT / 'content/theory').glob('*.v*.json'),
                       key=lambda p: (p.name.split('.v')[0], int(re.search(r'\.v(\d+)\.json$', p.name)[1])))
        for file in files:
            release = json.loads(file.read_text(encoding='utf-8'))
            pending = []
            for unit, entry, blocks in validate_release(release):
                desired = stable('theory-version/' + unit['id'] + '/' + digest(blocks))
                latest[unit['id']] = desired
                # Earlier revisions already in history must never replace newer ones.
                row = db.execute('SELECT unit_id,content_hash FROM theory_versions WHERE id=?', (desired,)).fetchone()
                if row:
                    if row['unit_id'] != unit['id'] or row['content_hash'] != digest(blocks):
                        raise ValueError('Theory history mismatch')
                else:
                    pending.append(entry)
            if pending:
                apply_release(db, {**release, 'entries': pending})
        current = dict(db.execute('SELECT unit_id,version_id FROM current_theory'))
        if current != latest:
            raise ValueError('Active theory differs from deployment releases; manual review required')
        deploy_releases(db)
        return check(db)
    finally:
        db.close()
