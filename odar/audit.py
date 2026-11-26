"""Audit trail: file first (always), then PostgreSQL (append-only table)."""
import logging
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from odar.config import get_settings

_audit_file = logging.getLogger("odar.audit")
_log = logging.getLogger("odar")


def _dsn():
    return get_settings().db_dsn


def audit(action: str, operator: str, target: str = "-", result: str = "OK", **details) -> str:
    audit_id = str(uuid.uuid4())
    record = {"audit_id": audit_id, "action": action, "operator": operator,
              "target": target, "result": result, "details": details}
    _audit_file.info(action, extra={"extra_data": record})
    if _dsn():
        try:
            with psycopg.connect(_dsn(), connect_timeout=3) as conn:
                conn.execute(
                    "INSERT INTO audit_log (audit_id, action, operator, target, result, details) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (audit_id, action, operator, target, result, Jsonb(details)),
                )
        except Exception as exc:
            _log.warning("audit DB write failed: %s", exc)
    return audit_id


def recent(limit: int = 20):
    limit = max(1, min(limit, 200))
    with psycopg.connect(_dsn(), connect_timeout=3, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT audit_id, ts, action, operator, target, result, details "
            "FROM audit_log ORDER BY ts DESC LIMIT %s", (limit,)
        ).fetchall()


def db_status() -> str:
    if not _dsn():
        return "not_configured"
    try:
        with psycopg.connect(_dsn(), connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return "ok"
    except Exception:
        return "down"
