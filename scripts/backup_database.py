"""Create a private PostgreSQL backup; never write credentials to command arguments."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path,
                        help='Private directory outside the repository and public web folders')
    parser.add_argument('--include-uploads', action='store_true', help='Also archive private uploaded files')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = args.output.resolve()
    if destination == root or root in destination.parents:
        parser.error('Choose a private directory outside the repository.')
    load_dotenv(root / '.env')
    env = os.environ.copy()
    for source, target in [('PG_HOST', 'PGHOST'), ('PG_PORT', 'PGPORT'),
                           ('PG_USER', 'PGUSER'), ('PG_PASSWORD', 'PGPASSWORD'),
                           ('PG_DB', 'PGDATABASE')]:
        if env.get(source):
            env[target] = env[source]
    env['PGCONNECT_TIMEOUT'] = '10'
    for tool in ('pg_dump', 'pg_restore'):
        if not shutil.which(tool):
            parser.error(f'{tool} must be installed and on PATH.')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    filename = destination / ('capre-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.dump')
    try:
        with filename.open('xb') as output:
            os.chmod(filename, 0o600)
            subprocess.run(['pg_dump', '--format=custom', '--no-password'],
                           env=env, stdout=output, check=True)
        subprocess.run(['pg_restore', '--list', str(filename)],
                       stdout=subprocess.DEVNULL, check=True)
    except (OSError, subprocess.CalledProcessError):
        filename.unlink(missing_ok=True)
        raise SystemExit('Backup failed; incomplete dump removed.')
    print(f'Backup created and archive listing checked: {filename}')
    if args.include_uploads:
        folders = {
            'manuscripts': os.environ.get('UPLOAD_MANUSCRIPT_FOLDER') or os.environ.get('UPLOAD_FOLDER') or root / 'instance/uploads/manuscripts',
            'registration': os.environ.get('UPLOAD_REGISTRATION_FOLDER') or root / 'instance/uploads/registration',
            'avatars': root / 'instance/uploads/avatars',
            'legacy': root / 'app/static/uploads',
        }
        archive = filename.with_suffix('.uploads.zip')
        try:
            with archive.open('xb') as output:
                os.chmod(archive, 0o600)
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipped:
                    for label, folder in folders.items():
                        folder = Path(folder)
                        if not folder.is_absolute():
                            folder = root / folder
                        if folder.is_dir():
                            for item in folder.rglob('*'):
                                if item.is_file() and not item.is_symlink():
                                    zipped.write(item, str(Path(label) / item.relative_to(folder)))
            with zipfile.ZipFile(archive) as zipped:
                if zipped.testzip():
                    raise ValueError('Upload archive verification failed.')
        except Exception:
            archive.unlink(missing_ok=True)
            raise
        print(f'Uploaded files archived and checked: {archive}')
    print('Restore into a separate test database before applying migrations.')


if __name__ == '__main__':
    main()
