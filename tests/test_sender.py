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


def test_warmup_day_index_auto(tmp_path: Path):
    """A1 : sans envoi passé → day_index 0 (plafond bas) ; après un jour d'envoi → 1."""
    conn = _seed(tmp_path, 1)
    assert sender.auto_day_index(conn, date(2026, 1, 10)) == 0
    # Un envoi enregistré la veille → on est au 2e jour de warm-up.
    conn.execute(
        "INSERT INTO events (contact_id, type, created_at) VALUES (1, 'sent', '2026-01-09T08:00:00+00:00')"
    )
    conn.commit()
    assert sender.auto_day_index(conn, date(2026, 1, 10)) == 1
    conn.close()


def test_warmup_auto_applique_le_plafond_bas(tmp_path: Path):
    """A1 : sans day_index explicite, le 1ᵉʳ jour plafonne à caps[0], pas au plateau."""
    conn = _seed(tmp_path, 5)
    r = sender.send_due(conn, D, transport=lambda e, s, b: True, confirm=True, caps=(2, 5, 10))
    assert r["day_index"] == 0
    assert r["sent"] == 2  # plafond J1 = 2, pas le plateau 10
    conn.close()


def test_placeholder_jamais_envoye(tmp_path: Path):
    """B1 : un message contenant un placeholder [..] n'est jamais envoyé."""
    conn = _seed(tmp_path, 1)
    conn.execute("UPDATE messages SET body='Lien : [VOTRE_LIEN_CALENDLY]'")
    conn.commit()
    sent: list[str] = []
    r = sender.send_due(
        conn, D, transport=lambda e, s, b: sent.append(e) or True,
        confirm=True, caps=(10, 10, 10),
    )
    assert r["blocked_placeholder"] == 1
    assert r["sent"] == 0
    assert sent == []
    conn.close()


def test_coupe_circuit_bounce_rate(tmp_path: Path):
    """A4 : au-delà du seuil de bounce, send_due refuse d'envoyer."""
    conn = _seed(tmp_path, 3)
    # 60 envois + 6 bounces = 10 % > 5 %, échantillon suffisant.
    for _ in range(60):
        conn.execute("INSERT INTO events (contact_id, type, created_at) VALUES (1, 'sent', '2025-12-01T08:00:00+00:00')")
    for _ in range(6):
        conn.execute("INSERT INTO events (contact_id, type, created_at) VALUES (1, 'bounce', '2025-12-02T08:00:00+00:00')")
    conn.commit()
    sent: list[str] = []
    r = sender.send_due(
        conn, D, transport=lambda e, s, b: sent.append(e) or True,
        confirm=True, caps=(100, 100, 100), bounce_min_sample=50,
    )
    assert r.get("circuit_breaker") == "bounce_rate"
    assert r["sent"] == 0
    assert sent == []
    conn.close()


def test_coupe_circuit_inactif_sous_echantillon(tmp_path: Path):
    """A4 : sous l'échantillon minimal, le coupe-circuit ne se déclenche pas."""
    conn = _seed(tmp_path, 2)
    conn.execute("INSERT INTO events (contact_id, type, created_at) VALUES (1, 'bounce', '2025-12-02T08:00:00+00:00')")
    conn.commit()
    r = sender.send_due(
        conn, D, transport=lambda e, s, b: True, confirm=True,
        caps=(10, 10, 10), bounce_min_sample=50,
    )
    assert "circuit_breaker" not in r
    assert r["sent"] == 2
    conn.close()


# --- Transport SMTP réel ----------------------------------------------------
from src.templates import MessageContext  # noqa: E402

REAL_CTX = MessageContext(
    calendly_url="https://calendly.com/expert/30min",
    optout_url="https://exemple.fr/stop",
    sender_name="Équipe CVC",
)


def test_build_mime_headers_et_optout():
    msg = sender.build_mime(
        "client@b.fr", "Objet", "Corps\nfin", from_email="contact@dom.fr",
        sender_name="Équipe CVC", optout_url="https://exemple.fr/stop",
        unsubscribe_mailto="unsubscribe@dom.fr",
    )
    assert msg["To"] == "client@b.fr"
    assert msg["From"] == "Équipe CVC <contact@dom.fr>"
    assert msg["Reply-To"] == "contact@dom.fr"
    assert "https://exemple.fr/stop" in msg["List-Unsubscribe"]
    assert "mailto:unsubscribe@dom.fr" in msg["List-Unsubscribe"]
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert msg.get_content().strip() == "Corps\nfin"


