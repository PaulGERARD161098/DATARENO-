"""scoring — Phase 10 : scoring d'engagement (priorisation commerciale).

À partir du journal d'events, classe chaque contact dans un palier d'engagement
(du plus chaud au plus froid) et fait remonter les **leads chauds** : ceux qui ont
cliqué le CTA sans encore répondre — la priorité absolue d'un humain.

Paliers (signal le plus fort prime) :
    PERDU < EN_FILE < DELIVRE < OUVREUR < CLIQUEUR < REPONDU < RDV
- RDV       : a pris rendez-vous (gagné).
- REPONDU   : a répondu (à traiter / classer).
- CLIQUEUR  : a cliqué le lien Calendly sans répondre → **lead chaud à relancer**.
- OUVREUR   : a ouvert sans cliquer → tiède.
- DELIVRE   : a reçu au moins un envoi, sans ouverture connue.
- EN_FILE   : pas encore d'envoi.
- PERDU     : supprimé (STOP / bounce / opt-out / hygiène) ou exclu.

Lecture seule (aucun envoi, aucun effet de bord). Pas de PII dans les logs.

CLI :
    python -m src.scoring report [--db state.sqlite] [--top 20]
"""
from __future__ import annotations

import argparse
import sqlite3

from . import db as _db

# Ordre du plus froid au plus chaud (sert au tri).
TIERS = ("PERDU", "EN_FILE", "DELIVRE", "OUVREUR", "CLIQUEUR", "REPONDU", "RDV")
TIER_RANK = {t: i for i, t in enumerate(TIERS)}

_FLAGS_SQL = """
SELECT
  c.id AS id, c.email AS email, c.status AS status,
  (c.email IN (SELECT email FROM suppressions)) AS suppressed,
  EXISTS(SELECT 1 FROM events e WHERE e.contact_id=c.id AND e.type='sent')  AS has_sent,
  EXISTS(SELECT 1 FROM events e WHERE e.contact_id=c.id AND e.type='open')  AS has_open,
  EXISTS(SELECT 1 FROM events e WHERE e.contact_id=c.id AND e.type='click') AS has_click,
  EXISTS(SELECT 1 FROM events e WHERE e.contact_id=c.id AND e.type='reply') AS has_reply,
  EXISTS(SELECT 1 FROM events e WHERE e.contact_id=c.id AND e.type='rdv')   AS has_rdv
FROM contacts c
"""


def _tier_from_flags(row: sqlite3.Row) -> str:
    if row["suppressed"] or row["status"] in ("stopped", "bounced", "excluded"):
        return "PERDU"
    if row["has_rdv"] or row["status"] == "rdv":
        return "RDV"
    if row["has_reply"]:
        return "REPONDU"
    if row["has_click"]:
        return "CLIQUEUR"
    if row["has_open"]:
        return "OUVREUR"
    if row["has_sent"]:
        return "DELIVRE"
    return "EN_FILE"


def tiers_summary(conn: sqlite3.Connection) -> dict[str, int]:
    """Compte de contacts par palier d'engagement (tous paliers présents, même à 0)."""
    counts = {t: 0 for t in TIERS}
    for row in conn.execute(_FLAGS_SQL):
        counts[_tier_from_flags(row)] += 1
    return counts


def hot_leads(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, object]]:
    """Leads chauds = CLIQUEUR (a cliqué, pas répondu, non supprimé), les plus récents."""
    out: list[dict[str, object]] = []
    for row in conn.execute(_FLAGS_SQL):
        if _tier_from_flags(row) != "CLIQUEUR":
            continue
        last = conn.execute(
            "SELECT MAX(created_at) FROM events WHERE contact_id=? AND type='click'",
            (row["id"],),
        ).fetchone()[0]
        out.append({"contact_id": row["id"], "email": row["email"], "dernier_clic": last})
    out.sort(key=lambda d: d["dernier_clic"] or "", reverse=True)
    return out[:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scoring d'engagement (priorisation commerciale).")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report", help="Paliers d'engagement + leads chauds à relancer.")
    r.add_argument("--top", type=int, default=20, help="Nombre de leads chauds à lister.")
    args = parser.parse_args(argv)

    conn = _db.connect(args.db)
    try:
        counts = tiers_summary(conn)
        hot = hot_leads(conn, args.top)
    finally:
        conn.close()

    print("=== Paliers d'engagement (froid → chaud) ===")  # noqa: T201
    for t in TIERS:
        print(f"  {t:10}: {counts[t]}")  # noqa: T201
    print(f"\n=== Leads chauds — cliqueurs sans réponse (top {args.top}) ===")  # noqa: T201
    if not hot:
        print("  (aucun pour l'instant)")  # noqa: T201
    for h in hot:
        print(f"  #{h['contact_id']:<6} {h['email']:32} dernier clic {h['dernier_clic']}")  # noqa: T201
    print("\nPriorité humaine : relancer les cliqueurs (ils ont montré l'intention, pas encore booké).")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
