"""inbox — Ingestion des retours par IMAP (poll de la boîte du domaine dédié).

Chaînon « retours » de l'opérationnel, pendant autonome du transport SMTP. On
relève les messages non lus, on classe chaque retour, et on alimente l'état :

- **bounce** (DSN mailer-daemon) → suppression auto du destinataire en échec
  (purge), via `sender.ingest_event` ;
- **réponse** d'un contact connu → on **stoppe la séquence** (`cancel_pending`,
  cf. SPEC « arrêts : réponse/clic/opt-out/bounce ») et on **journalise la classe
  PROPOSÉE** — l'action finale (Intéressé→Calendly, STOP→blacklist…) reste validée
  par un humain via `python -m src.replies apply`.

Le réseau (IMAP) est isolé derrière un *fetcher* injectable : la logique d'ingestion
se teste sans connexion. Aucune PII dans les logs.

CLI :
    python -m src.inbox poll [--db state.sqlite]
"""
from __future__ import annotations

import argparse
import email
import email.header
import email.utils
import imaplib
import os
import re
import sqlite3
import ssl
from dataclasses import dataclass
from email.message import Message
from typing import Callable, Iterator

from . import config as _C
from . import db as _db
from . import replies as _replies
from . import sender as _sender
from .logging_setup import get_logger

logger = get_logger("datareno.inbox")

# Adresse email « brute » dans un texte (DSN, en-têtes) — non ancrée (≠ config.EMAIL_REGEX).
_EMAIL_FIND = re.compile(r"[^@\s<>\"]+@[^@\s<>\"]+\.[^@\s<>\"]+")

# Expéditeurs typiques d'un avis de non-remise.
_DAEMON_HINTS = ("mailer-daemon", "postmaster", "mail delivery")

# Bounce SOFT (temporaire) : ne pas supprimer le contact, c'est récupérable.
_SOFT_HINTS = (
    "temporhttps", "temporaire", "temporarily", "try again", "mailbox full", "boite pleine",
    "boîte pleine", "over quota", "quota exceeded", "delayed", "deferred", "greylist",
    "4.2.2", "4.2.1", "4.3.1", "4.7.1",
)
# Bounce HARD (permanent) : adresse morte → suppression.
_HARD_HINTS = (
    "user unknown", "no such user", "does not exist", "adresse introuvable",
    "address not found", "mailbox unavailable", "5.1.1", "550 5.1.1", "recipient rejected",
)
# Réponse automatique (absence / OOO) : ce N'EST PAS un engagement, la séquence continue.
_AUTOREPLY_HINTS = (
    "absent", "absence", "out of office", "ooo", "autoreply", "auto-reply", "automatic reply",
    "reponse automatique", "réponse automatique", "conges", "congés", "en vacances",
    "de retour le", "je serai de retour", "actuellement absent",
)

# Au-delà de N bounces soft pour un même contact, on escalade en suppression.
SOFT_BOUNCE_ESCALATE = 3

# Genres de retour possibles.
KIND_BOUNCE_HARD = "bounce_hard"
KIND_BOUNCE_SOFT = "bounce_soft"
KIND_AUTOREPLY = "auto_reply"
KIND_REPLY = "reply"


def classify_inbound(from_email: str, subject: str, body: str) -> tuple[str, str]:
    """Retourne (kind, classe_proposée).

    kind ∈ {bounce_hard, bounce_soft, auto_reply, reply}. La classe proposée
    n'a de sens que pour `reply` (à valider par un humain).
    """
    text = _C.strip_accents(f"{subject}\n{body}").lower()
    sender_l = (from_email or "").lower()
    label = _replies.classify_reply(f"{subject}\n{body}")

    is_bounce = label == _replies.BOUNCE or any(h in sender_l for h in _DAEMON_HINTS)
    if is_bounce:
        # Ambigu → HARD par défaut : protéger la réputation du domaine prime (pre-mortem).
        if any(h in text for h in _SOFT_HINTS) and not any(h in text for h in _HARD_HINTS):
            return KIND_BOUNCE_SOFT, _replies.BOUNCE
        return KIND_BOUNCE_HARD, _replies.BOUNCE

    if any(h in text for h in _AUTOREPLY_HINTS):
        return KIND_AUTOREPLY, _replies.RECONTACTER

    return KIND_REPLY, label


