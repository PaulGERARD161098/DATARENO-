"""dashboard — Phase 9 (optionnel) : vue HTML statique de l'état du pipeline.

Génère un fichier HTML autonome à partir du SQLite : rangée de KPI tiles
(taux d'ouverture / réponse / RDV + funnel clé), funnel détaillé, comptes par
segment et par statut, suppressions par raison, réponses par classe, et la file
de validation (drafts dus, avec email et date d'envoi prévue). Pas de serveur,
pas de JS, aucune ressource externe : CSS inline, ouverture dans un navigateur.

Sécurité : toute valeur dynamique passe par html.escape (garde-fou XSS — les
données SQLite sont considérées non sûres). L'email apparaît dans le HTML
(usage métier local), jamais dans les logs.

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

# Palette neutre (chrome & encre), contraste AA sur surface claire.
# Accent bleu réservé aux éléments non-texte (liseré des tiles).
_STYLE = """
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;
--hairline:#e1e0d9;--border:rgba(11,11,11,.10);--accent:#2a78d6;--zebra:#f4f3ef}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:1.5rem 1.25rem 3rem}
header{border-bottom:1px solid var(--hairline);padding-bottom:.9rem;margin-bottom:1.25rem}
h1{font-size:1.35rem;margin:0 0 .25rem;letter-spacing:-.01em}
.meta{color:var(--ink-2);font-size:.85rem;margin:0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:.75rem;margin:0 0 1.25rem}
.tile{background:var(--surface);border:1px solid var(--border);
border-top:3px solid var(--accent);border-radius:8px;padding:.7rem .9rem}
.tile-label{font-size:.72rem;color:var(--ink-2);text-transform:uppercase;
letter-spacing:.04em}
.tile-value{font-size:1.6rem;font-weight:600;margin-top:.15rem}
section{background:var(--surface);border:1px solid var(--border);
border-radius:8px;padding:1rem 1.1rem;margin:0 0 1rem}
h2{font-size:.95rem;margin:0 0 .6rem}
table{border-collapse:collapse;width:100%;font-size:.875rem}
th{color:var(--ink-2);font-size:.72rem;text-transform:uppercase;
letter-spacing:.04em;text-align:left;padding:.35rem .6rem;
border-bottom:1px solid var(--hairline)}
td{padding:.35rem .6rem}
tbody tr:nth-child(even){background:var(--zebra)}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
.empty{color:var(--ink-2);font-size:.85rem;margin:.2rem 0}
"""


def _rows(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return conn.execute(sql).fetchall()


def _table(
    headers: list[str],
    rows: list[list[object]],
    num_cols: frozenset[int] = frozenset(),
    empty: str = "(aucune donnée)",
) -> str:
    """Tableau HTML échappé ; `num_cols` = index des colonnes numériques (alignées à droite)."""
    if not rows:
        return f"<p class='empty'>{html.escape(empty)}</p>"

    def _cls(i: int) -> str:
        return " class='num'" if i in num_cols else ""

    head = "".join(f"<th{_cls(i)}>{html.escape(str(h))}</th>" for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f"<td{_cls(i)}>{html.escape(str(c))}</td>" for i, c in enumerate(r)) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _tile(label: str, value: object) -> str:
    """KPI tile : libellé + valeur (tout est échappé)."""
    return (
        "<div class='tile'>"
        f"<div class='tile-label'>{html.escape(str(label))}</div>"
        f"<div class='tile-value'>{html.escape(str(value))}</div>"
        "</div>"
    )


def _section(title: str, inner: str) -> str:
    return f"<section><h2>{html.escape(title)}</h2>{inner}</section>"


def build_html(conn: sqlite3.Connection, on_date: date | None = None) -> str:
    on_date = on_date or date.today()
    funnel = _report.funnel(conn)
    kpis = _report.kpis(conn)

    segs = _rows(conn, "SELECT segment, COUNT(*) c FROM contacts GROUP BY segment ORDER BY c DESC")
    msg = _rows(conn, "SELECT status, COUNT(*) c FROM messages GROUP BY status ORDER BY c DESC")
    sup_total = conn.execute("SELECT COUNT(*) FROM suppressions").fetchone()[0]
    sup = _rows(conn, "SELECT reason, COUNT(*) c FROM suppressions GROUP BY reason ORDER BY c DESC")
    rep = _rows(
        conn,
        "SELECT payload, COUNT(*) c FROM events WHERE type='reply' "
        "GROUP BY payload ORDER BY c DESC",
    )
    due = due_messages(conn, on_date)

    tiles = "".join([
        _tile("Messages envoyés", funnel["messages_envoyes"]),
        _tile("Taux d'ouverture", f"{kpis['taux_ouverture_%']} %"),
        _tile("Taux de réponse", f"{kpis['taux_reponse_%']} %"),
        _tile("RDV obtenus", funnel["rdv"]),
        _tile("Taux de RDV", f"{kpis['taux_rdv_%']} %"),
    ])

    funnel_tbl = _table(["Étape", "Valeur"], [[k, v] for k, v in funnel.items()],
                        num_cols=frozenset({1}))
    seg_tbl = _table(["Segment", "Contacts"], [[r["segment"], r["c"]] for r in segs],
                     num_cols=frozenset({1}), empty="(aucun contact)")
    msg_tbl = _table(["Statut message", "Nombre"], [[r["status"], r["c"]] for r in msg],
                     num_cols=frozenset({1}), empty="(aucun message)")
    sup_tbl = _table(["Raison", "Nombre"], [[r["reason"], r["c"]] for r in sup],
                     num_cols=frozenset({1}), empty="(aucune suppression)")
    rep_tbl = _table(
        ["Classe", "Nombre"],
        [[r["payload"] or "(sans classe)", r["c"]] for r in rep],
        num_cols=frozenset({1}), empty="(aucune réponse)",
    )
    due_tbl = _table(
        ["contact_id", "email", "objet", "envoi prévu"],
        [[r["contact_id"], r["email"], r["subject"], r["scheduled_at"]] for r in due[:50]],
        num_cols=frozenset({0}), empty="(aucun draft dû)",
    )

    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>DATA RÉNO — pipeline</title><style>{_STYLE}</style></head><body>"
        "<div class='wrap'>"
        "<header><h1>DATA RÉNO — état du pipeline</h1>"
        f"<p class='meta'>Généré le {html.escape(on_date.isoformat())} · "
        f"suppressions : {sup_total}</p></header>"
        f"<div class='tiles'>{tiles}</div>"
        + _section("Funnel", funnel_tbl)
        + _section("Contacts par segment", seg_tbl)
        + _section("Messages par statut", msg_tbl)
        + _section("Suppressions par raison", sup_tbl)
        + _section("Réponses par classe", rep_tbl)
        + _section("File de validation — drafts dus (max 50)", due_tbl)
        + "</div></body></html>"
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
