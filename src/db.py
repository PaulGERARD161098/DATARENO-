"""db — Phase 2 : état & schéma SQLite (autonome, local).

Tables :
- contacts : un contact adressable (clé d'idempotence = email, UNIQUE).
- messages : les touches de séquence (J0/J+4/J+8) par contact, statut draft→sent.
- events   : journal envoi / ouverture / réponse / bounce / opt-out / clic.

Import idempotent depuis les CSV de segments (réimport sans doublon).
SQL paramétré uniquement ; aucune PII dans les logs.

CLI :
    python -m src.db init   [--db state.sqlite]
    python -m src.db import out/segments [--db state.sqlite] [--all]
    python -m src.db stats  [--db state.sqlite]
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config as C
from .logging_setup import get_logger

logger = get_logger("datareno.db")

DEFAULT_DB = "state.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id           INTEGER PRIMARY KEY,
    email        TEXT NOT NULL UNIQUE,
    nom          TEXT,
    tel          TEXT,
    cp           TEXT,
    dept         TEXT,
    chauffage    TEXT,
    surface      REAL,
    campagne     TEXT,
    date_contact TEXT,
    segment      TEXT NOT NULL,
    froid_plus   INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'new',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contacts_segment ON contacts(segment);
CREATE INDEX IF NOT EXISTS idx_contacts_status  ON contacts(status);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY,
    contact_id   INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    position     TEXT NOT NULL,                         -- J0 / J4 / J8
    variant      TEXT,
    subject      TEXT,
    body         TEXT,
    status       TEXT NOT NULL DEFAULT 'draft',         -- draft / scheduled / sent
    scheduled_at TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE(contact_id, position)
);
CREATE INDEX IF NOT EXISTS idx_messages_contact ON messages(contact_id);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY,
    contact_id  INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    message_id  INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    type        TEXT NOT NULL,                          -- sent/open/reply/bounce/optout/click
    payload     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_contact ON events(contact_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _to_float(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _upsert_contact(conn: sqlite3.Connection, row: dict[str, str], segment: str, email: str) -> None:
    now = _now()
    froid = 1 if str(row.get("froid_plus", "")).strip().lower() == "true" else 0
    conn.execute(
        """
        INSERT INTO contacts
            (email, nom, tel, cp, dept, chauffage, surface, campagne, date_contact,
             segment, froid_plus, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            nom=excluded.nom, tel=excluded.tel, cp=excluded.cp, dept=excluded.dept,
            chauffage=excluded.chauffage, surface=excluded.surface,
            campagne=excluded.campagne, date_contact=excluded.date_contact,
            segment=excluded.segment, froid_plus=excluded.froid_plus,
            updated_at=excluded.updated_at
        """,
        (
            email, _clean(row.get("nom")), _clean(row.get("tel")), _clean(row.get("cp")),
            _clean(row.get("dept")), _clean(row.get("chauffage")), _to_float(row.get("surface")),
            _clean(row.get("campagne")), _clean(row.get("date_contact")),
            segment, froid, now, now,
        ),
    )


def import_segments(
    conn: sqlite3.Connection,
    segments_dir: str | Path,
    segments: tuple[str, ...] | None = None,
) -> dict[str, int]:
    """Importe les CSV de segments dans `contacts`. Idempotent (dédup sur email)."""
    init_db(conn)
    segments = segments or C.ACTIVABLE_SEGMENTS
    segments_dir = Path(segments_dir)

    before = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    processed = 0
    for segment in segments:
        path = segments_dir / f"{segment}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                email = (row.get("email") or "").strip().lower()
                if not email:
                    continue
                _upsert_contact(conn, row, segment, email)
                processed += 1
    conn.commit()

    after = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    inserted = after - before
    result = {
        "processed": processed,
        "inserted": inserted,
        "updated": processed - inserted,
        "total": after,
    }
    logger.info("import segments", extra={"context": result})
    return result


def counts_by_segment(conn: sqlite3.Connection) -> dict[str, int]:
    cur = conn.execute(
        "SELECT segment, COUNT(*) AS c FROM contacts GROUP BY segment ORDER BY c DESC"
    )
    return {r["segment"]: r["c"] for r in cur.fetchall()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="État SQLite du pipeline DATA RÉNO.")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"Chemin SQLite (défaut: {DEFAULT_DB}).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Crée le schéma.")
    p_import = sub.add_parser("import", help="Importe les CSV de segments.")
    p_import.add_argument("segments_dir", help="Dossier des segments (ex: out/segments).")
    p_import.add_argument("--all", action="store_true", help="Inclure aussi le segment EXCLU.")
    sub.add_parser("stats", help="Affiche les comptes par segment.")
    args = parser.parse_args(argv)

    conn = connect(args.db)
    try:
        if args.cmd == "init":
            init_db(conn)
            print(f"Schéma initialisé → {args.db}")  # noqa: T201
        elif args.cmd == "import":
            segments = C.ALL_SEGMENTS if args.all else C.ACTIVABLE_SEGMENTS
            r = import_segments(conn, args.segments_dir, segments)
            print(  # noqa: T201
                f"Import OK — traités={r['processed']} · insérés={r['inserted']} · "
                f"mis à jour={r['updated']} · total en base={r['total']}"
            )
        elif args.cmd == "stats":
            counts = counts_by_segment(conn)
            total = sum(counts.values())
            print(f"Contacts en base : {total}")  # noqa: T201
            for seg, c in counts.items():
                print(f"  {seg:24}: {c}")  # noqa: T201
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
