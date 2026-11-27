"""Controlled automation: allowlist + four-eyes approval. Nothing runs without a second person approving."""
import re

import oracledb
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from odar.audit import audit
from odar.config import get_settings

IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")

CATALOG = {
    "GATHER_TABLE_STATS": {"risk": "low", "description": "Gather optimizer stats on one table (cascade to indexes)",
                           "params": {"owner": "identifier", "table": "identifier"}},
    "GATHER_SCHEMA_STATS": {"risk": "low", "description": "Gather optimizer stats on a non-Oracle-maintained schema",
                            "params": {"owner": "identifier"}},
    "ADD_DATAFILE": {"risk": "low", "description": "Add an autoextend datafile in +DATA to a smallfile permanent tablespace",
                     "params": {"tablespace": "identifier", "size_mb": "10-1024", "maxsize_mb": "size_mb-4096"}},
    "AWR_SNAPSHOT": {"risk": "low", "description": "Create a manual AWR snapshot in the PDB", "params": {}},
}


def _ident(v, name):
    if not isinstance(v, str) or not IDENT.match(v):
        raise ValueError(f"{name} must be a simple Oracle identifier")
    return v.upper()


def _int(v, name, lo, hi):
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer")
    if not lo <= v <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return v


def validate(action, params):
    if action not in CATALOG:
        raise ValueError(f"Action '{action}' is not in the allowlist")
    p = params or {}
    if action == "GATHER_TABLE_STATS":
        return {"owner": _ident(p.get("owner"), "owner"), "table": _ident(p.get("table"), "table")}
    if action == "GATHER_SCHEMA_STATS":
        return {"owner": _ident(p.get("owner"), "owner")}
    if action == "ADD_DATAFILE":
        size = _int(p.get("size_mb"), "size_mb", 10, 1024)
        return {"tablespace": _ident(p.get("tablespace"), "tablespace"), "size_mb": size,
                "maxsize_mb": _int(p.get("maxsize_mb"), "maxsize_mb", size, 4096)}
    return {}


def _db():
    return psycopg.connect(get_settings().db_dsn, connect_timeout=3, row_factory=dict_row)


def _run_oracle(action, p):
    s = get_settings()
    with oracledb.connect(user=s.exec_user, password=s.exec_password, dsn=s.exec_dsn,
                          tcp_connect_timeout=5) as conn:
        cur = conn.cursor()
        if action == "GATHER_TABLE_STATS":
            cur.callproc("odar_ops.odar_actions.gather_table_stats", [p["owner"], p["table"]])
            return f"Stats gathered on {p['owner']}.{p['table']}"
        if action == "GATHER_SCHEMA_STATS":
            cur.callproc("odar_ops.odar_actions.gather_schema_stats", [p["owner"]])
            return f"Stats gathered on schema {p['owner']}"
        if action == "ADD_DATAFILE":
            cur.callproc("odar_ops.odar_actions.add_datafile", [p["tablespace"], p["size_mb"], p["maxsize_mb"]])
            return f"Datafile added to {p['tablespace']} ({p['size_mb']}M, max {p['maxsize_mb']}M)"
        if action == "AWR_SNAPSHOT":
            snap = cur.callfunc("odar_ops.odar_actions.awr_snapshot", int)
            return f"AWR snapshot {snap} created"
    raise ValueError(f"No executor for {action}")


def request_action(action, params, requested_by, reason, source="manual"):
    p = validate(action, params)
    with _db() as c:
        row = c.execute(
            "INSERT INTO action_requests (action, params, reason, source, requested_by) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (action, Jsonb(p), reason, source, requested_by)).fetchone()
    audit("ACTION_REQUESTED", operator=requested_by, target=action,
          request_id=row["request_id"], params=p, reason=reason)
    return row


def list_requests(status=None, limit=50):
    limit = max(1, min(limit, 200))
    with _db() as c:
        if status:
            return c.execute("SELECT * FROM action_requests WHERE status = %s ORDER BY request_id DESC LIMIT %s",
                             (status.upper(), limit)).fetchall()
        return c.execute("SELECT * FROM action_requests ORDER BY request_id DESC LIMIT %s", (limit,)).fetchall()


def decide(request_id, approver, approve, comment=""):
    with _db() as c:
        row = c.execute("SELECT * FROM action_requests WHERE request_id = %s", (request_id,)).fetchone()
        if not row:
            raise LookupError("request not found")
        if row["status"] != "PENDING":
            raise ValueError(f"request is {row['status']}, not PENDING")
        if approver.lower() == row["requested_by"].lower() and not get_settings().allow_self_approval:
            raise PermissionError("four-eyes rule: the requester cannot approve or reject their own request")
        new = "APPROVED" if approve else "REJECTED"
        row = c.execute(
            "UPDATE action_requests SET status = %s, decided_by = %s, decided_at = now(), decision_comment = %s "
            "WHERE request_id = %s AND status = 'PENDING' RETURNING *",
            (new, approver, comment, request_id)).fetchone()
        if not row:
            raise ValueError("request changed state concurrently")
    audit(f"ACTION_{new}", operator=approver, target=row["action"], request_id=request_id, comment=comment)
    return row


def execute(request_id, operator):
    if get_settings().read_only:
        raise PermissionError("ODAR is in read-only mode (ODAR_READ_ONLY=true): execution disabled")
    with _db() as c:
        row = c.execute(
            "UPDATE action_requests SET status = 'EXECUTING', executed_by = %s, executed_at = now() "
            "WHERE request_id = %s AND status = 'APPROVED' AND decided_at > now() - interval '60 minutes' "
            "RETURNING *", (operator, request_id)).fetchone()
        if not row:
            cur = c.execute("SELECT status FROM action_requests WHERE request_id = %s", (request_id,)).fetchone()
            if not cur:
                raise LookupError("request not found")
            raise ValueError(f"not executable: status is {cur['status']} (approvals expire after 60 minutes)")
    audit("ACTION_EXECUTE_START", operator=operator, target=row["action"], request_id=request_id)
    try:
        outcome = _run_oracle(row["action"], row["params"])
        status = "EXECUTED"
    except Exception as exc:
        outcome = f"{type(exc).__name__}: {exc}"[:1000]
        status = "FAILED"
    with _db() as c:
        row = c.execute("UPDATE action_requests SET status = %s, result = %s WHERE request_id = %s RETURNING *",
                        (status, outcome, request_id)).fetchone()
    audit(f"ACTION_{status}", operator=operator, target=row["action"],
          result="OK" if status == "EXECUTED" else "ERROR", request_id=request_id, outcome=outcome)
    return row
