#!/bin/bash
# ODAR v1 smoke test: run on odar-mgmt01. Expect all PASS.
API=${API:-http://localhost:8000}
fails=0
chk(){ if eval "$2" >/dev/null 2>&1; then printf "PASS  %s\n" "$1"; else printf "FAIL  %s\n" "$1"; fails=$((fails+1)); fi; }
chk "/health  ok + read_only"      "curl -s $API/health | jq -e '.status==\"ok\" and .read_only==true and .audit_db==\"ok\"'"
chk "/audit/recent  rows"          "curl -s '$API/audit/recent?limit=5' | jq -e 'length>0'"
chk "/oracle/health  OK"           "curl -s $API/oracle/health | jq -e '.overall==\"OK\" and .instances_open==2'"
chk "/oracle/instances  2 OPEN"    "curl -s $API/oracle/instances | jq -e '[.[]|select(.status==\"OPEN\")]|length==2'"
chk "/oracle/database  READ WRITE" "curl -s $API/oracle/database | jq -e '.[0].open_mode==\"READ WRITE\"'"
chk "/oracle/pdbs  RACPDB1 RW x2"  "curl -s $API/oracle/pdbs | jq -e '[.[]|select(.name==\"RACPDB1\" and .open_mode==\"READ WRITE\")]|length==2'"
chk "/oracle/services  PDB svc"    "curl -s $API/oracle/services | jq -e '[.[]|select(.name==\"RACDB_RACPDB1\")]|length==2'"
chk "/ai/status  ready"            "curl -s $API/ai/status | jq -e '.ready==true'"
chk "/actions/catalog  4 actions"  "curl -s $API/actions/catalog | jq -e 'keys|length==4'"
chk "/actions/requests  queue"     "curl -s $API/actions/requests | jq -e 'length>=1'"
chk "exporter  oracle_up=1"        "curl -s localhost:9161/metrics | grep -q '^odar_oracle_up 1'"
chk "prometheus  targets up"       "curl -s localhost:9090/api/v1/targets | jq -e '[.data.activeTargets[]|select(.health==\"up\")]|length==2'"
chk "grafana  healthy"             "curl -s localhost:3000/api/health | jq -e '.database==\"ok\"'"
echo "----"; [ $fails -eq 0 ] && echo "ALL PASS" || echo "$fails FAILED"; exit $fails
