"""Small, privacy-safe HTTP request telemetry helpers."""

import json
import logging
import secrets
import time

from flask import g, request


logger = logging.getLogger("capre.http")


def start_request_observation():
    g.request_id = secrets.token_hex(12)
    g.request_started_at = time.perf_counter()


def finish_request_observation(response):
    request_id = getattr(g, "request_id", secrets.token_hex(12))
    started_at = getattr(g, "request_started_at", time.perf_counter())
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id

    if request.endpoint != "static":
        logger.info(
            "http_request %s",
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "endpoint": request.endpoint,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
                separators=(",", ":"),
            ),
        )
        if response.status_code >= 500 and not getattr(g, 'maintenance_active', False):
            try:
                from app.db.system import record_event
                record_event('request_failed', category='request', severity='error', request_id=request_id,
                             details={'endpoint': request.endpoint, 'method': request.method,
                                      'status': response.status_code, 'duration_ms': duration_ms})
            except Exception:
                logger.warning('Could not persist sanitized request failure %s', request_id)
    return response
