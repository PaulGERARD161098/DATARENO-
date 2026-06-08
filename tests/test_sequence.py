"""Tests Phase 5 — séquençage J0/J+4/J+8, warm-up et conditions d'arrêt."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path


from src import config as C
from src import db
from src import sequence


TODAY = date(2026, 1, 1)


def _seed(tmp_path: Path, n: int) -> db.sqlite3.Connection:
    """Crée n contacts AIR_EAU directement en base (sans passer par les CSV)."""
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    for i in range(n):
        conn.execute(
            "INSERT INTO contacts (email, segment, surface, froid_plus, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, 'new', ?, ?)",
            (f"c{i}@b.fr", C.SEGMENT_AIR_EAU, float(i), now, now),
        )
    conn.commit()
    return conn


def test_warmup_caps_par_jour():
    caps = (30, 50, 100)
    assert sequence.cap_for_day(0, caps) == 30
    assert sequence.cap_for_day(1, caps) == 50
    assert sequence.cap_for_day(2, caps) == 100
    assert sequence.cap_for_day(99, caps) == 100


def test_plan_cree_les_trois_touches(tmp_path: Path):
    conn = _seed(tmp_path, 1)
    sequence.plan_sequence(conn, start_date=TODAY, caps=(10, 10, 10))
    rows = {r["position"]: r["scheduled_at"] for r in conn.execute(
        "SELECT position, scheduled_at, status FROM messages"
    )}
    assert rows["J0"] == TODAY.isoformat()
    assert rows["J4"] == (TODAY + timedelta(days=4)).isoformat()
    assert rows["J8"] == (TODAY + timedelta(days=8)).isoformat()
    statuses = {r["status"] for r in conn.execute("SELECT status FROM messages")}
    assert statuses == {"scheduled"}
    conn.close()


def test_plan_respecte_le_plafond(tmp_path: Path):
    # Plafond serré : 2 le J1, 3 le J2, 4 ensuite.
    conn = _seed(tmp_path, 12)
    caps = (2, 3, 4)
    sequence.plan_sequence(conn, start_date=TODAY, caps=caps)
    counts = sequence.simulate(conn, TODAY, days=40)
    for i, (_, n) in enumerate(counts.items()):
        assert n <= sequence.cap_for_day(i, caps), f"jour {i} dépasse le plafond : {n}"
    # tous les contacts planifiés (12 × 3 = 36 messages)
    total = conn.execute("SELECT COUNT(*) FROM messages WHERE status='scheduled'").fetchone()[0]
    assert total == 36
    conn.close()


def test_contact_stoppe_non_planifie(tmp_path: Path):
    conn = _seed(tmp_path, 2)
    # Le contact 1 a un opt-out -> exclu de la planification.
    cid = conn.execute("SELECT id FROM contacts ORDER BY id LIMIT 1").fetchone()["id"]
    conn.execute(
        "INSERT INTO events (contact_id, type, created_at) VALUES (?, 'optout', ?)",
        (cid, db._now()),
    )
    conn.commit()
    r = sequence.plan_sequence(conn, start_date=TODAY, caps=(10, 10, 10))
    assert r["skipped_stop"] == 1
    assert r["planned_contacts"] == 1
    # aucun message programmé pour le contact stoppé
    n = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE contact_id=? AND status='scheduled'", (cid,)
    ).fetchone()[0]
    assert n == 0
    conn.close()


def test_plan_idempotent(tmp_path: Path):
    conn = _seed(tmp_path, 5)
    r1 = sequence.plan_sequence(conn, start_date=TODAY, caps=(3, 4, 5))
    r2 = sequence.plan_sequence(conn, start_date=TODAY, caps=(3, 4, 5))
    assert r1["scheduled_messages"] == r2["scheduled_messages"]
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert total == 15  # 5 contacts × 3 touches, pas de doublon
    conn.close()


def test_aucun_envoi(tmp_path: Path):
    conn = _seed(tmp_path, 3)
    sequence.plan_sequence(conn, start_date=TODAY, caps=(5, 5, 5))
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE status='sent'").fetchone()[0] == 0
    conn.close()
