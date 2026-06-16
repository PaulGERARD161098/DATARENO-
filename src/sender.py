"""sender — Phase 8 : connecteur d'envoi (déclenché par l'humain) + ingestion.

C'est le chaînon « opérationnel ». Par défaut **dry-run** : il liste ce qui
serait envoyé et ne touche à rien. L'envoi réel exige `confirm=True` ET un
transport explicite (SMTP du domaine dédié, ou export de fichiers .eml).

Garde-fous à l'envoi :
- on n'envoie que les messages `scheduled` dont `scheduled_at <= jour` ;
- on saute les emails présents en liste de suppression ;
- on respecte le plafond du jour (warm-up) en comptant les `sent` déjà émis ce jour ;
- à chaque envoi réussi : event `sent` + message `status='sent'` + contact `contacted`.

Ingestion : `ingest_event` enregistre open/reply/bounce/optout/click venant de
l'extérieur (webhook ESP ou poll IMAP — câblage = infra, hors de ce module).
"""
from __future__ import annotations

import argparse
import os
import re
import smtplib
import sqlite3
import ssl
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Callable

from . import db as _db
from . import replies as _replies
from .logging_setup import get_logger
from .sequence import cap_for_day, warmup_caps
from .templates import MessageContext, lint_claims, unfilled_placeholders

logger = get_logger("datareno.sender")

# Un transport prend (email, subject, body) et renvoie True si l'envoi a réussi.
Transport = Callable[[str, str, str], bool]

# Coupe-circuit bounce-rate (A4) : ne s'active qu'au-delà de cet échantillon d'envois.
BOUNCE_MIN_SAMPLE = 50


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def due_messages(conn: sqlite3.Connection, on_date: date) -> list[sqlite3.Row]:
    """Messages programmés dus à `on_date` (inclus), contact non supprimé."""
    return conn.execute(
        """
        SELECT m.id AS message_id, m.contact_id, m.subject, m.body, c.email
        FROM messages m JOIN contacts c ON c.id = m.contact_id
        WHERE m.status = 'scheduled' AND m.scheduled_at <= ?
          AND c.email NOT IN (SELECT email FROM suppressions)
        ORDER BY m.scheduled_at, m.id
        """,
        (on_date.isoformat(),),
    ).fetchall()


def _sent_today(conn: sqlite3.Connection, on_date: date) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM events WHERE type='sent' AND substr(created_at,1,10)=?",
        (on_date.isoformat(),),
    ).fetchone()[0]


def auto_day_index(conn: sqlite3.Connection, on_date: date) -> int:
    """Position warm-up = nombre de jours DISTINCTS déjà envoyés avant `on_date`.

    Défensif (A1) : remplace le `day_index` codé en dur. Si l'envoi passe par l'ESP
    (aucun event `sent` écrit), reste à 0 → plafond bas 30/j, jamais le plateau 100.
    """
    return conn.execute(
        "SELECT COUNT(DISTINCT substr(created_at,1,10)) FROM events "
        "WHERE type='sent' AND substr(created_at,1,10) < ?",
        (on_date.isoformat(),),
    ).fetchone()[0]


def bounce_stats(conn: sqlite3.Connection) -> tuple[int, int, float]:
    """(envois, bounces, taux) sur tout l'historique d'envoi connu du tool."""
    sent = conn.execute("SELECT COUNT(*) FROM events WHERE type='sent'").fetchone()[0]
    bounced = conn.execute("SELECT COUNT(*) FROM events WHERE type='bounce'").fetchone()[0]
    return sent, bounced, (bounced / sent if sent else 0.0)


