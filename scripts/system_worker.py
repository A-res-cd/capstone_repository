"""Run one durable maintenance worker, separately from Flask web workers."""
import argparse
from contextlib import closing
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from app.db.connection import db_connect
from app.db import system
from app.services.system_maintenance import run_job


def process_next():
    row = system.claim_job()
    if not row:
        return False
    try:
        result = run_job(row)
    except Exception as exc:
        from flask import current_app
        current_app.logger.exception('Maintenance job %s failed', row['job_id'])
        # Avoid copying tracebacks, SQL, paths, or connection secrets into UI.
        detail = str(exc) if isinstance(exc, ValueError) else 'Operation failed. Inspect the protected server logs.'
        system.finish_job(row['job_id'], {'error': detail}, failed=True)
    else:
        system.finish_job(row['job_id'], result)
    return True


def schedule():
    settings = system.settings()
    for kind, hours in [('backup', settings['backup_interval_hours']), ('diagnostics', 1), ('archive_purge', 24)]:
        if system.due(kind, hours):
            try:
                system.enqueue(kind, None, 'Scheduled maintenance')
            except ValueError:
                pass  # Another request queued this kind after the due check.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='Process one queued job without scheduling new work.')
    args = parser.parse_args()
    app = create_app()
    with app.app_context(), closing(db_connect()) as lock_connection:
        with lock_connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext('capre.maintenance-worker'))")
            if not cur.fetchone()[0]:
                raise SystemExit('A maintenance worker is already running.')
        lock_connection.commit()
        stop = threading.Event()
        def pulse():
            with app.app_context():
                while not stop.is_set():
                    try:
                        system.heartbeat()
                    except Exception:
                        app.logger.exception('Maintenance worker heartbeat failed')
                    stop.wait(30)
        heartbeat = threading.Thread(target=pulse, daemon=True)
        heartbeat.start()
        try:
            system.recover_interrupted_jobs()
            while True:
                # Validate the lock connection before claiming more work.
                with lock_connection.cursor() as cur:
                    cur.execute('SELECT 1')
                lock_connection.commit()
                if not args.once:
                    schedule()
                worked = process_next()
                if args.once:
                    break
                if not worked:
                    time.sleep(5)
        finally:
            stop.set()
            heartbeat.join(timeout=5)
            with lock_connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext('capre.maintenance-worker'))")


if __name__ == '__main__':
    main()
