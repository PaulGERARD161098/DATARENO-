"""Tests — scoring d'engagement (paliers + leads chauds)."""
from __future__ import annotations

from pathlib import Path

from src import db
from src import scoring


def _seed(tmp_path: Path):
    """Un contact par palier d'engagement attendu."""
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()

    def add(email, status="new"):
        conn.execute(
            "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
            "VALUES (?, 'AIR_EAU', ?, ?, ?)", (email, status, now, now),
        )
        return conn.execute("SELECT id FROM contacts WHERE email=?", (email,)).fetchone()["id"]

    def ev(cid, types, when=None):
        for t in types:
            conn.execute("INSERT INTO events (contact_id, type, created_at) VALUES (?,?,?)",
                         (cid, t, when or now))

    en_file = add("enfile@b.fr")  # aucun event
    ev(add("delivre@b.fr"), ["sent"])
    ev(add("ouvreur@b.fr"), ["sent", "open"])
    cliqueur = add("cliqueur@b.fr")
    ev(cliqueur, ["sent", "open"])
    ev(cliqueur, ["click"], "2026-01-02T09:00:00+00:00")
    ev(add("repondu@b.fr"), ["sent", "click", "reply"])
    ev(add("rdv@b.fr", status="rdv"), ["rdv"])
    add("perdu@b.fr", status="stopped")
    conn.commit()
    return conn, {"en_file": en_file, "cliqueur": cliqueur}


def test_tiers_summary(tmp_path: Path):
    conn, _ = _seed(tmp_path)
    counts = scoring.tiers_summary(conn)
    assert counts["EN_FILE"] == 1
    assert counts["DELIVRE"] == 1
    assert counts["OUVREUR"] == 1
    assert counts["CLIQUEUR"] == 1
    assert counts["REPONDU"] == 1
    assert counts["RDV"] == 1
    assert counts["PERDU"] == 1
    assert sum(counts.values()) == 7
    conn.close()


def test_perdu_si_supprime_meme_avec_engagement(tmp_path: Path):
    conn, ids = _seed(tmp_path)
    # Le cliqueur passe en suppression → bascule PERDU malgré le clic.
    conn.execute("INSERT INTO suppressions (email, reason, created_at) VALUES ('cliqueur@b.fr','stop',?)", (db._now(),))
    conn.commit()
    counts = scoring.tiers_summary(conn)
    assert counts["CLIQUEUR"] == 0
    assert counts["PERDU"] == 2
    conn.close()


def test_hot_leads_liste_les_cliqueurs(tmp_path: Path):
    conn, ids = _seed(tmp_path)
    hot = scoring.hot_leads(conn)
    assert [h["email"] for h in hot] == ["cliqueur@b.fr"]
    assert hot[0]["contact_id"] == ids["cliqueur"]
    conn.close()