def send_due(
    conn: sqlite3.Connection,
    on_date: date | None = None,
    transport: Transport | None = None,
    *,
    confirm: bool = False,
    caps: tuple[int, int, int] | None = None,
    day_index: int | None = None,
    bounce_limit: float | None = None,
    bounce_min_sample: int = BOUNCE_MIN_SAMPLE,
    limit: int | None = None,
) -> dict[str, int]:
    """Envoie les messages dus (si confirm + transport), sinon simule (dry-run).

    `day_index` situe `on_date` dans le warm-up (0 = J1). Par défaut **auto** (A1) :
    déduit du nombre de jours déjà envoyés (cf. `auto_day_index`). Un entier explicite
    force la valeur (override de test / rattrapage manuel).

    `limit` plafonne le nombre d'envois de CE batch, sous le plafond warm-up (mode
    micro-lot : 1ᵉʳ envoi test contrôlé à 20-30 avant la montée en volume).
    """
    on_date = on_date or date.today()
    caps = caps or warmup_caps()
    if day_index is None:
        day_index = auto_day_index(conn, on_date)
    cap = cap_for_day(day_index, caps)
    remaining = max(0, cap - _sent_today(conn, on_date))
    if limit is not None:
        remaining = min(remaining, max(0, limit))

    due = due_messages(conn, on_date)
    # Garde-fous à l'envoi (derniers filets, juste avant que ça parte) :
    #  B1 — jamais de placeholder « [..] » non renseigné (opt-out / CTA morts) ;
    #  B5 — re-lint des claims : un corps édité après génération ne contourne pas la DGCCRF.
    sendable: list[sqlite3.Row] = []
    blocked_placeholder = 0
    blocked_claim = 0
    for row in due:
        if unfilled_placeholders(row["body"]):
            blocked_placeholder += 1
        elif lint_claims(f"{row['subject']}\n{row['body']}"):
            blocked_claim += 1
        else:
            sendable.append(row)
    dry_run = not (confirm and transport is not None)

    result = {"due": len(due), "cap": cap, "day_index": day_index,
              "remaining_cap": remaining, "sent": 0, "failed": 0, "skipped_cap": 0,
              "blocked_placeholder": blocked_placeholder, "blocked_claim": blocked_claim,
              "dry_run": int(dry_run)}

    if dry_run:
        result["would_send"] = min(len(sendable), remaining)
        logger.info("send dry-run", extra={"context": result})
        return result

    # Coupe-circuit A4 : bounce-rate trop élevé → on stoppe tout envoi (domaine en danger).
    if bounce_limit is None:
        bounce_limit = _env_float("BOUNCE_RATE_LIMIT", 0.05)
    sent_total, _bounced, rate = bounce_stats(conn)
    if sent_total >= bounce_min_sample and rate > bounce_limit:
        result["circuit_breaker"] = "bounce_rate"
        result["bounce_rate"] = round(rate, 4)
        logger.warning("coupe-circuit bounce-rate", extra={"context": result})
        return result

    for row in sendable:
        if result["sent"] >= remaining:
            result["skipped_cap"] = len(sendable) - result["sent"]
            break
        ok = False
        try:
            ok = transport(row["email"], row["subject"], row["body"])
        except Exception:  # noqa: BLE001 — un envoi raté ne doit pas tuer le batch
            ok = False
        if not ok:
            result["failed"] += 1
            continue
        now = _db._now()
        conn.execute("UPDATE messages SET status='sent' WHERE id=?", (row["message_id"],))
        conn.execute(
            "INSERT INTO events (contact_id, message_id, type, created_at) VALUES (?, ?, 'sent', ?)",
            (row["contact_id"], row["message_id"], now),
        )
        conn.execute(
            "UPDATE contacts SET status='contacted', updated_at=? WHERE id=? AND status='new'",
            (now, row["contact_id"]),
        )
        result["sent"] += 1
    conn.commit()
    logger.info("send réel", extra={"context": result})
    return result


