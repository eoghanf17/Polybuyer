"""Credentials and runtime settings, read from the environment.

Secrets are never arguments, never logged and never written to the database.
They are read once at startup from the process environment, which in practice
means a gitignored ``.env`` locally and the platform's secret store in
production.

:func:`redact` exists because the most common way a token escapes is not
theft but an exception traceback or a debug print of a request object.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env reader, so no dependency is needed for local runs."""
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    x_bearer: str = ""
    openai_key: str = ""
    gate_model: str = "gpt-4.1"
    db_path: str = "newsdesk.db"
    paper: bool = True
    max_daily_usd: float = 100.0

    @property
    def can_stream(self) -> bool:
        return bool(self.x_bearer)

    @property
    def can_gate(self) -> bool:
        return bool(self.openai_key)

    def missing(self) -> list[str]:
        out = []
        if not self.x_bearer:
            out.append("X_BEARER_TOKEN")
        if not self.openai_key:
            out.append("OPENAI_API_KEY")
        return out


def load(dotenv: str = ".env") -> Settings:
    _load_dotenv(dotenv)
    return Settings(
        x_bearer=os.environ.get("X_BEARER_TOKEN", ""),
        openai_key=os.environ.get("OPENAI_API_KEY", ""),
        gate_model=os.environ.get("OPENAI_GATE_MODEL", "gpt-4.1"),
        db_path=os.environ.get("NEWSDESK_DB", "newsdesk.db"),
        paper=os.environ.get("NEWSDESK_PAPER", "1") not in ("0", "false", "False"),
        max_daily_usd=float(os.environ.get("NEWSDESK_MAX_DAILY_USD", "100") or 100),
    )


def redact(text: str, *secrets: str) -> str:
    """Blank out secrets in anything about to be logged or displayed.

    Tokens usually leak through a traceback or a printed request object
    rather than through carelessness with the value itself, so redaction
    belongs at the point of output.
    """
    out = text
    for s in secrets:
        if s and len(s) > 8:
            out = out.replace(s, f"{s[:4]}…{s[-4:]}[REDACTED]")
    return out
