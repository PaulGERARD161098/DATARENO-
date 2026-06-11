"""Tests Phase 7 — reporting & A/B + Phase 9 dashboard (génération HTML)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from src import db
from src import report
from src import dashboard


def _seed(tmp_path: Path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    # 2 contacts, messages envoyés avec objets distincts ; events open/reply ; 1 RDV.
    for i, (subj, status) in enumerate([("Objet A", "rdv"), ("Objet B", "contacted")]):
        conn.execute(
            "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
            "VALUES (?, 'AIR_EAU', ?, ?, ?)", (f"c{i}@b.fr", status, now, now),
        )
        cid = conn.execute("SELECT id FROM contacts WHERE email=?", (f"c{i}@b.fr",)).fetchone()["id"]
        conn.execute(
            "INSERT INTO messages (contact_id, position, subject, status, created_at) "
            "VALUES (?, 'J0', ?, 'sent', ?)", (cid, subj, now),
        )
        mid = conn.execute("SELECT id FROM messages WHERE contact_id=?", (cid,)).fetchone()["id"]
        conn.execute("INSERT INTO events (contact_id, message_id, type, created_at) VALUES (?,?,'open',?)", (cid, mid, now))
        if i == 0:
            conn.execute("INSERT INTO events (contact_id, message_id, type, created_at) VALUES (?,?,'reply',?)", (cid, mid, now))
    conn.commit()
    return conn


def test_funnel_compte_les_etapes(tmp_path: Path):
    conn = _seed(tmp_path)
    f = report.funnel(conn)
    assert f["messages_envoyes"] == 2
    assert f["contacts_ouverts"] == 2
    assert f["contacts_repondus"] == 1
    assert f["rdv"] == 1
    conn.close()


def test_kpis_taux(tmp_path: Path):
    conn = _seed(tmp_path)
    k = report.kpis(conn)
    assert k["taux_ouverture_%"] == 100.0
    assert k["taux_reponse_%"] == 50.0
    assert k["taux_rdv_%"] == 50.0
    conn.close()


def test_ab_objet_et_reco(tmp_path: Path):
    conn = _seed(tmp_path)
    ab = report.ab_subjects(conn)
    assert len(ab) == 2
    # « Objet A » a une réponse → meilleur taux → recommandé
    assert report.recommend_subject(conn) == "Objet A"
    conn.close()


def test_render_report_non_vide(tmp_path: Path):
    conn = _seed(tmp_path)
    txt = report.render_report(conn)
    assert "Funnel" in txt and "Objet A" in txt
    conn.close()


def test_dashboard_genere_html(tmp_path: Path):
    conn = _seed(tmp_path)
    html_str = dashboard.build_html(conn, on_date=date(2026, 1, 1))
    assert "<html" in html_str and "DATA RÉNO" in html_str
    assert "Funnel" in html_str
    # Sections ajoutées (scoring / A-B / RDV).
    assert "Paliers d'engagement" in html_str
    assert "A/B objet" in html_str
    assert "RDV pris" in html_str
    assert "Leads chauds" in html_str
    conn.close()