def send_one(
    conn: sqlite3.Connection,
    message_id: int,
    transport: Transport | None = None,
    *,
    confirm: bool = False,
    on_date: date | None = None,
    bounce_limit: float | None = None,
    bounce_min_sample: int = BOUNCE_MIN_SAMPLE,
    caps: tuple[int, int, int] | None = None,
    day_index: int | None = None,
) -> dict[str, object]:
    """Envoie UN message précis (clic humain depuis le panneau), avec les MÊMES
    garde-fous que `send_due`. Renvoie `{"status": ...}` (jamais d'exception métier).

    status possibles : not_found · already_sent · suppressed · blocked_placeholder ·
    blocked_claim · simulated (dry-run) · circuit_breaker · cap_reached · failed · sent.
    """
    on_date = on_date or date.today()
    row = conn.execute(
        "SELECT m.id AS message_id, m.contact_id, m.subject, m.body, m.status, c.email "
        "FROM messages m JOIN contacts c ON c.id = m.contact_id WHERE m.id = ?",
        (message_id,),
    ).fetchone()
    if row is None:
        return {"status": "not_found"}
    if row["status"] == "sent":
        return {"status": "already_sent"}

    # Suppression (opt-out / bounce) : on ne renvoie jamais à un contact supprimé.
    if conn.execute("SELECT 1 FROM suppressions WHERE email = ?", (row["email"],)).fetchone():
        return {"status": "suppressed"}
    # B1 — placeholder non renseigné ; B5 — re-lint claims (corps édité à la main).
    if unfilled_placeholders(row["body"]):
        return {"status": "blocked_placeholder"}
    if lint_claims(f"{row['subject']}\n{row['body']}"):
        return {"status": "blocked_claim"}

    if not (confirm and transport is not None):
        return {"status": "simulated"}

    # A4 — coupe-circuit bounce-rate (protège la réputation du domaine).
    if bounce_limit is None:
        bounce_limit = _env_float("BOUNCE_RATE_LIMIT", 0.05)
    sent_total, _bounced, rate = bounce_stats(conn)
    if sent_total >= bounce_min_sample and rate > bounce_limit:
        return {"status": "circuit_breaker", "bounce_rate": round(rate, 4)}

    # Plafond warm-up du jour (même logique d'auto-index que le batch).
    caps = caps or warmup_caps()
    if day_index is None:
        day_index = auto_day_index(conn, on_date)
    if cap_for_day(day_index, caps) - _sent_today(conn, on_date) <= 0:
        return {"status": "cap_reached"}

    try:
        ok = transport(row["email"], row["subject"], row["body"])
    except Exception:  # noqa: BLE001 — un envoi raté ne lève pas, on le signale
        ok = False
    if not ok:
        return {"status": "failed"}

    now = _db._now()
    conn.execute("UPDATE messages SET status='sent' WHERE id=?", (message_id,))
    conn.execute(
        "INSERT INTO events (contact_id, message_id, type, created_at) VALUES (?, ?, 'sent', ?)",
        (row["contact_id"], message_id, now),
    )
    conn.execute(
        "UPDATE contacts SET status='contacted', updated_at=? WHERE id=? AND status='new'",
        (now, row["contact_id"]),
    )
    conn.commit()
    logger.info("send unitaire", extra={"context": {"message_id": message_id, "status": "sent"}})
    return {"status": "sent"}


# Anti header-injection : un CR/LF dans une valeur d'en-tête permettrait d'injecter
# des en-têtes arbitraires (Bcc…). EmailMessage refuse déjà ; on neutralise partout.
_HEADER_UNSAFE = re.compile(r"[\r\n]+")


def _safe_header(value: str) -> str:
    return _HEADER_UNSAFE.sub(" ", value or "").strip()


