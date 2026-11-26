"""ODAR Prometheus exporter: read-only Oracle metrics on :9161/metrics."""
import logging
import time

from prometheus_client import start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily
from prometheus_client.registry import Collector

from odar import oracle

log = logging.getLogger("odar.exporter")


def _safe(name):
    try:
        return oracle.query(name)
    except Exception as exc:
        log.warning("query %s failed: %s", name, exc)
        return None


class OracleCollector(Collector):
    def collect(self):
        t0 = time.time()
        up = GaugeMetricFamily("odar_oracle_up", "1 if ODAR can query the database")
        inst = _safe("instances")
        up.add_metric([], 1 if inst is not None else 0)
        yield up
        if inst is None:
            return
        names = {i["inst_id"]: i["instance_name"] for i in inst}

        g = GaugeMetricFamily("odar_instance_up", "1 if instance status is OPEN",
                              labels=["db_instance", "host"])
        for i in inst:
            g.add_metric([i["instance_name"], i["host_name"]], 1 if i["status"] == "OPEN" else 0)
        yield g

        pdbs = _safe("pdbs") or []
        g = GaugeMetricFamily("odar_pdb_open_rw", "1 if PDB is READ WRITE on the instance",
                              labels=["pdb", "db_instance"])
        for p in pdbs:
            if p["name"] != "PDB$SEED":
                g.add_metric([p["name"], names.get(p["inst_id"], str(p["inst_id"]))],
                             1 if p["open_mode"] == "READ WRITE" else 0)
        yield g

        sess = _safe("sessions") or []
        g1 = GaugeMetricFamily("odar_sessions_user", "User sessions", labels=["db_instance"])
        g2 = GaugeMetricFamily("odar_sessions_active_user", "Active user sessions", labels=["db_instance"])
        g3 = GaugeMetricFamily("odar_sessions_blocked", "Sessions waiting on a blocker", labels=["db_instance"])
        for s in sess:
            n = names.get(s["inst_id"], str(s["inst_id"]))
            g1.add_metric([n], s["user_sessions"] or 0)
            g2.add_metric([n], s["active_user"] or 0)
            g3.add_metric([n], s["blocked"] or 0)
        yield g1
        yield g2
        yield g3

        ts = _safe("tablespaces") or []
        g = GaugeMetricFamily("odar_tablespace_used_pct", "Tablespace used % of max size",
                              labels=["container", "tablespace"])
        for t in ts:
            g.add_metric([t["container"], t["tablespace_name"]], float(t["used_pct"] or 0))
        yield g

        fra = _safe("fra") or []
        g1 = GaugeMetricFamily("odar_fra_used_pct", "FRA used % of limit")
        g2 = GaugeMetricFamily("odar_fra_reclaimable_pct", "FRA reclaimable % of limit")
        for f in fra:
            if f["space_limit"]:
                g1.add_metric([], 100.0 * f["space_used"] / f["space_limit"])
                g2.add_metric([], 100.0 * f["space_reclaimable"] / f["space_limit"])
        yield g1
        yield g2

        asm = _safe("asm") or []
        g1 = GaugeMetricFamily("odar_asm_dg_used_pct", "ASM disk group used %", labels=["diskgroup"])
        g2 = GaugeMetricFamily("odar_asm_dg_free_mb", "ASM disk group free MB", labels=["diskgroup"])
        for a in asm:
            if a["total_mb"]:
                g1.add_metric([a["name"]], 100.0 * (a["total_mb"] - a["free_mb"]) / a["total_mb"])
                g2.add_metric([a["name"]], a["free_mb"])
        yield g1
        yield g2

        d = GaugeMetricFamily("odar_scrape_duration_seconds", "Time taken to collect Oracle metrics")
        d.add_metric([], time.time() - t0)
        yield d


def main():
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    REGISTRY.register(OracleCollector())
    start_http_server(9161, addr="0.0.0.0")
    log.info("odar-exporter listening on :9161")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
