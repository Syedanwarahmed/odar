"""Mask sensitive details before any text leaves ODAR for a cloud AI service."""
import re

SECRET_RX = re.compile(
    r"(?i)\b(identified\s+by|password\s*[=:]|pwd\s*[=:]|api[_-]?key\s*[=:])\s*(\"[^\"]*\"|'[^']*'|\S+)")
RULES = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("HOST", re.compile(
        r"\b(?=[a-z0-9-]*[a-z])[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:local|lan|internal|corp|com|net|org|in|io)\b",
        re.I)),
    ("LITERAL", re.compile(r"'[^']{3,}'")),
]
HOME_RX = re.compile(r"(/home/)([^/\s]+)")


class Sanitizer:
    def __init__(self):
        self.mapping = {}
        self.counts = {}

    def _token(self, kind, value):
        key = (kind, value)
        if key not in self.mapping:
            n = sum(1 for k in self.mapping if k[0] == kind) + 1
            self.mapping[key] = f"<{kind}_{n}>"
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return self.mapping[key]

    def clean(self, text: str) -> str:
        text = SECRET_RX.sub(lambda m: f"{m.group(1)} {self._token('SECRET', m.group(2))}", text)
        for kind, rx in RULES:
            text = rx.sub(lambda m, k=kind: self._token(k, m.group(0)), text)
        text = HOME_RX.sub(lambda m: m.group(1) + self._token("OSUSER", m.group(2)), text)
        return text


def sanitize(text: str):
    """Return (sanitized_text, {kind: count})."""
    s = Sanitizer()
    return s.clean(text or ""), s.counts
