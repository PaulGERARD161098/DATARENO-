"""Tests — orchestrateur quotidien (ingestion des retours puis envoi du dû)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from src import daily
from src import db
from src import inbox


D = date(2026, 1, 10)


def _seed(tmp_path: Path, emails: list[str]):
    """Contacts avec une touche J0 scheduled aujourd'hui."""
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    for e in emails:
        conn.execute(
            "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
            "VALUES (?, 'AIR_EAU', 'new', ?, ?)", (e, now, now),
        )
        cid = conn.execute("SELECT id FROM contacts WHERE email=?", (e,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO messages (contact_id, position, subject, body, status, scheduled_at, created_at) "
            "VALUES (?, 'J0', 'O', 'Corps', 'scheduled', '2026-01-10', ?)", (cid, now),
        )
    conn.commit()
    return conn


def test_run_daily_dry_run_sans_poll(tmp_path: Path):
    conn = _seed(tmp_path, ["a@b.fr", "c@b.fr"])
    s = daily.run_daily(conn, on_date=D)  # pas de transport, pas d'IMAP
    assert s["inbox"] is None
    assert s["send"]["dry_run"] == 1
    assert s["send"]["would_send"] == 2
    conn.close()


def test_run_daily_ingere_avant_d_envoyer(tmp_path: Path):
    """Un STOP relevé par le poll annule la touche du jour AVANT l'envoi."""
    conn = _seed(tmp_path, ["a@b.fr", "stop@b.fr"])
    cfg = inbox.ImapConfig(host="imap.dom.fr", user="u", password="p")
    # Le contact stop@b.fr répond « désabonnez-moi » → séquence annulée.
    messages = [("stop@b.fr", "Re:", "merci de me desabonner, stop")]
    sent: list[str] = []
    s = daily.run_daily(
        conn, on_date=D,
        transport=lambda e, su, b: sent.append(e) or True, confirm=True,
        imap_cfg=cfg, imap_fetcher=lambda _c: iter(messages),
    )
    assert s["inbox"]["replies"] == 1
    # Seul a@b.fr est envoyé ; stop@b.fr a été annulé par l'ingestion.
    assert s["send"]["sent"] == 1
    assert sent == ["a@b.fr"]
    conn.close()


def test_run_daily_envoi_reel(tmp_path: Path):
    conn = _seed(tmp_path, ["a@b.fr"])
    sent: list[str] = []
    s = daily.run_daily(
        conn, on_date=D, transport=lambda e, su, b: sent.append(e) or True, confirm=True,
    )
    assert s["send"]["sent"] == 1
    assert sent == ["a@b.fr"]
    conn.close()
