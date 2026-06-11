"""webexport — export d'un instantané AGRÉGÉ de l'état, pour l'interface web (Vercel).

L'interface web est un tableau de bord **en lecture seule**, déployé sur Vercel. Vercel
est sans état : il ne peut pas faire tourner le pipeline (SQLite local, SMTP, IMAP). Ce
module produit donc un `data.json` que la page statique lit. À régénérer après chaque
run (puis re-déployer / committer).

🔒 RGPD : une URL Vercel est publique → **aucune PII** dans l'export. On n'exporte que
des agrégats (funnel, KPIs, paliers, A/B objet, comptes). Les leads chauds nominatifs
restent en local (`python -m src.scoring report`).

CLI :
    python -m src.webexport web/data.json [--db state.sqlite]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from . import db as _db
from . import report as _report
from . import scoring as _scoring
from .sender import due_messages


def build_payload(conn: sqlite3.Connection, on_date: date | None = None) -> dict[str, object]:
    """Construit l'instantané agrégé (sans PII) lu par l'interface web."""
    on_date = on_date or date.today()
    funnel = _report.funnel(conn)
    kpis = _report.kpis(conn)
    tiers = _scoring.tiers_summary(conn)

    ab = [
        {"subject": r["subject"], "sent": r["sent"],
         "open_rate": r["taux_ouverture_%"], "reply_rate": r["taux_reponse_%"]}
        for r in _report.ab_subjects(conn)
    ]
    segments = [
        {"segment": s, "count": c} for s, c in _db.counts_by_segment(conn).items()
    ]
    message_status = [
        {"status": r["status"], "count": r["c"]}
        for r in conn.execute(
            "SELECT status, COUNT(*) c FROM messages GROUP BY status ORDER BY c DESC"
        )
    ]
    suppressions = conn.execute("SELECT COUNT(*) FROM suppressions").fetchone()[0]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "funnel": funnel,
        "kpis": kpis,
        "engagement_tiers": [{"tier": t, "count": tiers[t]} for t in _scoring.TIERS],
        "hot_leads_count": len(_scoring.hot_leads(conn, limit=100000)),
        "ab_subjects": ab,
        "segments": segments,
        "message_status": message_status,
        "suppressions": suppressions,
        "due_today": len(due_messages(conn, on_date)),
    }


def write_json(conn: sqlite3.Connection, path: str | Path, on_date: date | None = None) -> int:
    """Écrit l'instantané. Retourne la taille du fichier en octets."""
    payload = build_payload(conn, on_date)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    p.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export agrégé (sans PII) pour l'interface web.")
    parser.add_argument("output", nargs="?", default="web/data.json", help="Chemin du JSON.")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    args = parser.parse_args(argv)
    conn = _db.connect(args.db)
    try:
        n = write_json(conn, args.output)
    finally:
        conn.close()
    print(f"Export web écrit → {args.output} ({n} octets, agrégats sans PII).")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
