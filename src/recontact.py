"""recontact — remise en file automatique des contacts « à recontacter à 3 mois ».

Quand une réponse est classée RECONTACTER, `replies` pose `status='recontact_3m'`
et `recontact_at = +3 mois`. Ce module relève les contacts dont la date est échue
et les **réarme pour une nouvelle séquence** :

- on pose un event `requeue` (marqueur qui réinitialise l'horloge des arrêts, cf.
  `sequence._stopped_contacts`) — l'ancienne réponse « recontactez-moi » ne bloque
  donc plus la planification ;
- on remet toutes les touches du contact en `draft` (séquence repartie de zéro) ;
- on repasse le contact en `status='new'`, `recontact_at=NULL`.

Les contacts en liste de suppression (STOP/bounce/optout) ne sont jamais réarmés.
Aucun envoi déclenché : `requeue` prépare, c'est `sequence plan` (option `--and-plan`)
puis l'envoi humain qui font le reste. Aucune PII dans les logs.

CLI :
    python -m src.recontact requeue [--db state.sqlite] [--and-plan]
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date

from . import db as _db
from .logging_setup import get_logger

logger = get_logger("datareno.recontact")


def due_recontacts(conn: sqlite3.Connection, on_date: date) -> list[int]:
    """Ids des contacts dont la date de recontact est échue (et non supprimés)."""
    rows = conn.execute(
        """
        SELECT id FROM contacts
        WHERE status = 'recontact_3m'
          AND recontact_at IS NOT NULL AND recontact_at <= ?
          AND email NOT IN (SELECT email FROM suppressions)
        ORDER BY id
        """,
        (on_date.isoformat(),),
    ).fetchall()
    return [r["id"] for r in rows]


def requeue(conn: sqlite3.Connection, on_date: date | None = None) -> dict[str, int]:
    """Réarme les contacts dont la date de recontact est échue. Idempotent."""
    on_date = on_date or date.today()
    ids = due_recontacts(conn, on_date)
    now = _db._now()
    for cid in ids:
        # Marqueur de remise en file : neutralise les arrêts antérieurs.
        conn.execute(
            "INSERT INTO events (contact_id, type, created_at) VALUES (?, 'requeue', ?)",
            (cid, now),
        )
        # Réarme toutes les touches (nouvelle séquence complète).
        conn.execute(
            "UPDATE messages SET status='draft', scheduled_at=NULL WHERE contact_id=?", (cid,)
        )
        conn.execute(
            "UPDATE contacts SET status='new', recontact_at=NULL, updated_at=? WHERE id=?",
            (now, cid),
        )
    conn.commit()
    result = {"requeued": len(ids)}
    logger.info("remise en file recontact", extra={"context": result})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remise en file des contacts à recontacter (sans envoi).")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    rq = sub.add_parser("requeue", help="Réarme les contacts dont la date de recontact est échue.")
    rq.add_argument("--and-plan", action="store_true",
                    help="Replanifie la séquence dans la foulée (sinon : lancer `src.sequence plan`).")
    args = parser.parse_args(argv)

    conn = _db.connect(args.db)
    try:
        r = requeue(conn)
        msg = f"Remis en file : {r['requeued']} contact(s)."
        if args.and_plan:
            from . import sequence  # import local : évite un cycle au chargement
            p = sequence.plan_sequence(conn)
            msg += f" Replanifié — messages programmés (total)={p['scheduled_messages']}."
        else:
            msg += " Lancez `python -m src.sequence plan` pour les replanifier."
        print(msg)  # noqa: T201
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
