"""Provider-independent AI layer. Every provider takes (system, user) text and returns text."""
import json

import httpx

from odar.config import get_settings


class MockProvider:
    name = "mock"
    model = "mock-v1"

    def complete(self, system: str, user: str) -> str:
        text = user.upper()
        if "ORA-01653" in text or "ORA-01654" in text or "ORA-01688" in text:
            d = {
                "summary": "A segment could not allocate a new extent: the tablespace is full or cannot autoextend.",
                "probable_causes": [
                    {"cause": "Datafiles reached MAXSIZE or autoextend is off", "likelihood": "high",
                     "evidence": "ORA-0165x reports failure to extend in a named tablespace"},
                    {"cause": "ASM disk group has no free space for datafile growth", "likelihood": "medium",
                     "evidence": "Check DATA disk group free MB in the metrics"}],
                "checks": [
                    {"description": "Tablespace usage vs max size",
                     "command": "SELECT tablespace_name, ROUND(used_percent,2) FROM dba_tablespace_usage_metrics ORDER BY 2 DESC;"},
                    {"description": "Datafile autoextend settings",
                     "command": "SELECT file_name, autoextensible, ROUND(maxbytes/1024/1024) max_mb FROM dba_data_files WHERE tablespace_name = '<TABLESPACE>';"}],
                "recommended_actions": [
                    {"action": "Add a datafile or raise MAXSIZE on the affected tablespace", "risk": "low"},
                    {"action": "Purge or archive old data if growth is unexpected", "risk": "medium"}],
                "confidence": "medium"}
        elif "ORA-00257" in text or "ORA-16038" in text:
            d = {
                "summary": "Archiver is stuck: the archive destination / FRA is full.",
                "probable_causes": [
                    {"cause": "FRA reached DB_RECOVERY_FILE_DEST_SIZE", "likelihood": "high",
                     "evidence": "ORA-00257 archiver error"},
                    {"cause": "Archive log backups/deletion policy not running", "likelihood": "medium",
                     "evidence": "Low reclaimable % in FRA metrics"}],
                "checks": [
                    {"description": "FRA usage", "command": "SELECT * FROM v$recovery_area_usage;"},
                    {"description": "Last archivelog backup",
                     "command": "RMAN> LIST BACKUP OF ARCHIVELOG ALL COMPLETED AFTER 'SYSDATE-1';"}],
                "recommended_actions": [
                    {"action": "Back up and delete archived logs per retention policy", "risk": "medium"},
                    {"action": "Temporarily increase DB_RECOVERY_FILE_DEST_SIZE if ASM has space", "risk": "low"}],
                "confidence": "medium"}
        else:
            d = {
                "summary": "Mock diagnosis: no specific rule matched this input.",
                "probable_causes": [{"cause": "Insufficient information", "likelihood": "low",
                                     "evidence": "Provide the full ORA error and alert log lines"}],
                "checks": [{"description": "Recent alert log errors",
                            "command": "adrci> show alert -p \"message_text like '%ORA-%'\" -tail 50"}],
                "recommended_actions": [{"action": "Collect more evidence before acting", "risk": "low"}],
                "confidence": "low"}
        return json.dumps(d)


class ClaudeProvider:
    name = "claude"

    def __init__(self):
        s = get_settings()
        if not s.ai_api_key:
            raise RuntimeError("ODAR_AI_API_KEY is not set")
        self.key = s.ai_api_key
        self.model = s.ai_model
        self.max_tokens = s.ai_max_tokens

    def complete(self, system: str, user: str) -> str:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": self.model, "max_tokens": self.max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


PROVIDERS = {"mock": MockProvider, "claude": ClaudeProvider}


def get_provider():
    name = (get_settings().ai_provider or "mock").lower()
    if name not in PROVIDERS:
        raise RuntimeError(f"Unknown AI provider '{name}'. Options: {', '.join(PROVIDERS)}")
    return PROVIDERS[name]()
