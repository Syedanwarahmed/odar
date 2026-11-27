import socket
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from odar import __version__
from odar import oracle
from odar.audit import audit, db_status, recent
from odar.config import get_settings
from odar.logging_setup import setup_logging

settings = get_settings()
setup_logging(settings.log_dir, settings.log_level)
START = time.time()
HOST = socket.gethostname()


@asynccontextmanager
async def lifespan(app: FastAPI):
    audit("SERVICE_START", operator="system", target=HOST,
          env=settings.env, read_only=settings.read_only, version=__version__)
    yield
    oracle.close_pool()
    audit("SERVICE_STOP", operator="system", target=HOST)


app = FastAPI(title="ODAR API", version=__version__, lifespan=lifespan)


def _ora(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Oracle query failed: {exc}")


@app.get("/health")
def health():
    return {
        "status": "ok", "service": "odar-api", "version": __version__,
        "host": HOST, "env": settings.env, "read_only": settings.read_only,
        "audit_db": db_status(), "uptime_s": int(time.time() - START),
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@app.get("/audit/recent")
def audit_recent(limit: int = 20):
    try:
        return recent(limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"audit DB unavailable: {exc}")


@app.get("/oracle/health")
def oracle_health():
    return _ora(oracle.health_summary)


@app.get("/oracle/instances")
def oracle_instances():
    return _ora(oracle.query, "instances")


@app.get("/oracle/database")
def oracle_database():
    return _ora(oracle.query, "database")


@app.get("/oracle/pdbs")
def oracle_pdbs():
    return _ora(oracle.query, "pdbs")


@app.get("/oracle/services")
def oracle_services():
    return _ora(oracle.query, "services")


# ---------------- Phase 5: AI diagnostics ----------------
from pydantic import BaseModel, Field  # noqa: E402

from odar.ai.diagnose import diagnose as ai_diagnose  # noqa: E402
from odar.ai.providers import get_provider  # noqa: E402


class DiagnoseRequest(BaseModel):
    text: str = Field(..., min_length=5, max_length=8000)
    operator: str = "dba"
    include_metrics: bool = True


@app.get("/ai/status")
def ai_status():
    try:
        p = get_provider()
        return {"provider": p.name, "model": p.model, "ready": True}
    except Exception as exc:
        return {"provider": settings.ai_provider, "ready": False, "detail": str(exc)}


@app.post("/ai/diagnose")
def ai_diagnose_endpoint(req: DiagnoseRequest):
    try:
        return ai_diagnose(req.text, req.operator, req.include_metrics)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"AI diagnose failed: {exc}")


# ---------------- Phase 6: controlled automation ----------------
from odar import actions  # noqa: E402


class ActionRequestIn(BaseModel):
    action: str
    params: dict = {}
    requested_by: str = Field(..., min_length=2)
    reason: str = Field(..., min_length=5)


class DecisionIn(BaseModel):
    approver: str = Field(..., min_length=2)
    comment: str = ""


class ExecuteIn(BaseModel):
    operator: str = Field(..., min_length=2)


def _act(fn, *args):
    try:
        return fn(*args)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"{type(exc).__name__}: {exc}")


@app.get("/actions/catalog")
def actions_catalog():
    return actions.CATALOG


@app.post("/actions/request")
def actions_request(req: ActionRequestIn):
    return _act(actions.request_action, req.action, req.params, req.requested_by, req.reason)


@app.get("/actions/requests")
def actions_list(status: str = None, limit: int = 50):
    return _act(actions.list_requests, status, limit)


@app.post("/actions/{request_id}/approve")
def actions_approve(request_id: int, d: DecisionIn):
    return _act(actions.decide, request_id, d.approver, True, d.comment)


@app.post("/actions/{request_id}/reject")
def actions_reject(request_id: int, d: DecisionIn):
    return _act(actions.decide, request_id, d.approver, False, d.comment)


@app.post("/actions/{request_id}/execute")
def actions_execute(request_id: int, e: ExecuteIn):
    return _act(actions.execute, request_id, e.operator)