class _FakeSMTP:
    """Faux client SMTP context-manager qui capture les messages envoyés."""
    sent: list = []

    def __init__(self, cfg):
        self.cfg = cfg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send_message(self, msg):
        _FakeSMTP.sent.append(msg)


def test_smtp_transport_envoie_via_connecteur_injecte(tmp_path: Path):
    _FakeSMTP.sent = []
    conn = _seed(tmp_path, 2)
    cfg = sender.SmtpConfig(host="smtp.dom.fr", user="u", password="p", from_email="contact@dom.fr")
    transport = sender.smtp_transport(cfg, REAL_CTX, connector=_FakeSMTP)
    r = sender.send_due(conn, D, transport=transport, confirm=True, caps=(10, 10, 10))
    assert r["sent"] == 2
    assert len(_FakeSMTP.sent) == 2
    assert _FakeSMTP.sent[0]["From"] == "Équipe CVC <contact@dom.fr>"
    conn.close()


def test_smtp_transport_echec_ne_tue_pas_le_batch(tmp_path: Path):
    conn = _seed(tmp_path, 2)

    def _boom(cfg):
        raise OSError("connexion refusée")

    cfg = sender.SmtpConfig(host="x", user="u", password="p", from_email="contact@dom.fr")
    transport = sender.smtp_transport(cfg, REAL_CTX, connector=_boom)
    r = sender.send_due(conn, D, transport=transport, confirm=True, caps=(10, 10, 10))
    assert r["sent"] == 0
    assert r["failed"] == 2  # échecs comptés, aucune exception remontée
    conn.close()


def test_header_injection_neutralisee():
    """Un CR/LF dans une valeur d'en-tête ne doit jamais injecter d'en-tête (Bcc…)."""
    msg = sender.build_mime(
        "client@b.fr", "Objet\nBcc: pirate@evil.com", "Corps",
        from_email="contact@dom.fr", sender_name="Eq\r\nuipe", optout_url="https://x.fr/o",
    )
    assert "pirate" not in str(msg["Bcc"] or "")
    assert "\n" not in msg["Subject"] and "\r" not in msg["From"]


def test_export_transport_neutralise_les_en_tetes(tmp_path: Path):
    transport = sender.export_transport(tmp_path / "outbox")
    transport("a@b.fr\nBcc: pirate@evil.com", "Objet\nX-Evil: 1", "Corps")
    content = next((tmp_path / "outbox").glob("*.eml")).read_text(encoding="utf-8")
    header_lines = content.split("\n\n", 1)[0].splitlines()
    # La charge ne doit jamais devenir un en-tête à part entière (= début de ligne).
    assert not any(line.startswith(("Bcc:", "X-Evil:")) for line in header_lines)
    assert [line.split(":")[0] for line in header_lines] == ["To", "Subject"]


def test_smtp_config_missing_detecte_les_trous():
    cfg = sender.SmtpConfig(host="", user="u", password="", from_email="")
    missing = cfg.missing()
    assert "SMTP_HOST" in missing
    assert "SMTP_PASSWORD" in missing
    assert "SENDER_EMAIL/SENDING_DOMAIN" in missing
    assert "SMTP_USER" not in missing


def test_relint_bloque_un_claim_glisse_apres_generation(tmp_path: Path):
    """B5 : un corps devenu non conforme (claim) n'est jamais envoyé."""
    conn = _seed(tmp_path, 2)
    # On corrompt un message : un claim interdit a « glissé » après génération.
    conn.execute("UPDATE messages SET body='Votre PAC à 1€ !' WHERE contact_id=1")
    conn.commit()
    sent: list[str] = []
    r = sender.send_due(
        conn, D, transport=lambda e, s, b: sent.append(e) or True,
        confirm=True, caps=(10, 10, 10),
    )
    assert r["blocked_claim"] == 1
    assert r["sent"] == 1  # seul le message sain part
    assert sent == ["c1@b.fr"]
    conn.close()
