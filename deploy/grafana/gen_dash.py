import json
DS = {"type": "prometheus", "uid": "odar-prom"}
panels = []
def p(ptype, title, x, y, w, h, targets, unit=None, steps=None, extra=None):
    fc = {"defaults": {}, "overrides": []}
    if unit: fc["defaults"]["unit"] = unit
    if steps:
        fc["defaults"]["thresholds"] = {"mode": "absolute", "steps": steps}
        fc["defaults"]["color"] = {"mode": "thresholds"}
    panel = {"id": len(panels) + 1, "type": ptype, "title": title, "datasource": DS,
             "gridPos": {"x": x, "y": y, "w": w, "h": h}, "fieldConfig": fc,
             "targets": [dict(datasource=DS, refId=chr(65 + i), **t) for i, t in enumerate(targets)]}
    if extra: panel.update(extra)
    panels.append(panel)
G = {"color": "green", "value": None}
UPDOWN = [{"color": "red", "value": None}, {"color": "green", "value": 1}]
PCT = [G, {"color": "orange", "value": 80}, {"color": "red", "value": 90}]
p("stat", "Oracle reachable", 0, 0, 4, 4, [{"expr": "odar_oracle_up"}], steps=UPDOWN,
  extra={"options": {"colorMode": "background", "graphMode": "none"}})
p("stat", "Instances OPEN", 4, 0, 4, 4, [{"expr": "sum(odar_instance_up)"}],
  steps=[{"color": "red", "value": None}, {"color": "orange", "value": 1}, {"color": "green", "value": 2}],
  extra={"options": {"colorMode": "background", "graphMode": "none"}})
p("stat", "Instance status", 8, 0, 8, 4, [{"expr": "odar_instance_up", "legendFormat": "{{db_instance}}"}],
  steps=UPDOWN, extra={"options": {"colorMode": "background", "graphMode": "none", "textMode": "name"}})
p("stat", "Blocked sessions", 16, 0, 4, 4, [{"expr": "sum(odar_sessions_blocked)"}],
  steps=[G, {"color": "orange", "value": 1}, {"color": "red", "value": 5}],
  extra={"options": {"colorMode": "background", "graphMode": "none"}})
p("gauge", "FRA used %", 20, 0, 4, 4, [{"expr": "odar_fra_used_pct"}], unit="percent", steps=PCT,
  extra={"fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100,
         "thresholds": {"mode": "absolute", "steps": PCT}}, "overrides": []}})
p("timeseries", "User sessions per instance", 0, 4, 12, 8,
  [{"expr": "odar_sessions_user", "legendFormat": "{{db_instance}} total"},
   {"expr": "odar_sessions_active_user", "legendFormat": "{{db_instance}} active"}])
p("bargauge", "ASM disk group used %", 12, 4, 12, 8,
  [{"expr": "odar_asm_dg_used_pct", "legendFormat": "{{diskgroup}}"}], unit="percent", steps=PCT,
  extra={"options": {"orientation": "horizontal", "displayMode": "gradient"},
         "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100,
         "thresholds": {"mode": "absolute", "steps": PCT}}, "overrides": []}})
p("bargauge", "Tablespace used % (of max size)", 0, 12, 24, 10,
  [{"expr": "sort_desc(odar_tablespace_used_pct)", "legendFormat": "{{container}} / {{tablespace}}", "instant": True}],
  unit="percent", steps=PCT,
  extra={"options": {"orientation": "horizontal", "displayMode": "gradient"},
         "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100,
         "thresholds": {"mode": "absolute", "steps": PCT}}, "overrides": []}})
p("timeseries", "Exporter scrape duration", 0, 22, 24, 6,
  [{"expr": "odar_scrape_duration_seconds", "legendFormat": "seconds"}], unit="s")
dash = {"uid": "odar-rac-health", "title": "ODAR - RAC Health", "tags": ["odar", "oracle", "rac"],
        "timezone": "browser", "refresh": "30s", "schemaVersion": 39,
        "time": {"from": "now-1h", "to": "now"}, "panels": panels}
print(json.dumps(dash, indent=1))
