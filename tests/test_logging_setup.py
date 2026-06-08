"""Tests RGPD — redact() et masquage PII dans les logs."""
from __future__ import annotations

import json
import logging

from src.logging_setup import get_logger, redact


def test_redact_masque_par_defaut():
    assert redact("jean@exemple.fr") == "***"
    assert redact("") == ""


def test_redact_garde_tete():
    assert redact("0601020304", keep=2) == "06***"


def test_logger_masque_pii(capsys):
    logger = get_logger("datareno.test_pii")
    logger.info("évènement", extra={"context": {"email": "a@b.fr", "count": 3}})
    err = capsys.readouterr().err.strip().splitlines()[-1]
    payload = json.loads(err)
    assert payload["context"]["email"] == "***"
    assert payload["context"]["count"] == 3


def test_logger_idempotent():
    logger = get_logger("datareno.unique")
    n = len(logger.handlers)
    logger = get_logger("datareno.unique")
    assert len(logger.handlers) == n
    assert logger.level == logging.INFO
