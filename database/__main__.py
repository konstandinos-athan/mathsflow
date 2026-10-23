import argparse
import os
from pathlib import Path
from . import DEFAULT_PATH, check, connect, copy_database, migrate
from .importer import import_data


def main():
    parser = argparse.ArgumentParser(description='MathsFlow database administration')
    parser.add_argument('--database', type=Path, default=Path(os.environ.get('MATHSFLOW_DATABASE', DEFAULT_PATH)))
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('init', help='Migrate and import the validated initial content (idempotent)')
    sub.add_parser('migrate', help='Apply pending schema migrations only')
    sub.add_parser('check', help='Verify integrity, foreign keys and migration checksums')
    backup = sub.add_parser('backup', help='Consistent backup to a new file')
    backup.add_argument('destination', type=Path)
    restore = sub.add_parser('restore', help='Restore a backup to a new database file; never overwrites')
    restore.add_argument('backup', type=Path)
    args = parser.parse_args()
    if args.action == 'backup':
        print(copy_database(args.database, args.destination))
        return
    if args.action == 'restore':
        print(copy_database(args.backup, args.database))
        return
    connection = connect(args.database, create=args.action in ('init', 'migrate'))
    try:
        if args.action in ('init', 'migrate'):
            migrate(connection)
        if args.action == 'init':
            print(import_data(connection))
        print(check(connection))
    finally:
        connection.close()


if __name__ == '__main__':
    main()
