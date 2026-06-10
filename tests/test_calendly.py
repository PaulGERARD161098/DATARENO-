"""Tests — ingestion des RDV Calendly (ferme le funnel), sans réseau."""
from __future__ import annotations

from pathlib import Path

from src import calendly
from src import db


def _seed(tmp_path: Path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    conn.execute(
        "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
        "VALUES ('c0@b.fr', 'AIR_EAU', 'contacted', ?, ?)", (now, now),
    )
    conn.execute(
        "INSERT INTO messages (contact_id, position, subject, body, status, scheduled_at, created_at) "
        "VALUES (1, 'J4', 'O', 'C', 'scheduled', '2026-01-20', ?)", (now,),
    )
    conn.commit()
    return conn


def test_ingest_booking_pose_rdv_et_annule_relances(tmp_path: Path):
    conn = _seed(tmp_path)
    s = calendly.ingest_bookings(conn, [("c0@b.fr", "2026-01-15T10:00:00Z")])
    assert s["matched"] == 1
    assert conn.execute("SELECT status FROM contacts WHERE id=1").fetchone()["status"] == "rdv"
    # Relance restante annulée (le prospect a booké).
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE status='scheduled'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type='rdv'").fetchone()[0] == 1
    conn.close()


def test_ingest_booking_idempotent(tmp_path: Path):
    conn = _seed(tmp_path)
    calendly.ingest_bookings(conn, [("c0@b.fr", "2026-01-15T10:00:00Z")])
    s = calendly.ingest_bookings(conn, [("c0@b.fr", "2026-01-15T10:00:00Z")])
    assert s["already"] == 1 and s["matched"] == 0
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type='rdv'").fetchone()[0] == 1
    conn.close()


def test_ingest_booking_contact_inconnu(tmp_path: Path):
    conn = _seed(tmp_path)
    s = calendly.ingest_bookings(conn, [("inconnu@x.fr", "2026-01-15T10:00:00Z")])
    assert s["unknown"] == 1 and s["matched"] == 0
    conn.close()


def test_poll_via_fetcher_injecte(tmp_path: Path):
    conn = _seed(tmp_path)
    cfg = calendly.CalendlyConfig(token="t")
    s = calendly.poll_calendly(
        conn, cfg, fetcher=lambda _c, _since: iter([("c0@b.fr", "2026-01-15T10:00:00Z")])
    )
    assert s["matched"] == 1
    conn.close()


def test_config_missing():
    assert calendly.CalendlyConfig(token="").missing() == ["CALENDLY_TOKEN"]
    assert calendly.CalendlyConfig(token="x").missing() == []
