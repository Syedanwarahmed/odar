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