def _known_email(conn: sqlite3.Connection, *texts: str) -> str | None:
    """Première adresse présente dans `contacts` trouvée dans les textes donnés."""
    seen: set[str] = set()
    for text in texts:
        for match in _EMAIL_FIND.findall(text or ""):
            candidate = match.lower()
            if candidate in seen:
                continue
            seen.add(candidate)
            row = conn.execute("SELECT 1 FROM contacts WHERE email=?", (candidate,)).fetchone()
            if row:
                return candidate
    return None


def _count_events(conn: sqlite3.Connection, contact_id: int, event_type: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM events WHERE contact_id=? AND type=?", (contact_id, event_type)
    ).fetchone()[0]


def ingest_inbound(
    conn: sqlite3.Connection, from_email: str, subject: str, body: str
) -> dict[str, object]:
    """Ingère un message entrant selon son genre (bounce hard/soft, auto-reply, réponse)."""
    kind, label = classify_inbound(from_email, subject, body)

    if kind in (KIND_BOUNCE_HARD, KIND_BOUNCE_SOFT):
        # Le destinataire en échec est dans le corps du DSN, pas dans le From (daemon).
        target = _known_email(conn, body, subject, from_email)
        if not target:
            logger.info("bounce sans destinataire connu")
            return {"ok": False, "kind": kind, "reason": "destinataire_introuvable"}
        row = conn.execute("SELECT id FROM contacts WHERE email=?", (target,)).fetchone()
        contact_id = row["id"]
        if kind == KIND_BOUNCE_HARD:
            _sender.ingest_event(conn, target, "bounce")  # → suppression définitive
            return {"ok": True, "kind": kind}
        # Soft : on journalise sans supprimer ; escalade au-delà du seuil.
        conn.execute(
            "INSERT INTO events (contact_id, type, created_at) VALUES (?, 'soft_bounce', ?)",
            (contact_id, _db._now()),
        )
        conn.commit()
        soft_count = _count_events(conn, contact_id, "soft_bounce")
        if soft_count >= SOFT_BOUNCE_ESCALATE:
            _sender.ingest_event(conn, target, "bounce")  # trop de soft → suppression
            return {"ok": True, "kind": kind, "escalated": True, "soft_count": soft_count}
        return {"ok": True, "kind": kind, "escalated": False, "soft_count": soft_count}

    # Pour auto-reply et réponse, on identifie par l'adresse expéditrice.
    target = (from_email or "").lower()
    row = conn.execute("SELECT id FROM contacts WHERE email=?", (target,)).fetchone()
    if not row:
        logger.info("message d'un expéditeur inconnu")
        return {"ok": False, "kind": kind, "reason": "contact_inconnu"}
    contact_id = row["id"]

    if kind == KIND_AUTOREPLY:
        # Absence/OOO : pas un engagement → on journalise SANS arrêter la séquence.
        conn.execute(
            "INSERT INTO events (contact_id, type, created_at) VALUES (?, 'auto_reply', ?)",
            (contact_id, _db._now()),
        )
        conn.commit()
        logger.info("auto-reply ingéré (séquence maintenue)", extra={"context": {"contact_id": contact_id}})
        return {"ok": True, "kind": kind, "contact_id": contact_id, "applied": False}

    # Réponse réelle : stoppe la séquence + classe proposée (action finale validée par un humain).
    cancelled = _replies.cancel_pending(conn, contact_id)
    _replies.record_reply(conn, contact_id, label)
    conn.commit()
    logger.info("réponse ingérée", extra={"context": {
        "contact_id": contact_id, "proposed": label, "cancelled": cancelled, "applied": False,
    }})
    return {"ok": True, "kind": KIND_REPLY, "contact_id": contact_id,
            "proposed": label, "cancelled": cancelled, "applied": False}


