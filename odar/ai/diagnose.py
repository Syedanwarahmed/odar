"""Diagnostic flow: sanitize -> add live metrics -> ask AI -> validate -> enforce approval -> audit."""
import json
import re

from odar import oracle
from odar.ai.providers import get_provider
from odar.audit import audit
from odar.sanitizer import sanitize

SYSTEM_PROMPT = """You are a senior Oracle DBA assistant for an Oracle RAC environment.
You analyse errors and metrics and propose a diagnosis. You never execute anything.
Rules:
- Base every cause on the evidence given; say when evidence is missing.
- Checks must be read-only (SELECT queries, srvctl/crsctl status, adrci show, RMAN LIST/REPORT).
- Any state-changing step goes in recommended_actions, never in checks.
- Placeholders like <HOST_1> are masked values; keep them as-is.
Reply with ONLY a JSON object, no prose, with exactly these keys:
{"summary": str,
 "probable_causes": [{"cause": str, "likelihood": "high|medium|low", "evidence": str}],
 "checks": [{"description": str, "command": str}],
 "recommended_actions": [{"action": str, "risk": "low|medium|high"}],
 "confidence": "high|medium|low"}"""


def _metrics_context():
    try:
        h = oracle.health_summary()
    except Exception as exc:
        return {"metrics_error": str(exc)[:200]}
    ctx = {
        "overall": h["overall"],
        "issues": h["issues"],
        "instances_open": f'{h["instances_open"]}/{h["instances_total"]}',
        "database_role": h["database"].get("database_role"),
        "open_mode": h["database"].get("open_mode"),
        "pdbs": [f'{p["name"]}@inst{p["inst_id"]}:{p["open_mode"]}' for p in h["pdbs"]],
        "sessions": h["sessions"],
    }
    for name in ("tablespaces", "fra", "asm"):
        try:
            rows = oracle.query(name)
            if name == "tablespaces":
                rows = sorted(rows, key=lambda r: -(r["used_pct"] or 0))[:8]
            ctx[name] = rows
        except Exception:
            pass
    return ctx


def _parse(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in AI response")
    return json.loads(m.group(0))


def diagnose(user_text: str, operator: str, include_metrics: bool = True):
    clean_text, redactions = sanitize(user_text)
    payload = {"problem": clean_text}
    if include_metrics:
        metrics = json.dumps(_metrics_context(), default=str)
        payload["live_metrics"], more = sanitize(metrics)
        for k, v in more.items():
            redactions[k] = redactions.get(k, 0) + v
    prompt = json.dumps(payload, indent=1)

    provider = get_provider()
    try:
        raw = provider.complete(SYSTEM_PROMPT, prompt)
        result = _parse(raw)
        status = "OK"
    except Exception as exc:
        result = {"error": f"AI call or parse failed: {exc}"}
        status = "ERROR"

    # Safety net: whatever the AI says, every action needs a human.
    for a in result.get("recommended_actions", []) or []:
        a["requires_approval"] = True
        a["executed"] = False

    audit_id = audit("AI_DIAGNOSE", operator=operator, target="RACDB", result=status,
                     provider=provider.name, model=provider.model,
                     input_sanitized=clean_text[:2000], redactions=redactions,
                     summary=result.get("summary", result.get("error", ""))[:500])
    return {"audit_id": audit_id, "provider": provider.name, "model": provider.model,
            "sanitized_input": clean_text, "redactions": redactions,
            "sent_to_ai": prompt if provider.name != "mock" else "(mock: nothing left the VM)",
            "diagnosis": result}