def export_transport(outdir: str | Path) -> Transport:
    """Transport « export » : écrit un .eml par message (l'humain envoie via l'ESP)."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    counter = {"i": 0}

    def _send(email: str, subject: str, body: str) -> bool:
        counter["i"] += 1
        path = out / f"{counter['i']:06d}.eml"
        path.write_text(
            f"To: {_safe_header(email)}\nSubject: {_safe_header(subject)}\n\n{body}\n",
            encoding="utf-8",
        )
        return True

    return _send


# --- Transport SMTP réel (domaine dédié) -----------------------------------
@dataclass
class SmtpConfig:
    """Paramètres SMTP du domaine dédié (jamais en dur : .env uniquement)."""
    host: str
    user: str
    password: str
    from_email: str
    port: int = 587
    starttls: bool = True
    unsubscribe_mailto: str | None = None
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        domain = os.getenv("SENDING_DOMAIN", "").strip()
        from_email = os.getenv("SENDER_EMAIL", "").strip() or (f"contact@{domain}" if domain else "")
        unsub = os.getenv("UNSUBSCRIBE_MAILTO", "").strip() or (
            f"unsubscribe@{domain}" if domain else None
        )
        return cls(
            host=os.getenv("SMTP_HOST", "").strip(),
            user=os.getenv("SMTP_USER", "").strip(),
            password=os.getenv("SMTP_PASSWORD", "").strip(),
            from_email=from_email,
            port=int(os.getenv("SMTP_PORT", "").strip() or 587),
            starttls=(os.getenv("SMTP_STARTTLS", "true").strip().lower() != "false"),
            unsubscribe_mailto=unsub,
        )

    def missing(self) -> list[str]:
        """Champs requis non renseignés (refus d'envoi tant que non vide)."""
        return [name for name, val in (
            ("SMTP_HOST", self.host), ("SMTP_USER", self.user),
            ("SMTP_PASSWORD", self.password), ("SENDER_EMAIL/SENDING_DOMAIN", self.from_email),
        ) if not val]


def build_mime(
    to_email: str, subject: str, body: str, *,
    from_email: str, sender_name: str, optout_url: str,
    unsubscribe_mailto: str | None = None, domain: str | None = None,
) -> EmailMessage:
    """Construit un email texte conforme délivrabilité + RGPD (List-Unsubscribe)."""
    msg = EmailMessage()
    sender_name = _safe_header(sender_name)
    from_email = _safe_header(from_email)
    msg["From"] = f"{sender_name} <{from_email}>" if sender_name else from_email
    msg["To"] = _safe_header(to_email)
    msg["Subject"] = _safe_header(subject)
    msg["Reply-To"] = from_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=domain or (from_email.split("@")[-1] or None))
    # Opt-out 1-clic : améliore la délivrabilité et matérialise le droit RGPD.
    targets = []
    if unsubscribe_mailto:
        targets.append(f"<mailto:{unsubscribe_mailto}?subject=unsubscribe>")
    if optout_url.startswith("https://"):
        targets.append(f"<{optout_url}>")
    if targets:
        msg["List-Unsubscribe"] = ", ".join(targets)
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(body)
    return msg


# Un connecteur ouvre une session SMTP prête à `send_message` (context manager).
SmtpConnector = Callable[[SmtpConfig], AbstractContextManager]


def _default_smtp_connect(cfg: SmtpConfig) -> smtplib.SMTP:
    """Ouvre une session SMTP réelle (STARTTLS par défaut), authentifiée, avec timeout.

    Contexte TLS explicite : sans lui, smtplib (Py 3.11) n'effectue PAS la
    vérification du certificat serveur → identifiants exposés à un MITM.
    """
    tls = ssl.create_default_context()
    if cfg.starttls:
        smtp = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout)
        smtp.starttls(context=tls)
    else:  # port 465 : TLS implicite
        smtp = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout, context=tls)
    smtp.login(cfg.user, cfg.password)
    return smtp


def smtp_transport(
    cfg: SmtpConfig, ctx: MessageContext, *, connector: SmtpConnector | None = None
) -> Transport:
    """Transport SMTP réel. `connector` injectable (test sans réseau)."""
    connector = connector or _default_smtp_connect

    def _send(email: str, subject: str, body: str) -> bool:
        msg = build_mime(
            email, subject, body, from_email=cfg.from_email, sender_name=ctx.sender_name,
            optout_url=ctx.optout_url, unsubscribe_mailto=cfg.unsubscribe_mailto,
        )
        try:
            with connector(cfg) as smtp:
                smtp.send_message(msg)
            return True
        except Exception:  # noqa: BLE001 — un échec d'envoi ne tue pas le batch
            logger.warning("échec SMTP")  # aucune PII (pas d'email en log)
            return False

    return _send


