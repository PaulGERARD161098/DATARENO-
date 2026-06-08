"""Tests Phase 6 — classification des réponses + actions (humain valide)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src import db
from src import replies
from src.templates import MessageContext


def _seed_contact(tmp_path: Path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    conn.execute(
        "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
        "VALUES ('a@b.fr', 'AIR_EAU', 'new', ?, ?)", (now, now),
    )
    cid = conn.execute("SELECT id FROM contacts").fetchone()["id"]
    for pos in ("J0", "J4", "J8"):
        conn.execute(
            "INSERT INTO messages (contact_id, position, status, created_at) VALUES (?, ?, 'scheduled', ?)",
            (cid, pos, now),
        )
    conn.commit()
    return conn, cid


@pytest.mark.parametrize("text,label", [
    ("Merci de me désabonner immédiatement", replies.STOP),
    ("Mail delivery failed: address not found", replies.BOUNCE),
    ("Oui ça m'intéresse, envoyez un devis", replies.INTERESSE),
    ("J'ai réservé un créneau sur calendly", replies.RDV),
    ("Pas maintenant, recontactez-moi plus tard", replies.RECONTACTER),
    ("Non merci, déjà équipé", replies.PAS_INTERESSE),
])
def test_classify_reply(text, label):
    assert replies.classify_reply(text) == label


def test_proposition_sans_action(tmp_path: Path):
    conn, cid = _seed_contact(tmp_path)
    r = replies.handle_reply(conn, cid, "ça m'intéresse")
    assert r["applied"] is False
    assert r["proposed"] == replies.INTERESSE
    # rien n'a bougé
    assert conn.execute("SELECT status FROM contacts WHERE id=?", (cid,)).fetchone()["status"] == "new"
    conn.close()


def test_stop_blackliste_et_annule(tmp_path: Path):
    conn, cid = _seed_contact(tmp_path)
    r = replies.handle_reply(conn, cid, "stop", validated_label=replies.STOP)
    assert r["applied"] is True
    assert replies.is_suppressed(conn, "a@b.fr")
    # toutes les touches annulées
    n = conn.execute("SELECT COUNT(*) FROM messages WHERE status='cancelled'").fetchone()[0]
    assert n == 3
    assert conn.execute("SELECT status FROM contacts WHERE id=?", (cid,)).fetchone()["status"] == "stopped"
    conn.close()


def test_interesse_renvoie_calendly(tmp_path: Path):
    conn, cid = _seed_contact(tmp_path)
    ctx = MessageContext(calendly_url="https://calendly.test/x")
    action = replies.apply_action(conn, cid, replies.INTERESSE, ctx=ctx)
    assert action["calendly_url"] == "https://calendly.test/x"
    assert conn.execute("SELECT status FROM contacts WHERE id=?", (cid,)).fetchone()["status"] == "interested"
    conn.close()


def test_recontacter_pose_date(tmp_path: Path):
    conn, cid = _seed_contact(tmp_path)
    replies.apply_action(conn, cid, replies.RECONTACTER, today=date(2026, 1, 1))
    row = conn.execute("SELECT status, recontact_at FROM contacts WHERE id=?", (cid,)).fetchone()
    assert row["status"] == "recontact_3m"
    assert row["recontact_at"] == "2026-04-01"
    conn.close()
