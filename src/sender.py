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
import sqlite3
from datetime import date
from pathlib import Path
from typing import Callable

from . import db as _db
from . import replies as _replies
from .logging_setup import get_logger
from .sequence import cap_for_day, warmup_caps
from .templates import MessageContext

logger = get_logger("datareno.sender")

# Un transport prend (email, subject, body) et renvoie True si l'envoi a réussi.
Transport = Callable[[str, str, str], bool]

# Placeholders par défaut des templates : leur présence signifie que .env est
# incomplet. Envoyer un tel message = opt-out non fonctionnel (RGPD) → refus.
_PLACEHOLDERS = (
    MessageContext.calendly_url,
    MessageContext.optout_url,
    MessageContext.sender_name,
    MessageContext.reassurance,
)


def _has_placeholder(subject: str | None, body: str | None) -> bool:
    text = (subject or "") + "\n" + (body or "")
    return any(p in text for p in _PLACEHOLDERS)


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


def send_due(
    conn: sqlite3.Connection,
    on_date: date | None = None,
    transport: Transport | None = None,
    *,
    confirm: bool = False,
    caps: tuple[int, int, int] | None = None,
    day_index: int = 2,
) -> dict[str, int]:
    """Envoie les messages dus (si confirm + transport), sinon simule (dry-run).

    `day_index` situe `on_date` dans le warm-up (0 = J1). Par défaut 2 (plateau).
    """
    on_date = on_date or date.today()
    caps = caps or warmup_caps()
    cap = cap_for_day(day_index, caps)
    remaining = max(0, cap - _sent_today(conn, on_date))

    due = due_messages(conn, on_date)
    dry_run = not (confirm and transport is not None)

    result = {"due": len(due), "cap": cap, "remaining_cap": remaining,
              "sent": 0, "failed": 0, "skipped_cap": 0, "skipped_placeholder": 0,
              "dry_run": int(dry_run)}

    if dry_run:
        result["would_send"] = min(len(due), remaining)
        logger.info("send dry-run", extra={"context": result})
        return result

    for row in due:
        if result["sent"] >= remaining:
            result["skipped_cap"] = len(due) - result["sent"]
            break
        if _has_placeholder(row["subject"], row["body"]):
            result["skipped_placeholder"] += 1
            logger.warning("message à placeholder non résolu refusé", extra={"context": {
                "message_id": row["message_id"],
            }})
            continue
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


def export_transport(outdir: str | Path) -> Transport:
    """Transport « export » : écrit un .eml par message (l'humain envoie via l'ESP)."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    counter = {"i": 0}

    def _send(email: str, subject: str, body: str) -> bool:
        # Anti header-injection : un email porteur de CR/LF est refusé (données DB
        # considérées non sûres) ; les retours ligne d'un sujet sont repliés.
        if "\r" in email or "\n" in email:
            return False
        subject = " ".join((subject or "").splitlines())
        counter["i"] += 1
        path = out / f"{counter['i']:06d}.eml"
        path.write_text(
            f"To: {email}\nSubject: {subject}\n\n{body}\n", encoding="utf-8"
        )
        return True

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
    s.add_argument("--export-dir", default=None, help="Mode export .eml vers ce dossier.")
    s.add_argument("--day-index", type=int, default=2, help="Position warm-up (0=J1).")
    i = sub.add_parser("ingest", help="Enregistre un retour externe.")
    i.add_argument("email")
    i.add_argument("type", choices=("open", "reply", "bounce", "optout", "click"))
    i.add_argument("--payload", default=None)
    args = parser.parse_args(argv)

    on_date = date.fromisoformat(args.date) if args.date else date.today()
    conn = _db.connect(args.db)
    try:
        if args.cmd == "send":
            transport = export_transport(args.export_dir) if args.export_dir else None
            r = send_due(conn, on_date, transport, confirm=args.confirm, day_index=args.day_index)
            if r["dry_run"]:
                print(  # noqa: T201
                    f"DRY-RUN — dus={r['due']} · enverrait={r.get('would_send', 0)} "
                    f"(plafond restant {r['remaining_cap']}/{r['cap']}). Aucun envoi.\n"
                    "Ajoutez --confirm + --export-dir (ou un transport SMTP) pour envoyer."
                )
            else:
                print(  # noqa: T201
                    f"ENVOI — envoyés={r['sent']} · échecs={r['failed']} · "
                    f"non envoyés (plafond)={r['skipped_cap']} · "
                    f"refusés (placeholder .env manquant)={r['skipped_placeholder']}"
                )
        elif args.cmd == "ingest":
            r = ingest_event(conn, args.email, args.type, args.payload)
            print(f"Ingestion : {r}")  # noqa: T201
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
