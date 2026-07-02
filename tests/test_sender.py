"""Tests Phase 8 — connecteur d'envoi (dry-run, plafond, suppression, ingestion)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from src import db
from src import replies
from src import sender


D = date(2026, 1, 10)


def _seed(tmp_path: Path, n: int, scheduled_at: str = "2026-01-10"):
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    for i in range(n):
        conn.execute(
            "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
            "VALUES (?, 'AIR_EAU', 'new', ?, ?)", (f"c{i}@b.fr", now, now),
        )
        cid = conn.execute("SELECT id FROM contacts WHERE email=?", (f"c{i}@b.fr",)).fetchone()["id"]
        conn.execute(
            "INSERT INTO messages (contact_id, position, subject, body, status, scheduled_at, created_at) "
            "VALUES (?, 'J0', 'Objet', 'Corps', 'scheduled', ?, ?)", (cid, scheduled_at, now),
        )
    conn.commit()
    return conn


def test_dry_run_n_envoie_rien(tmp_path: Path):
    conn = _seed(tmp_path, 3)
    r = sender.send_due(conn, D, caps=(10, 10, 10))  # pas de transport, pas de confirm
    assert r["dry_run"] == 1
    assert r["would_send"] == 3
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE status='sent'").fetchone()[0] == 0
    conn.close()


def test_envoi_reel_avec_transport(tmp_path: Path):
    conn = _seed(tmp_path, 2)
    sent = []
    r = sender.send_due(
        conn, D, transport=lambda e, s, b: sent.append(e) or True,
        confirm=True, caps=(10, 10, 10),
    )
    assert r["sent"] == 2
    assert len(sent) == 2
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type='sent'").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE status='sent'").fetchone()[0] == 2
    conn.close()


def test_plafond_respecte(tmp_path: Path):
    conn = _seed(tmp_path, 5)
    r = sender.send_due(
        conn, D, transport=lambda e, s, b: True, confirm=True,
        caps=(2, 2, 2), day_index=0,  # plafond 2
    )
    assert r["sent"] == 2
    assert r["skipped_cap"] == 3
    conn.close()


def test_suppression_evite_envoi(tmp_path: Path):
    conn = _seed(tmp_path, 2)
    replies.suppress(conn, "c0@b.fr", "stop")
    conn.commit()
    r = sender.send_due(conn, D, transport=lambda e, s, b: True, confirm=True, caps=(10, 10, 10))
    assert r["sent"] == 1  # c0 supprimé, seul c1 envoyé
    conn.close()


def test_export_transport_ecrit_eml(tmp_path: Path):
    conn = _seed(tmp_path, 1)
    transport = sender.export_transport(tmp_path / "outbox")
    sender.send_due(conn, D, transport=transport, confirm=True, caps=(10, 10, 10))
    files = list((tmp_path / "outbox").glob("*.eml"))
    assert len(files) == 1
    assert "Subject: Objet" in files[0].read_text(encoding="utf-8")
    conn.close()


def test_ingestion_bounce_supprime(tmp_path: Path):
    conn = _seed(tmp_path, 1)
    r = sender.ingest_event(conn, "c0@b.fr", "bounce")
    assert r["ok"] is True
    assert replies.is_suppressed(conn, "c0@b.fr")
    assert conn.execute("SELECT status FROM contacts WHERE email='c0@b.fr'").fetchone()["status"] == "bounced"
    conn.close()


def test_ingestion_contact_inconnu(tmp_path: Path):
    conn = _seed(tmp_path, 1)
    r = sender.ingest_event(conn, "inconnu@b.fr", "open")
    assert r["ok"] is False
    conn.close()


def test_export_transport_refuse_crlf_dans_email(tmp_path: Path):
    """S3 : un email porteur de CR/LF ne produit jamais de .eml (header injection)."""
    transport = sender.export_transport(tmp_path / "outbox")
    assert transport("a@b.fr\nBcc: spam@x.fr", "Objet", "Corps") is False
    assert list((tmp_path / "outbox").glob("*.eml")) == []


def test_export_transport_replie_sujet_multiligne(tmp_path: Path):
    transport = sender.export_transport(tmp_path / "outbox")
    assert transport("a@b.fr", "Objet\nX-Injecte: oui", "Corps") is True
    content = next((tmp_path / "outbox").glob("*.eml")).read_text(encoding="utf-8")
    assert "Subject: Objet X-Injecte: oui\n" in content
    assert "\nX-Injecte" not in content


def test_envoi_reel_refuse_placeholders_non_resolus(tmp_path: Path):
    """S4 : un message dont l'opt-out/CTA est resté en placeholder n'est jamais envoyé."""
    conn = _seed(tmp_path, 0)
    now = db._now()
    conn.execute(
        "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
        "VALUES ('p@b.fr', 'AIR_EAU', 'new', ?, ?)", (now, now),
    )
    cid = conn.execute("SELECT id FROM contacts WHERE email='p@b.fr'").fetchone()["id"]
    conn.execute(
        "INSERT INTO messages (contact_id, position, subject, body, status, scheduled_at, created_at) "
        "VALUES (?, 'J0', 'Objet', 'Corps… [LIEN_DESINSCRIPTION]', 'scheduled', '2026-01-10', ?)",
        (cid, now),
    )
    conn.commit()
    r = sender.send_due(conn, D, transport=lambda e, s, b: True, confirm=True, caps=(10, 10, 10))
    assert r["sent"] == 0
    assert r["skipped_placeholder"] == 1
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE status='sent'").fetchone()[0] == 0
    conn.close()


def test_cli_confirm_sans_transport_erreur(tmp_path: Path, capsys):
    """U1 : --confirm sans transport doit échouer explicitement, pas simuler en silence."""
    conn = _seed(tmp_path, 1)
    conn.close()
    import pytest
    with pytest.raises(SystemExit) as exc:
        sender.main(["--db", str(tmp_path / "s.sqlite"), "send", "--confirm"])
    assert exc.value.code == 2
    assert "transport" in capsys.readouterr().err


def test_day_index_deduit_de_l_historique(tmp_path: Path):
    """U2 : sans historique d'envoi → J1 (plafond bas), jamais le plateau par oubli."""
    conn = _seed(tmp_path, 5)
    r = sender.send_due(conn, D, caps=(2, 3, 100))  # dry-run, day_index non fourni
    assert r["cap"] == 2  # aucun envoi passé → J1
    # Historique : envois sur 2 jours distincts avant D → 3e jour = plateau.
    now = db._now()
    cid = conn.execute("SELECT id FROM contacts LIMIT 1").fetchone()["id"]
    for d in ("2026-01-08", "2026-01-09"):
        conn.execute(
            "INSERT INTO events (contact_id, type, created_at) VALUES (?, 'sent', ?)",
            (cid, f"{d}T09:00:00+00:00"),
        )
    conn.commit()
    assert sender.infer_day_index(conn, D) == 2
    r2 = sender.send_due(conn, D, caps=(2, 3, 100))
    assert r2["cap"] == 100
    conn.close()


def test_skipped_cap_exclut_les_echecs(tmp_path: Path):
    """U5 : un échec d'envoi n'est pas compté comme « non envoyé plafond »."""
    conn = _seed(tmp_path, 3)
    calls = {"n": 0}

    def flaky(email: str, subject: str, body: str) -> bool:
        calls["n"] += 1
        return calls["n"] != 1  # le premier envoi échoue

    r = sender.send_due(conn, D, transport=flaky, confirm=True, caps=(1, 1, 1), day_index=0)
    assert r["sent"] == 1
    assert r["failed"] == 1
    assert r["skipped_cap"] == 1  # 3 dus - 1 envoyé - 1 échec
    conn.close()
