"""Bounded admission and disposable parser processes shared by signup paths."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import psycopg2

from flask import current_app, has_app_context
from app.db.connection import db_connect

DEFAULTS = {
    'render_dimension': 2000, 'page_pixels': 4_000_000, 'total_pixels': 40_000_000,
    'image_pixels': 16_000_000, 'page_points': 14400, 'text_chars': 200_000,
    'ocr_seconds': 10, 'job_seconds': 30, 'memory_mb': 768,
}
_local_slot = threading.BoundedSemaphore(1)


class DocumentBusy(ValueError):
    pass


class DocumentTimeout(ValueError):
    pass


@contextmanager
def _slot():
    if not has_app_context():
        if not _local_slot.acquire(blocking=False):
            raise DocumentBusy('Document processing is busy. Try again later.')
        try:
            yield
        finally:
            _local_slot.release()
        return
    conn, selected = None, None
    try:
        conn = db_connect()
        count = int(current_app.config.get('DOCUMENT_MAX_JOBS', 1))
        if not 1 <= count <= 4:
            raise DocumentBusy('Document processing is unavailable.')
        with conn.cursor() as cursor:
            for slot in range(count):
                cursor.execute('SELECT pg_try_advisory_lock(%s, %s)', (17290413, slot))
                if cursor.fetchone()[0]:
                    selected = slot
                    break
        conn.rollback()
        if selected is None:
            raise DocumentBusy('Document processing is busy. Enter details manually or try later.')
        yield
    except psycopg2.Error:
        raise DocumentBusy('Document processing is unavailable. Try again later.') from None
    finally:
        if conn is not None:
            try:
                if selected is not None:
                    conn.rollback()
                    with conn.cursor() as cursor:
                        cursor.execute('SELECT pg_advisory_unlock(%s, %s)', (17290413, selected))
                    conn.rollback()
            finally:
                conn.close()


def process_document(content, extension, operation='validate'):
    if extension not in ('.pdf', '.jpg', '.jpeg', '.png') or operation not in ('validate', 'extract', 'abstract'):
        raise ValueError('Invalid document options.')
    limits = dict(DEFAULTS)
    if has_app_context():
        for key, ceiling in DEFAULTS.items():
            value = int(current_app.config.get('DOCUMENT_' + key.upper(), ceiling))
            if not 1 <= value <= ceiling:
                raise ValueError('Invalid document processing budget.')
            limits[key] = value
    worker = str(Path(__file__).with_name('document_worker.py').resolve())
    if len(content) > (20 if operation == 'abstract' else 5) * 1024**2:
        raise ValueError('Document exceeds the upload budget.')
    # Credentials, cloud configuration, PYTHONPATH and arbitrary inherited options are excluded.
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TESSERACT_CMD', 'SYSTEMROOT') if key in os.environ}
    env.update(OMP_THREAD_LIMIT='1', OPENBLAS_NUM_THREADS='1')
    with _slot(), tempfile.TemporaryDirectory(prefix='capre-document-') as directory, tempfile.TemporaryFile() as output_file:
        env['TMPDIR'] = directory
        env['TEMP'] = env['TMP'] = directory
        try:
            process = subprocess.Popen(
                [sys.executable, '-I', worker, json.dumps(limits), extension, operation],
                stdin=subprocess.PIPE, stdout=output_file, stderr=subprocess.DEVNULL,
                cwd=directory, env=env, start_new_session=(os.name == 'posix'),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except OSError:
            raise DocumentBusy('Document processing is unavailable. Try again later.') from None
        job = None
        try:
            if os.name == 'nt':
                from app.utils.windows_job import WindowsJob
                job = WindowsJob(process, limits['memory_mb'], limits['job_seconds'])
            process.communicate(content, timeout=limits['job_seconds'])
            output_file.seek(0)
            output = output_file.read(limits['text_chars'] * 6 + 1)
            if process.returncode or len(output) > limits['text_chars'] * 6:
                raise ValueError('Document could not be processed within the allowed budget.')
            return json.loads(output)
        except subprocess.TimeoutExpired:
            raise DocumentTimeout('Document processing timed out. Enter details manually or try another file.')
        except OSError:
            raise DocumentBusy('Document processing is unavailable. Try again later.') from None
        finally:
            # Kill the whole group even if a parser exited leaving an OCR descendant behind.
            if job is not None:
                job.close()
            elif os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.communicate()
