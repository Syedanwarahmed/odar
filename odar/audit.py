"""Audit trail: every action records what, who, target and result."""
import logging
import uuid

_log = logging.getLogger("odar.audit")


def audit(action: str, operator: str, target: str = "-", result: str = "OK", **details) -> str:
    audit_id = str(uuid.uuid4())
    record = {
        "audit_id": audit_id,
        "action": action,
        "operator": operator,
        "target": target,
        "result": result,
        "details": details,
    }
    _log.info(action, extra={"extra_data": record})
    return audit_id
