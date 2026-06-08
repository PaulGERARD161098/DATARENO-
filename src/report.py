"""report — Phase 7 : reporting & A/B.

Calcule le funnel jusqu'au RDV et compare les objets (A/B). La sortie est une
**recommandation** : l'humain décide, aucune bascule automatique.

Funnel (sur les contacts adressables) :
    programmés → envoyés → ouverts → répondus → RDV
KPIs dérivés : taux d'ouverture, de réponse, de RDV.

A/B objet : pour chaque objet (porté par la position/variant), taux d'ouverture
et de réponse, trié par taux de réponse décroissant.
"""
from __future__ import annotations

import argparse
import sqlite3

from . import db as _db


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def funnel(conn: sqlite3.Connection) -> dict[str, int]:
    """Compte les étapes du funnel à partir de l'état (messages + events)."""
    scheduled = _scalar(conn, "SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','sent')")
    sent = _scalar(conn, "SELECT COUNT(*) FROM messages WHERE status='sent'")
    # Contacts distincts ayant au moins un event du type donné.
    opened = _scalar(conn, "SELECT COUNT(DISTINCT contact_id) FROM events WHERE type='open'")
    replied = _scalar(conn, "SELECT COUNT(DISTINCT contact_id) FROM events WHERE type='reply'")
    rdv = _scalar(conn, "SELECT COUNT(*) FROM contacts WHERE status='rdv'")
    return {
        "messages_programmes": scheduled,
        "messages_envoyes": sent,
        "contacts_ouverts": opened,
        "contacts_repondus": replied,
        "rdv": rdv,
    }


def _rate(num: int, den: int) -> float:
    return round(100 * num / den, 1) if den else 0.0


def kpis(conn: sqlite3.Connection) -> dict[str, float]:
    f = funnel(conn)
    return {
        "taux_ouverture_%": _rate(f["contacts_ouverts"], f["messages_envoyes"]),
        "taux_reponse_%": _rate(f["contacts_repondus"], f["messages_envoyes"]),
        "taux_rdv_%": _rate(f["rdv"], f["messages_envoyes"]),
    }


def ab_subjects(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Performance par objet : envoyés / ouverts / répondus + taux. Trié par réponse."""
    rows = conn.execute(
        """
        SELECT m.subject AS subject,
               COUNT(*) AS sent,
               SUM(CASE WHEN o.n > 0 THEN 1 ELSE 0 END) AS opened,
               SUM(CASE WHEN r.n > 0 THEN 1 ELSE 0 END) AS replied
        FROM messages m
        LEFT JOIN (SELECT message_id, COUNT(*) n FROM events WHERE type='open'  GROUP BY message_id) o
               ON o.message_id = m.id
        LEFT JOIN (SELECT message_id, COUNT(*) n FROM events WHERE type='reply' GROUP BY message_id) r
               ON r.message_id = m.id
        WHERE m.status = 'sent'
        GROUP BY m.subject
        ORDER BY replied * 1.0 / sent DESC, sent DESC
        """
    ).fetchall()
    out = []
    for row in rows:
        sent = row["sent"] or 0
        out.append({
            "subject": row["subject"],
            "sent": sent,
            "opened": row["opened"] or 0,
            "replied": row["replied"] or 0,
            "taux_ouverture_%": _rate(row["opened"] or 0, sent),
            "taux_reponse_%": _rate(row["replied"] or 0, sent),
        })
    return out


def recommend_subject(conn: sqlite3.Connection) -> str | None:
    rows = ab_subjects(conn)
    return rows[0]["subject"] if rows else None


def render_report(conn: sqlite3.Connection) -> str:
    f = funnel(conn)
    k = kpis(conn)
    lines = ["=== Funnel ==="]
    lines += [f"  {key:24}: {val}" for key, val in f.items()]
    lines += ["", "=== KPIs ==="]
    lines += [f"  {key:24}: {val}" for key, val in k.items()]
    lines += ["", "=== A/B objet (trié par taux de réponse) ==="]
    ab = ab_subjects(conn)
    if not ab:
        lines.append("  (aucun message envoyé pour l'instant)")
    for r in ab:
        lines.append(
            f"  « {r['subject']} » — envoyés={r['sent']} · "
            f"ouv={r['taux_ouverture_%']}% · rép={r['taux_reponse_%']}%"
        )
    reco = recommend_subject(conn)
    if reco:
        lines += ["", f"Recommandation (l'humain décide) : « {reco} »"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reporting & A/B (recommandation, pas de bascule auto).")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    args = parser.parse_args(argv)
    conn = _db.connect(args.db)
    try:
        print(render_report(conn))  # noqa: T201
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
