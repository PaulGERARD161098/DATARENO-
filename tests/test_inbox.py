"""Tests — ingestion des retours par IMAP (classification + effets, sans réseau)."""
from __future__ import annotations

from pathlib import Path

from src import db
from src import inbox
from src import replies


def _seed(tmp_path: Path):
    """Un contact c0@b.fr (id 1) avec 3 touches scheduled."""
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    conn.execute(
        "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
        "VALUES ('c0@b.fr', 'AIR_EAU', 'new', ?, ?)", (now, now),
    )
    for pos in ("J0", "J4", "J8"):
        conn.execute(
            "INSERT INTO messages (contact_id, position, subject, body, status, scheduled_at, created_at) "
            "VALUES (1, ?, 'O', 'C', 'scheduled', '2026-01-10', ?)", (pos, now),
        )
    conn.commit()
    return conn


def test_classify_bounce_par_daemon():
    kind, _ = inbox.classify_inbound("MAILER-DAEMON@b.fr", "Undeliverable", "...")
    assert kind == "bounce"


def test_classify_reply_interesse():
    kind, label = inbox.classify_inbound("c0@b.fr", "Re: votre projet", "Oui je suis intéressé")
    assert kind == "reply"
    assert label == replies.INTERESSE


def test_ingest_reply_stoppe_la_sequence_sans_blacklist(tmp_path: Path):
    conn = _seed(tmp_path)
    r = inbox.ingest_inbound(conn, "c0@b.fr", "Re:", "Oui, ça m'intéresse")
    assert r["ok"] is True and r["kind"] == "reply"
    assert r["proposed"] == replies.INTERESSE
    assert r["applied"] is False  # l'action finale reste validée par un humain
    # Séquence stoppée : plus aucune touche scheduled.
    n = conn.execute("SELECT COUNT(*) FROM messages WHERE status='scheduled'").fetchone()[0]
    assert n == 0
    # Pas de blacklist automatique sur une simple réponse.
    assert not replies.is_suppressed(conn, "c0@b.fr")
    # La réponse est journalisée avec la classe proposée.
    ev = conn.execute("SELECT type, payload FROM events WHERE type='reply'").fetchone()
    assert ev["payload"] == replies.INTERESSE
    conn.close()


def test_ingest_bounce_supprime_le_destinataire_du_corps(tmp_path: Path):
    conn = _seed(tmp_path)
    body = "Mail delivery failed.\nFinal-Recipient: rfc822; c0@b.fr\nAddress not found"
    r = inbox.ingest_inbound(conn, "mailer-daemon@esp.fr", "Delivery Status Notification", body)
    assert r["ok"] is True and r["kind"] == "bounce"
    assert replies.is_suppressed(conn, "c0@b.fr")
    assert conn.execute("SELECT status FROM contacts WHERE id=1").fetchone()["status"] == "bounced"
    conn.close()


def test_ingest_bounce_destinataire_inconnu(tmp_path: Path):
    conn = _seed(tmp_path)
    r = inbox.ingest_inbound(conn, "mailer-daemon@esp.fr", "DSN", "echec pour inconnu@x.fr")
    assert r["ok"] is False
    assert r["reason"] == "destinataire_introuvable"
    conn.close()


def test_ingest_reply_expediteur_inconnu(tmp_path: Path):
    conn = _seed(tmp_path)
    r = inbox.ingest_inbound(conn, "inconnu@x.fr", "Bonjour", "une question")
    assert r["ok"] is False and r["reason"] == "contact_inconnu"
    conn.close()


def test_poll_inbox_via_fetcher_injecte(tmp_path: Path):
    conn = _seed(tmp_path)
    messages = [
        ("c0@b.fr", "Re:", "intéressé"),
        ("mailer-daemon@esp.fr", "DSN", "Address not found: c0@b.fr"),
        ("inconnu@x.fr", "?", "?"),
    ]
    cfg = inbox.ImapConfig(host="imap.dom.fr", user="u", password="p")
    s = inbox.poll_inbox(conn, cfg, fetcher=lambda _cfg: iter(messages))
    assert s["seen"] == 3
    assert s["replies"] == 1
    assert s["bounces"] == 1
    assert s["unknown"] == 1
    conn.close()


def test_imap_config_missing():
    cfg = inbox.ImapConfig(host="", user="u", password="")
    missing = cfg.missing()
    assert "IMAP_HOST" in missing and "IMAP_PASSWORD" in missing
    assert "IMAP_USER" not in missing
