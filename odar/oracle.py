"""Read-only Oracle access via python-oracledb Thin mode (no client install)."""
import threading

import oracledb

from odar.config import get_settings

_pool = None
_lock = threading.Lock()

SQL = {
    "instances": """
        SELECT inst_id, instance_name, host_name, status, database_status,
               TO_CHAR(startup_time,'YYYY-MM-DD HH24:MI:SS') startup_time, version_full
        FROM gv$instance ORDER BY inst_id""",
    "database": """
        SELECT name, db_unique_name, database_role, open_mode, log_mode, cdb, protection_mode
        FROM v$database""",
    "pdbs": """
        SELECT inst_id, con_id, name, open_mode, NVL(restricted,'N/A') restricted
        FROM gv$pdbs ORDER BY con_id, inst_id""",
    "services": """
        SELECT inst_id, name, NVL(network_name,'N/A') network_name, con_id
        FROM gv$active_services WHERE name NOT LIKE 'SYS$%' ORDER BY name, inst_id""",
    "sessions": """
        SELECT inst_id, COUNT(*) total,
               SUM(CASE WHEN type='USER' THEN 1 ELSE 0 END) user_sessions,
               SUM(CASE WHEN type='USER' AND status='ACTIVE' THEN 1 ELSE 0 END) active_user
        FROM gv$session GROUP BY inst_id ORDER BY inst_id""",
}


def get_pool():
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                s = get_settings()
                _pool = oracledb.create_pool(
                    user=s.ora_user, password=s.ora_password, dsn=s.ora_dsn,
                    min=1, max=4, increment=1, tcp_connect_timeout=5,
                    getmode=oracledb.POOL_GETMODE_TIMEDWAIT, wait_timeout=5000,
                )
    return _pool


def close_pool():
    if _pool is not None:
        _pool.close(force=True)


def query(name: str):
    with get_pool().acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL[name])
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def health_summary():
    inst = query("instances")
    db = query("database")[0]
    pdbs = [p for p in query("pdbs") if p["name"] != "PDB$SEED"]
    sess = query("sessions")
    issues = []
    for i in inst:
        if i["status"] != "OPEN":
            issues.append(f"instance {i['instance_name']} status {i['status']}")
    for p in pdbs:
        if p["open_mode"] != "READ WRITE":
            issues.append(f"PDB {p['name']} on inst {p['inst_id']} is {p['open_mode']}")
    return {
        "overall": "OK" if not issues else "DEGRADED",
        "issues": issues,
        "database": db,
        "instances_open": sum(1 for i in inst if i["status"] == "OPEN"),
        "instances_total": len(inst),
        "pdbs": pdbs,
        "sessions": sess,
    }
