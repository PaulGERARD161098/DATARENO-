"""Tests U3 — dashboard HTML statique (sections, file enrichie, échappement XSS)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from src import dashboard
from src import db
from src import replies


D = date(2026, 1, 10)


def _seed(tmp_path: Path, n: int, scheduled_at: str = "2026-01-10", subject: str = "Objet"):
    conn = db.connect(tmp_path / "d.sqlite")
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
            "VALUES (?, 'J0', ?, 'Corps', 'scheduled', ?, ?)", (cid, subject, scheduled_at, now),
        )
    conn.commit()
    return conn


def test_sections_presentes(tmp_path: Path):
    conn = _seed(tmp_path, 1)
    out = dashboard.build_html(conn, D)
    for titre in (
        "Funnel", "Contacts par segment", "Messages par statut",
        "Suppressions par raison", "Réponses par classe",
        "File de validation — drafts dus (max 50)",
    ):
        assert titre in out
    conn.close()


def test_file_validation_email_et_envoi_prevu(tmp_path: Path):
    conn = _seed(tmp_path, 2)
    out = dashboard.build_html(conn, D)
    assert "c0@b.fr" in out
    assert "c1@b.fr" in out
    assert "2026-01-10" in out  # scheduled_at affiché
    conn.close()


def test_file_validation_plafonnee_a_50(tmp_path: Path):
    conn = _seed(tmp_path, 60)
    out = dashboard.build_html(conn, D)
    # Les emails n'apparaissent que dans la file de validation.
    assert out.count("@b.fr") == 50
    conn.close()


def test_valeur_hostile_echappee(tmp_path: Path):
    """Garde-fou XSS : un objet forgé en DB ne doit jamais produire de balise."""
    conn = _seed(tmp_path, 1, subject="<script>alert('x')</script>")
    out = dashboard.build_html(conn, D)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    conn.close()


def test_suppressions_par_raison_comptees(tmp_path: Path):
    conn = _seed(tmp_path, 3)
    replies.suppress(conn, "c0@b.fr", "stop")
    replies.suppress(conn, "c1@b.fr", "stop")
    replies.suppress(conn, "c2@b.fr", "optout")
    conn.commit()
    out = dashboard.build_html(conn, D)
    assert "<td>stop</td><td class='num'>2</td>" in out
    assert "<td>optout</td><td class='num'>1</td>" in out
    assert "suppressions : 3" in out
    conn.close()


def test_reponses_par_classe_comptees(tmp_path: Path):
    conn = _seed(tmp_path, 2)
    now = db._now()
    cid = conn.execute("SELECT id FROM contacts WHERE email='c0@b.fr'").fetchone()["id"]
    for payload in ("interesse", "interesse", None):
        conn.execute(
            "INSERT INTO events (contact_id, type, payload, created_at) VALUES (?, 'reply', ?, ?)",
            (cid, payload, now),
        )
    conn.commit()
    out = dashboard.build_html(conn, D)
    assert "<td>interesse</td><td class='num'>2</td>" in out
    assert "<td>(sans classe)</td><td class='num'>1</td>" in out
    conn.close()


def test_kpi_tiles_presentes(tmp_path: Path):
    conn = _seed(tmp_path, 1)
    out = dashboard.build_html(conn, D)
    for label in ("Messages envoyés", "Taux d&#x27;ouverture", "Taux de réponse",
                  "RDV obtenus", "Taux de RDV"):
        assert label in out
    conn.close()


def test_base_vide_rend_messages_vides(tmp_path: Path):
    conn = db.connect(tmp_path / "v.sqlite")
    db.init_db(conn)
    out = dashboard.build_html(conn, D)
    assert "(aucun draft dû)" in out
    assert "(aucune suppression)" in out
    assert "(aucune réponse)" in out
    conn.close()


def test_cli_ecrit_le_fichier(tmp_path: Path, capsys):
    conn = _seed(tmp_path, 1)
    conn.close()
    rc = dashboard.main([str(tmp_path / "dash.html"), "--db", str(tmp_path / "d.sqlite")])
    assert rc == 0
    content = (tmp_path / "dash.html").read_text(encoding="utf-8")
    assert content.startswith("<!doctype html>")
    assert "DATA RÉNO" in content