# --- IMAP (réseau isolé, injectable) ---------------------------------------
@dataclass
class ImapConfig:
    host: str
    user: str
    password: str
    port: int = 993
    folder: str = "INBOX"

    @classmethod
    def from_env(cls) -> "ImapConfig":
        return cls(
            host=os.getenv("IMAP_HOST", "").strip(),
            user=os.getenv("IMAP_USER", "").strip(),
            password=os.getenv("IMAP_PASSWORD", "").strip(),
            port=int(os.getenv("IMAP_PORT", "").strip() or 993),
            folder=os.getenv("IMAP_FOLDER", "INBOX").strip() or "INBOX",
        )

    def missing(self) -> list[str]:
        return [name for name, val in (
            ("IMAP_HOST", self.host), ("IMAP_USER", self.user), ("IMAP_PASSWORD", self.password),
        ) if not val]


# Un fetcher rend des tuples (from_email, subject, body) pour chaque message non lu.
Fetcher = Callable[[ImapConfig], Iterator[tuple[str, str, str]]]


def _body_text(msg: Message) -> str:
    """Extrait le texte (text/plain prioritaire) d'un message email, tolérant aux erreurs."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_content()
                except Exception:  # noqa: BLE001
                    payload = part.get_payload(decode=True) or b""
                    return payload.decode("utf-8", "replace")
        return ""
    try:
        return msg.get_content()
    except Exception:  # noqa: BLE001
        payload = msg.get_payload(decode=True) or b""
        return payload.decode("utf-8", "replace")


def _default_imap_fetch(cfg: ImapConfig) -> Iterator[tuple[str, str, str]]:
    """Relève les messages non lus via IMAP (TLS vérifié + timeout), marqués lus au passage.

    Contexte TLS explicite : sans lui, imaplib (Py 3.11) ne vérifie PAS le
    certificat serveur → identifiants exposés à un MITM.
    """
    client = imaplib.IMAP4_SSL(
        cfg.host, cfg.port, ssl_context=ssl.create_default_context(), timeout=30.0
    )
    try:
        client.login(cfg.user, cfg.password)
        client.select(cfg.folder)
        _typ, data = client.search(None, "UNSEEN")
        for num in (data[0].split() if data and data[0] else []):
            _typ, raw = client.fetch(num, "(RFC822)")
            if not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])
            from_email = email.utils.parseaddr(msg.get("From", ""))[1]
            subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))
            yield from_email, subject, _body_text(msg)
            client.store(num, "+FLAGS", "\\Seen")
    finally:
        try:
            client.logout()
        except Exception:  # noqa: BLE001
            pass


def poll_inbox(
    conn: sqlite3.Connection, cfg: ImapConfig, *, fetcher: Fetcher | None = None
) -> dict[str, int]:
    """Relève la boîte et ingère chaque message. Retourne une synthèse comptée."""
    fetcher = fetcher or _default_imap_fetch
    summary = {"seen": 0, "bounces": 0, "soft_bounces": 0, "auto_replies": 0,
               "replies": 0, "unknown": 0}
    for from_email, subject, body in fetcher(cfg):
        summary["seen"] += 1
        r = ingest_inbound(conn, from_email, subject, body)
        if not r["ok"]:
            summary["unknown"] += 1
        elif r["kind"] == KIND_BOUNCE_HARD:
            summary["bounces"] += 1
        elif r["kind"] == KIND_BOUNCE_SOFT:
            summary["soft_bounces"] += 1
            if r.get("escalated"):
                summary["bounces"] += 1
        elif r["kind"] == KIND_AUTOREPLY:
            summary["auto_replies"] += 1
        else:
            summary["replies"] += 1
    logger.info("poll inbox", extra={"context": summary})
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestion des retours par IMAP.")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("poll", help="Relève la boîte IMAP et ingère les retours.")
    args = parser.parse_args(argv)

    if args.cmd == "poll":
        cfg = ImapConfig.from_env()
        missing = cfg.missing()
        if missing:
            print(f"⛔ IMAP non configuré : {', '.join(missing)}. Rien relevé.")  # noqa: T201
            return 2
        conn = _db.connect(args.db)
        try:
            s = poll_inbox(conn, cfg)
            print(  # noqa: T201
                f"Poll IMAP — relevés={s['seen']} · bounces={s['bounces']} "
                f"(soft={s['soft_bounces']}) · auto-replies={s['auto_replies']} · "
                f"réponses={s['replies']} · inconnus={s['unknown']}\n"
                "Réponses : classe proposée journalisée — valider via `src.replies apply`."
            )
        finally:
            conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
