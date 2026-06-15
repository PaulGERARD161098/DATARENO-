"""Tests — panneau de contrôle local (rendu + actions, sans réseau ni socket)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from src import config as C
from src import db
from src import replies
from src import web


D = date(2026, 1, 10)


def _seed(tmp_path: Path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    conn.execute(
        "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
        "VALUES ('jean@b.fr', 'AIR_EAU', 'new', ?, ?)", (now, now),
    )
    conn.execute(
        "INSERT INTO messages (contact_id, position, subject, body, status, scheduled_at, created_at) "
        "VALUES (1, 'J0', 'Objet', 'Corps', 'scheduled', '2026-01-10', ?)", (now,),
    )
    conn.commit()
    return conn


def test_render_panel_contient_les_sections(tmp_path: Path):
    conn = _seed(tmp_path)
    html = web.render_panel(conn, on_date=D)
    assert "panneau de pilotage" in html.lower()
    assert "Geste du jour" in html
    assert "Leads chauds" in html
    assert "A/B objet" in html
    assert "Gate" in html
    conn.close()


def test_action_run_simulation_n_envoie_rien(tmp_path: Path, monkeypatch):
    conn = _seed(tmp_path)
    # Aucune config SMTP/IMAP/Calendly → simulation forcée.
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SENDER_EMAIL", "SENDING_DOMAIN",
              "IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD", "CALENDLY_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    flash = web.action_run(conn, confirm=True, limit=None)
    assert "Simulation" in flash
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type='sent'").fetchone()[0] == 0
    conn.close()


def test_action_reply_stop_blackliste(tmp_path: Path):
    conn = _seed(tmp_path)
    flash = web.action_reply(conn, 1, replies.STOP)
    assert "STOP" in flash
    assert replies.is_suppressed(conn, "jean@b.fr")
    conn.close()


def test_action_reply_classe_inconnue(tmp_path: Path):
    conn = _seed(tmp_path)
    assert "inconnue" in web.action_reply(conn, 1, "BIDON").lower()
    conn.close()


def test_load_env(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('FOO_X=bar\n# commentaire\nQUOTED="zzz"\n', encoding="utf-8")
    monkeypatch.delenv("FOO_X", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)
    n = C.load_env(env)
    import os
    assert os.environ["FOO_X"] == "bar"
    assert os.environ["QUOTED"] == "zzz"
    assert n == 2


def test_load_env_n_ecrase_pas(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FOO_Y=fromfile\n", encoding="utf-8")
    monkeypatch.setenv("FOO_Y", "existant")
    C.load_env(env)
    import os
    assert os.environ["FOO_Y"] == "existant"  # l'existant prime