def ingest_event(
    conn: sqlite3.Connection, email: str, event_type: str, payload: str | None = None
) -> dict[str, object]:
    """Enregistre un retour externe (open/reply/bounce/optout/click) et applique l'arrêt."""
    row = conn.execute("SELECT id FROM contacts WHERE email=?", (email.lower(),)).fetchone()
    if not row:
        return {"ok": False, "reason": "contact_inconnu"}
    contact_id = row["id"]
    conn.execute(
        "INSERT INTO events (contact_id, type, payload, created_at) VALUES (?, ?, ?, ?)",
        (contact_id, event_type, payload, _db._now()),
    )
    conn.commit()
    # bounce / optout déclenchent immédiatement la suppression + annulation.
    if event_type == "bounce":
        _replies.apply_action(conn, contact_id, _replies.BOUNCE)
    elif event_type == "optout":
        _replies.suppress(conn, email, "optout")
        _replies.cancel_pending(conn, contact_id)
        conn.execute("UPDATE contacts SET status='stopped', updated_at=? WHERE id=?",
                     (_db._now(), contact_id))
        conn.commit()
    return {"ok": True, "contact_id": contact_id, "type": event_type}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Connecteur d'envoi (dry-run par défaut).")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    parser.add_argument("--date", default=None, help="Jour d'envoi AAAA-MM-JJ (défaut: aujourd'hui).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send", help="Envoie les messages dus (dry-run sauf --confirm).")
    s.add_argument("--confirm", action="store_true", help="Envoi réel (sinon simulation).")
    transport_grp = s.add_mutually_exclusive_group()
    transport_grp.add_argument("--export-dir", default=None, help="Mode export .eml vers ce dossier.")
    transport_grp.add_argument("--smtp", action="store_true",
                               help="Transport SMTP réel du domaine dédié (config .env).")
    s.add_argument("--day-index", type=int, default=None,
                   help="Position warm-up (0=J1). Défaut: auto (déduit des envois passés).")
    s.add_argument("--limit", type=int, default=None,
                   help="Plafonne ce batch (mode micro-lot : ex. 20 pour le 1ᵉʳ test).")
    i = sub.add_parser("ingest", help="Enregistre un retour externe.")
    i.add_argument("email")
    i.add_argument("type", choices=("open", "reply", "bounce", "optout", "click"))
    i.add_argument("--payload", default=None)
    args = parser.parse_args(argv)

    on_date = date.fromisoformat(args.date) if args.date else date.today()
    conn = _db.connect(args.db)
    try:
        if args.cmd == "send":
            if args.smtp:
                cfg = SmtpConfig.from_env()
                missing = cfg.missing()
                if missing and args.confirm:
                    print(f"⛔ SMTP non configuré : {', '.join(missing)}. Aucun envoi.")  # noqa: T201
                    return 2
                transport = smtp_transport(cfg, MessageContext.from_env())
            elif args.export_dir:
                transport = export_transport(args.export_dir)
            else:
                transport = None
            r = send_due(conn, on_date, transport, confirm=args.confirm,
                         day_index=args.day_index, limit=args.limit)
            if r["dry_run"]:
                print(  # noqa: T201
                    f"DRY-RUN — dus={r['due']} · enverrait={r.get('would_send', 0)} "
                    f"(warm-up J{r['day_index']}, plafond restant {r['remaining_cap']}/{r['cap']}) "
                    f"· bloqués placeholder={r['blocked_placeholder']}. Aucun envoi.\n"
                    "Ajoutez --confirm + --export-dir (ou un transport SMTP) pour envoyer."
                )
            elif r.get("circuit_breaker"):
                print(  # noqa: T201
                    f"⛔ ENVOI BLOQUÉ — coupe-circuit {r['circuit_breaker']} "
                    f"(bounce-rate {r.get('bounce_rate')}). Aucun envoi : vérifiez la qualité de la base."
                )
            else:
                print(  # noqa: T201
                    f"ENVOI — envoyés={r['sent']} · échecs={r['failed']} · "
                    f"non envoyés (plafond)={r['skipped_cap']} · "
                    f"bloqués placeholder={r['blocked_placeholder']} · "
                    f"warm-up J{r['day_index']} (plafond {r['cap']})"
                )
        elif args.cmd == "ingest":
            r = ingest_event(conn, args.email, args.type, args.payload)
            print(f"Ingestion : {r}")  # noqa: T201
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
