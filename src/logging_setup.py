"""logging_setup — logger JSON multi-niveaux + redact() PII (RGPD).

Aucune PII (email / tel / nom) ne doit transiter par les logs. `redact()`
masque les valeurs sensibles ; le logger n'émet que des agrégats/raisons.
"""
from __future__ import annotations

import json
import logging
import sys

# Clés considérées comme PII : masquées si elles apparaissent dans les `extra`.
PII_KEYS = {"email", "mail", "tel", "telephone", "phone", "nom", "name", "prenom"}


def redact(value: str | None, keep: int = 0) -> str:
    """Masque une valeur sensible. `keep` = nb de caractères de tête conservés."""
    if not value:
        return ""
    text = str(value)
    if keep <= 0 or keep >= len(text):
        return "***"
    return text[:keep] + "***"


class _JsonFormatter(logging.Formatter):
    """Formatte chaque enregistrement en une ligne JSON, en masquant la PII."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload["context"] = {
                k: (redact(v) if k.lower() in PII_KEYS else v) for k, v in extra.items()
            }
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str = "datareno", level: int = logging.INFO) -> logging.Logger:
    """Retourne un logger JSON idempotent (un seul handler sur stderr)."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    return logger
