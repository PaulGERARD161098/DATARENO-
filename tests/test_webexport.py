"""Tests — export web agrégé (schéma + garantie zéro PII)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src import db
from src import webexport


def _seed(tmp_path: Path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    conn.execute(
        "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
        "VALUES ('jean.dupont@gmail.com', 'AIR_EAU', 'rdv', ?, ?)", (now, now),
    )
    conn.execute(
        "INSERT INTO messages (contact_id, position, subject, status, created_at) "
        "VALUES (1, 'J0', 'On reprend votre projet ?', 'sent', ?)", (now,),
    )
    conn.execute("INSERT INTO events (contact_id, type, created_at) VALUES (1,'sent',?)", (now,))
    conn.execute("INSERT INTO events (contact_id, type, created_at) VALUES (1,'rdv',?)", (now,))
    conn.execute("INSERT INTO suppressions (email, reason, created_at) VALUES ('x@b.fr','stop',?)", (now,))
    conn.commit()
    return conn


def test_payload_schema(tmp_path: Path):
    conn = _seed(tmp_path)
    p = webexport.build_payload(conn, on_date=date(2026, 1, 1))
    assert set(p) >= {"generated_at", "funnel", "kpis", "engagement_tiers",
                      "hot_leads_count", "ab_subjects", "segments", "message_status",
                      "suppressions", "due_today"}
    assert p["funnel"]["rdv"] == 1
    assert p["suppressions"] == 1
    assert [t["tier"] for t in p["engagement_tiers"]][-1] == "RDV"
    conn.close()


def test_payload_sans_pii(tmp_path: Path):
    """Garantie : aucun email (ni domaine de contact) dans l'export agrégé."""
    conn = _seed(tmp_path)
    blob = json.dumps(webexport.build_payload(conn))
    assert "@" not in blob
    assert "jean.dupont" not in blob
    conn.close()


def test_write_json_cree_le_fichier(tmp_path: Path):
    conn = _seed(tmp_path)
    out = tmp_path / "web" / "data.json"
    n = webexport.write_json(conn, out)
    assert out.exists() and n > 0
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert "funnel" in loaded
    conn.close()
