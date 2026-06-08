"""dashboard — Phase 9 (optionnel) : vue HTML statique de l'état du pipeline.

Génère un fichier HTML autonome à partir du SQLite : funnel, comptes par segment,
statuts des messages, et un extrait de la file de validation (drafts dus). Pas de
serveur, pas de JS : simple lecture, ouverture dans un navigateur.

CLI :
    python -m src.dashboard out/dashboard.html [--db state.sqlite]
"""
from __future__ import annotations

import argparse
import html
import sqlite3
from datetime import date
from pathlib import Path

from . import db as _db
from . import report as _report
from .sender import due_messages


def _rows(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return conn.execute(sql).fetchall()


def _table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_html(conn: sqlite3.Connection, on_date: date | None = None) -> str:
    on_date = on_date or date.today()
    funnel = _report.funnel(conn)
    kpis = _report.kpis(conn)

    segs = _rows(conn, "SELECT segment, COUNT(*) c FROM contacts GROUP BY segment ORDER BY c DESC")
    msg = _rows(conn, "SELECT status, COUNT(*) c FROM messages GROUP BY status ORDER BY c DESC")
    sup = conn.execute("SELECT COUNT(*) FROM suppressions").fetchone()[0]
    due = due_messages(conn, on_date)

    funnel_tbl = _table(["Étape", "Valeur"], [[k, v] for k, v in funnel.items()])
    kpis_tbl = _table(["KPI", "Valeur"], [[k, v] for k, v in kpis.items()])
    seg_tbl = _table(["Segment", "Contacts"], [[r["segment"], r["c"]] for r in segs])
    msg_tbl = _table(["Statut message", "Nombre"], [[r["status"], r["c"]] for r in msg])
    due_tbl = _table(
        ["contact_id", "objet"],
        [[r["contact_id"], r["subject"]] for r in due[:50]],
    )

    style = (
        "body{font-family:system-ui,Arial,sans-serif;margin:2rem;color:#1b1b1b}"
        "h1{font-size:1.4rem}h2{margin-top:1.6rem;font-size:1.05rem;color:#0a5}"
        "table{border-collapse:collapse;margin:.4rem 0}"
        "th,td{border:1px solid #ddd;padding:.3rem .6rem;text-align:left;font-size:.9rem}"
        "th{background:#f3f6f4}.muted{color:#666;font-size:.85rem}"
    )
    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        f"<title>DATA RÉNO — pipeline</title><style>{style}</style></head><body>"
        f"<h1>DATA RÉNO — état du pipeline</h1>"
        f"<p class='muted'>Généré le {on_date.isoformat()} · suppressions : {sup}</p>"
        f"<h2>Funnel</h2>{funnel_tbl}"
        f"<h2>KPIs</h2>{kpis_tbl}"
        f"<h2>Contacts par segment</h2>{seg_tbl}"
        f"<h2>Messages par statut</h2>{msg_tbl}"
        f"<h2>File de validation — drafts dus (max 50)</h2>{due_tbl}"
        "</body></html>"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dashboard HTML statique (lecture SQLite).")
    parser.add_argument("output", help="Chemin du fichier HTML à écrire.")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    args = parser.parse_args(argv)
    conn = _db.connect(args.db)
    try:
        Path(args.output).write_text(build_html(conn), encoding="utf-8")
    finally:
        conn.close()
    print(f"Dashboard écrit → {args.output}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
