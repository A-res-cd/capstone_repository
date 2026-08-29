"""
Database connection helper. Every other app/db/*.py module imports
db_connect() from here — this is the one place PostgreSQL connection
params are read from Config.
"""
import atexit
import threading

import psycopg2
from psycopg2 import extensions
from psycopg2.pool import ThreadedConnectionPool

from config import Config


_pool = None
_pool_lock = threading.Lock()


def _create_pool():
    min_connections = Config.PG_POOL_MIN
    max_connections = Config.PG_POOL_MAX
    if min_connections < 1 or max_connections < min_connections:
        raise RuntimeError("PG_POOL_MIN and PG_POOL_MAX must satisfy 1 <= min <= max")

    return ThreadedConnectionPool(
        minconn=min_connections,
        maxconn=max_connections,
        host=Config.PG_HOST,
        port=Config.PG_PORT,
        user=Config.PG_USER,
        password=Config.PG_PASSWORD,
        database=Config.PG_DB,
    )


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _create_pool()
    return _pool


class _PooledConnection:
    """Proxy whose close() returns the physical connection to the pool."""

    def __init__(self, connection_pool, connection):
        self._pool = connection_pool
        self._connection = connection

    def __getattr__(self, name):
        if self._connection is None:
            raise psycopg2.InterfaceError("connection already returned to pool")
        return getattr(self._connection, name)

    def close(self):
        connection = self._connection
        if connection is None:
            return

        self._connection = None
        discard = bool(connection.closed)
        if not discard:
            try:
                if connection.status != extensions.STATUS_READY:
                    connection.rollback()
            except psycopg2.Error:
                discard = True

        self._pool.putconn(connection, close=discard)

    def __enter__(self):
        if self._connection is None:
            raise psycopg2.InterfaceError("connection already returned to pool")
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._connection.__exit__(exc_type, exc_value, traceback)


def db_connect():
    connection_pool = _get_pool()
    return _PooledConnection(connection_pool, connection_pool.getconn())


def close_pool():
    global _pool
    with _pool_lock:
        connection_pool = _pool
        _pool = None
    if connection_pool is not None:
        connection_pool.closeall()


atexit.register(close_pool)

