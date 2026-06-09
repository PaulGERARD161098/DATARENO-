"""Tests — remise en file « recontacter à 3 mois » + réinitialisation des arrêts."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from src import config as C
from src import db
from src import recontact
from src import replies
from src import sequence


TODAY = date(2026, 6, 9)


def _seed_recontact(tmp_path: Path):
    """1 contact qui a répondu RECONTACTER il y a 3 mois (date échue)."""
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    conn.execute(
        "INSERT INTO contacts (email, segment, surface, status, created_at, updated_at) "
        "VALUES ('c0@b.fr', ?, 50, 'new', ?, ?)", (C.SEGMENT_AIR_EAU, now, now),
    )
    cid = conn.execute("SELECT id FROM contacts WHERE email='c0@b.fr'").fetchone()["id"]
    # Simule une réponse RECONTACTER passée : event reply + statut/recontact_at échus.
    conn.execute("INSERT INTO events (contact_id, type, payload, created_at) VALUES (?, 'reply', ?, ?)",
                 (cid, replies.RECONTACTER, "2026-03-01T08:00:00+00:00"))
    past = (TODAY - timedelta(days=1)).isoformat()
    conn.execute("UPDATE contacts SET status='recontact_3m', recontact_at=? WHERE id=?", (past, cid))
    # Une touche annulée (comme après cancel_pending).
    conn.execute(
        "INSERT INTO messages (contact_id, position, subject, body, status, created_at) "
        "VALUES (?, 'J0', 'O', 'C', 'cancelled', ?)", (cid, now),
    )
    conn.commit()
    return conn, cid


def test_due_recontacts_selectionne_les_echus(tmp_path: Path):
    conn, cid = _seed_recontact(tmp_path)
    assert recontact.due_recontacts(conn, TODAY) == [cid]
    # Pas encore échu → non sélectionné.
    future = (TODAY + timedelta(days=10)).isoformat()
    conn.execute("UPDATE contacts SET recontact_at=? WHERE id=?", (future, cid))
    conn.commit()
    assert recontact.due_recontacts(conn, TODAY) == []
    conn.close()


def test_requeue_rearme_le_contact(tmp_path: Path):
    conn, cid = _seed_recontact(tmp_path)
    r = recontact.requeue(conn, TODAY)
    assert r["requeued"] == 1
    row = conn.execute("SELECT status, recontact_at FROM contacts WHERE id=?", (cid,)).fetchone()
    assert row["status"] == "new"
    assert row["recontact_at"] is None
    # Touches réarmées en draft, marqueur requeue posé.
    assert conn.execute("SELECT status FROM messages WHERE contact_id=?", (cid,)).fetchone()["status"] == "draft"
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type='requeue' AND contact_id=?", (cid,)).fetchone()[0] == 1
    conn.close()


def test_requeue_ignore_les_supprimes(tmp_path: Path):
    conn, cid = _seed_recontact(tmp_path)
    replies.suppress(conn, "c0@b.fr", "stop")
    conn.commit()
    assert recontact.requeue(conn, TODAY)["requeued"] == 0
    conn.close()


def test_apres_requeue_la_sequence_replanifie(tmp_path: Path):
    """Le requeue neutralise l'ancien arrêt : plan_sequence reprend le contact."""
    conn, cid = _seed_recontact(tmp_path)
    # Avant requeue : l'event reply (arrêt) exclut le contact.
    assert cid in sequence._stopped_contacts(conn)
    recontact.requeue(conn, TODAY)
    # Après requeue : l'arrêt antérieur ne compte plus.
    assert cid not in sequence._stopped_contacts(conn)
    r = sequence.plan_sequence(conn, start_date=TODAY, caps=(10, 10, 10))
    assert r["planned_contacts"] == 1
    n = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE contact_id=? AND status='scheduled'", (cid,)
    ).fetchone()[0]
    assert n == 3  # séquence complète régénérée
    conn.close()


def test_nouvel_arret_apres_requeue_re_exclut(tmp_path: Path):
    conn, cid = _seed_recontact(tmp_path)
    recontact.requeue(conn, TODAY)
    # Un nouveau STOP postérieur au requeue ré-exclut le contact.
    conn.execute("INSERT INTO events (contact_id, type, created_at) VALUES (?, 'optout', ?)",
                 (cid, db._now()))
    conn.commit()
    assert cid in sequence._stopped_contacts(conn)
    conn.close()
