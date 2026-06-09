"""drafts — Phase 4 : génération des brouillons.

Produit un brouillon par contact (1 touche, J0 par défaut) dans la table
`messages`, statut `draft`. **Aucun envoi n'est déclenché par le code** : pas
de réseau, pas d'API d'envoi ici. L'envoi est une action humaine (Phases 5+).

Garde-fou : chaque brouillon repasse par le linter avant insertion ; un message
non conforme n'est jamais stocké (il est compté et journalisé, sans PII).

Sorties :
- en base : lignes `messages` (statut `draft`, idempotent sur (contact, position)) ;
- export ESP : CSV mailmerge (email, objet, corps) pour le domaine d'envoi dédié.

CLI :
    python -m src.drafts generate [--db state.sqlite] [--position J0] [--limit N]
    python -m src.drafts export out/drafts_J0.csv [--db state.sqlite] [--position J0]
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from . import config as C
from . import db as _db
from .logging_setup import get_logger
from .templates import (
    POSITIONS,
    MessageContext,
    assign_ab,
    render,
    unfilled_placeholders,
    validate_message,
)

logger = get_logger("datareno.drafts")

EXPORT_FIELDS = ["email", "nom", "segment", "position", "subject", "body"]


def generate_drafts(
    conn: sqlite3.Connection,
    ctx: MessageContext | None = None,
    position: str = "J0",
    segments: tuple[str, ...] = C.ACTIVABLE_SEGMENTS,
    limit: int | None = None,
) -> dict[str, int]:
    """Génère les brouillons (statut `draft`) pour la position donnée. Idempotent."""
    if position not in POSITIONS:
        raise ValueError(f"Position inconnue : {position}")
    ctx = ctx or MessageContext.from_env()
    _db.init_db(conn)

    placeholders = ",".join("?" for _ in segments)
    query = (
        f"SELECT id, segment, dept FROM contacts WHERE segment IN ({placeholders}) ORDER BY id"
    )
    rows = conn.execute(query, segments).fetchall()
    if limit is not None:
        rows = rows[:limit]

    before = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    skipped = 0
    for r in rows:
        # A/B objet : bras stable par contact (toutes ses touches dans le même bras).
        ab = assign_ab(str(r["id"]))
        subject, body = render(r["segment"], position, {"dept": r["dept"] or ""}, ctx, variant=ab)
        violations = validate_message(
            subject, body, calendly_url=ctx.calendly_url, optout_url=ctx.optout_url
        )
        if violations:
            skipped += 1
            logger.warning("draft non conforme ignoré", extra={"context": {
                "segment": r["segment"], "position": position, "violations": violations,
            }})
            continue
        conn.execute(
            """
            INSERT INTO messages (contact_id, position, variant, subject, body, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'draft', ?)
            ON CONFLICT(contact_id, position) DO NOTHING
            """,
            (r["id"], position, f"{r['segment']}:{position}:{ab}", subject, body, _db._now()),
        )
    conn.commit()

    after = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    result = {
        "candidates": len(rows),
        "inserted": after - before,
        "skipped_existing": len(rows) - skipped - (after - before),
        "skipped_noncompliant": skipped,
        "total_messages": after,
    }
    logger.info("génération drafts", extra={"context": result})
    return result


def export_mailmerge(
    conn: sqlite3.Connection, path: str | Path, position: str = "J0", status: str = "draft"
) -> int:
    """Exporte les brouillons d'une position vers un CSV mailmerge pour l'ESP.

    Garde-fous (pre-mortem) : on **exclut les contacts en liste de suppression** (A3 — le
    chemin ESP ne doit pas contourner la blacklist STOP/bounce/optout) et on **saute tout
    corps contenant un placeholder « [..] » non renseigné** (B1 — opt-out / CTA morts).
    """
    rows = conn.execute(
        """
        SELECT c.email, c.nom, c.segment, m.position, m.subject, m.body
        FROM messages m JOIN contacts c ON c.id = m.contact_id
        WHERE m.position = ? AND m.status = ?
          AND c.email NOT IN (SELECT email FROM suppressions)
        ORDER BY c.id
        """,
        (position, status),
    ).fetchall()
    written = 0
    skipped_placeholder = 0
    with Path(path).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        for r in rows:
            if unfilled_placeholders(r["body"]):
                skipped_placeholder += 1
                continue
            writer.writerow({k: r[k] for k in EXPORT_FIELDS})
            written += 1
    logger.info("export mailmerge", extra={"context": {
        "position": position, "rows": written, "skipped_placeholder": skipped_placeholder,
    }})
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Génération des brouillons (sans envoi).")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="Génère les brouillons en base.")
    g.add_argument("--position", default="J0", choices=POSITIONS)
    g.add_argument("--limit", type=int, default=None)
    e = sub.add_parser("export", help="Exporte les brouillons en CSV mailmerge.")
    e.add_argument("path")
    e.add_argument("--position", default="J0", choices=POSITIONS)
    args = parser.parse_args(argv)

    conn = _db.connect(args.db)
    try:
        if args.cmd == "generate":
            r = generate_drafts(conn, position=args.position, limit=args.limit)
            print(  # noqa: T201
                f"Drafts {args.position} — insérés={r['inserted']} · "
                f"déjà présents={r['skipped_existing']} · "
                f"non conformes ignorés={r['skipped_noncompliant']} · "
                f"total messages={r['total_messages']}\n"
                "Aucun envoi déclenché (statut draft)."
            )
        elif args.cmd == "export":
            n = export_mailmerge(conn, args.path, position=args.position)
            print(f"Export OK — {n} brouillons → {args.path}")  # noqa: T201
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
