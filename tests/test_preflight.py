"""Tests — gate Go/No-Go (preflight)."""
from __future__ import annotations

from pathlib import Path

from src import db
from src import preflight
from src.calendly import CalendlyConfig
from src.inbox import ImapConfig
from src.sender import SmtpConfig
from src.templates import MessageContext


REAL_CTX = MessageContext(
    calendly_url="https://calendly.com/x/30min",
    optout_url="https://exemple.fr/stop",
    sender_name="Équipe CVC",
    reassurance="RGE, décennale",
)
FULL_SMTP = SmtpConfig(host="h", user="u", password="p", from_email="c@dom.fr")
FULL_IMAP = ImapConfig(host="h", user="u", password="p")
FULL_CAL = CalendlyConfig(token="t")


def _seed(tmp_path: Path, *, placeholder=False, role=False):
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    email = "contact@b.fr" if role else "jean@b.fr"
    conn.execute(
        "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
        "VALUES (?, 'AIR_EAU', 'new', ?, ?)", (email, now, now),
    )
    body = "Corps [LIEN_DESINSCRIPTION]" if placeholder else "Corps https://ok"
    conn.execute(
        "INSERT INTO messages (contact_id, position, subject, body, status, scheduled_at, created_at) "
        "VALUES (1, 'J0', 'O', ?, 'scheduled', '2026-01-10', ?)", (body, now),
    )
    conn.commit()
    return conn


def _status(checks, name):
    return next(c.status for c in checks if c.name == name)


def test_preflight_go_quand_tout_est_pret(tmp_path: Path):
    conn = _seed(tmp_path)
    checks = preflight.run_preflight(
        conn, ctx=REAL_CTX, smtp=FULL_SMTP, imap=FULL_IMAP, calendly=FULL_CAL
    )
    assert preflight.verdict(checks) == "GO"
    conn.close()


def test_preflight_nogo_si_lien_placeholder(tmp_path: Path):
    conn = _seed(tmp_path)
    bad_ctx = MessageContext(  # opt-out resté en placeholder
        calendly_url="https://calendly.com/x", optout_url="[LIEN_DESINSCRIPTION]",
        sender_name="X", reassurance="RGE",
    )
    checks = preflight.run_preflight(conn, ctx=bad_ctx, smtp=FULL_SMTP, imap=FULL_IMAP, calendly=FULL_CAL)
    assert _status(checks, "optout_url") == preflight.FAIL
    assert preflight.verdict(checks) == "NO-GO"
    conn.close()


def test_preflight_nogo_si_smtp_incomplet(tmp_path: Path):
    conn = _seed(tmp_path)
    checks = preflight.run_preflight(
        conn, ctx=REAL_CTX, smtp=SmtpConfig(host="", user="", password="", from_email=""),
        imap=FULL_IMAP, calendly=FULL_CAL,
    )
    assert _status(checks, "smtp_config") == preflight.FAIL
    assert preflight.verdict(checks) == "NO-GO"
    conn.close()


def test_preflight_nogo_si_message_avec_placeholder(tmp_path: Path):
    conn = _seed(tmp_path, placeholder=True)
    checks = preflight.run_preflight(conn, ctx=REAL_CTX, smtp=FULL_SMTP, imap=FULL_IMAP, calendly=FULL_CAL)
    assert _status(checks, "placeholders_residuels") == preflight.FAIL
    assert preflight.verdict(checks) == "NO-GO"
    conn.close()


def test_preflight_warn_adresse_role(tmp_path: Path):
    conn = _seed(tmp_path, role=True)
    checks = preflight.run_preflight(conn, ctx=REAL_CTX, smtp=FULL_SMTP, imap=FULL_IMAP, calendly=FULL_CAL)
    assert _status(checks, "hygiene_adresses") == preflight.WARN
    assert preflight.verdict(checks) == "GO"  # un WARN ne bloque pas
    conn.close()


def test_preflight_imap_calendly_absents_sont_warn(tmp_path: Path):
    conn = _seed(tmp_path)
    checks = preflight.run_preflight(
        conn, ctx=REAL_CTX, smtp=FULL_SMTP,
        imap=ImapConfig(host="", user="", password=""), calendly=CalendlyConfig(token=""),
    )
    assert _status(checks, "imap_config") == preflight.WARN
    assert _status(checks, "calendly_token") == preflight.WARN
    assert preflight.verdict(checks) == "GO"
    conn.close()
