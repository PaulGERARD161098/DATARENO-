"""daily — geste opérationnel quotidien (un seul appel).

Enchaîne, dans le bon ordre :
  1. **Ingestion des retours** (poll IMAP) — pour que STOP / bounce / réponses soient
     appliqués AVANT de sélectionner les envois du jour (suppression & annulation
     prises en compte immédiatement) ;
  2. **Envoi du dû** via `sender.send_due`, derrière tous les garde-fous (warm-up auto,
     refus placeholders, suppression, coupe-circuit bounce).

Dry-run par défaut (aucun transport → aucune sortie). Réseau isolé : `imap_fetcher`
et `transport` sont injectables → testable sans connexion. Aucune PII dans les logs.

CLI :
    python -m src.daily run [--db state.sqlite]
    python -m src.daily run --confirm --smtp            # ingestion + envoi réels
    python -m src.daily run --confirm --export-dir out/outbox
    python -m src.daily run --no-poll                   # n'ingère pas, simule l'envoi
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date

from . import db as _db
from . import inbox as _inbox
from . import sender as _sender
from .logging_setup import get_logger
from .templates import MessageContext

logger = get_logger("datareno.daily")


def run_daily(
    conn: sqlite3.Connection,
    *,
    on_date: date | None = None,
    transport: _sender.Transport | None = None,
    confirm: bool = False,
    imap_cfg: _inbox.ImapConfig | None = None,
    imap_fetcher: _inbox.Fetcher | None = None,
    day_index: int | None = None,
) -> dict[str, object]:
    """Ingère les retours (si IMAP configuré) puis envoie le dû du jour."""
    on_date = on_date or date.today()
    summary: dict[str, object] = {"inbox": None, "send": None}

    # 1. Retours d'abord : un STOP/bounce arrivé doit bloquer l'envoi du jour même.
    if imap_cfg is not None and not imap_cfg.missing():
        summary["inbox"] = _inbox.poll_inbox(conn, imap_cfg, fetcher=imap_fetcher)

    # 2. Envoi du dû (dry-run si pas de transport/confirm).
    summary["send"] = _sender.send_due(
        conn, on_date, transport, confirm=confirm, day_index=day_index
    )
    logger.info("run quotidien", extra={"context": {
        "polled": summary["inbox"] is not None,
        "sent": summary["send"].get("sent", 0),
        "dry_run": summary["send"].get("dry_run"),
    }})
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run quotidien : ingestion des retours + envoi du dû.")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="Ingère les retours (IMAP) puis envoie le dû du jour.")
    run.add_argument("--confirm", action="store_true", help="Envoi réel (sinon simulation).")
    grp = run.add_mutually_exclusive_group()
    grp.add_argument("--export-dir", default=None, help="Transport export .eml.")
    grp.add_argument("--smtp", action="store_true", help="Transport SMTP du domaine dédié (.env).")
    run.add_argument("--no-poll", action="store_true", help="Ne pas relever la boîte IMAP.")
    run.add_argument("--day-index", type=int, default=None, help="Position warm-up (défaut: auto).")
    args = parser.parse_args(argv)

    # Transport
    if args.smtp:
        smtp_cfg = _sender.SmtpConfig.from_env()
        missing = smtp_cfg.missing()
        if missing and args.confirm:
            print(f"⛔ SMTP non configuré : {', '.join(missing)}. Aucun envoi.")  # noqa: T201
            return 2
        transport = _sender.smtp_transport(smtp_cfg, MessageContext.from_env())
    elif args.export_dir:
        transport = _sender.export_transport(args.export_dir)
    else:
        transport = None

    # Ingestion IMAP (sauf --no-poll et si configurée)
    imap_cfg = None if args.no_poll else _inbox.ImapConfig.from_env()
    if imap_cfg is not None and imap_cfg.missing():
        logger.info("IMAP non configuré : poll ignoré ce jour")
        imap_cfg = None

    conn = _db.connect(args.db)
    try:
        s = run_daily(conn, transport=transport, confirm=args.confirm,
                      imap_cfg=imap_cfg, day_index=args.day_index)
        inbox_s = s["inbox"]
        send_s = s["send"]
        if inbox_s is not None:
            print(  # noqa: T201
                f"Retours — relevés={inbox_s['seen']} · bounces={inbox_s['bounces']} · "
                f"réponses={inbox_s['replies']} · inconnus={inbox_s['unknown']}"
            )
        else:
            print("Retours — poll IMAP ignoré.")  # noqa: T201
        if send_s.get("dry_run"):
            print(  # noqa: T201
                f"Envoi (DRY-RUN) — dus={send_s['due']} · enverrait={send_s.get('would_send', 0)} "
                f"(warm-up J{send_s['day_index']}) · bloqués placeholder={send_s['blocked_placeholder']}."
            )
        elif send_s.get("circuit_breaker"):
            print(  # noqa: T201
                f"⛔ Envoi BLOQUÉ — coupe-circuit {send_s['circuit_breaker']} "
                f"(bounce-rate {send_s.get('bounce_rate')}). Aucun envoi."
            )
        else:
            print(  # noqa: T201
                f"Envoi — envoyés={send_s['sent']} · échecs={send_s['failed']} · "
                f"plafond restant={send_s['remaining_cap']} (warm-up J{send_s['day_index']})."
            )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
