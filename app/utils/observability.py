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
    return response
