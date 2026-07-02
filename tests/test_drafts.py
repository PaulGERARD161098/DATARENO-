"""Tests Phase 4 — génération des brouillons (et garantie : aucun envoi)."""
from __future__ import annotations

import csv
from pathlib import Path

from src import db
from src import drafts
from src.templates import MessageContext
from tests.test_db import _seed_segments


def _db_with_contacts(tmp_path: Path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.import_segments(conn, _seed_segments(tmp_path))  # 3 contacts activables
    return conn


def test_generate_cree_des_drafts(tmp_path: Path):
    conn = _db_with_contacts(tmp_path)
    r = drafts.generate_drafts(conn, position="J0")
    assert r["inserted"] == 3
    statuses = [row["status"] for row in conn.execute("SELECT status FROM messages")]
    assert statuses == ["draft", "draft", "draft"]
    conn.close()


def test_aucun_envoi_aucun_event(tmp_path: Path):
    conn = _db_with_contacts(tmp_path)
    drafts.generate_drafts(conn, position="J0")
    # Le code ne déclenche aucun envoi : pas d'event, aucun message 'sent'.
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE status!='draft'").fetchone()[0] == 0
    conn.close()


def test_generate_idempotent(tmp_path: Path):
    conn = _db_with_contacts(tmp_path)
    drafts.generate_drafts(conn, position="J0")
    r2 = drafts.generate_drafts(conn, position="J0")
    assert r2["inserted"] == 0
    assert r2["skipped_existing"] == 3
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 3
    conn.close()


def test_generate_respecte_limit(tmp_path: Path):
    conn = _db_with_contacts(tmp_path)
    r = drafts.generate_drafts(conn, position="J0", limit=2)
    assert r["inserted"] == 2
    conn.close()


def test_drafts_conformes(tmp_path: Path):
    conn = _db_with_contacts(tmp_path)
    drafts.generate_drafts(conn, position="J0")
    ctx = MessageContext()
    for row in conn.execute("SELECT subject, body FROM messages"):
        from src.templates import validate_message
        assert validate_message(
            row["subject"], row["body"], calendly_url=ctx.calendly_url, optout_url=ctx.optout_url
        ) == []
    conn.close()


def test_draft_non_conforme_jamais_stocke(tmp_path: Path):
    """Filet de sécurité : si la réassurance introduit un claim, rien n'est stocké."""
    conn = _db_with_contacts(tmp_path)
    ctx = MessageContext(reassurance="Votre PAC à 1€ !")  # claim interdit injecté
    r = drafts.generate_drafts(conn, ctx=ctx, position="J0")
    assert r["inserted"] == 0
    assert r["skipped_noncompliant"] == 3
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    conn.close()


def test_export_mailmerge(tmp_path: Path):
    conn = _db_with_contacts(tmp_path)
    drafts.generate_drafts(conn, position="J0")
    out = tmp_path / "drafts.csv"
    n = drafts.export_mailmerge(conn, out, position="J0")
    assert n == 3
    with out.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        assert reader.fieldnames == drafts.EXPORT_FIELDS
    assert len(rows) == 3
    assert all("@" in r["email"] for r in rows)
    conn.close()


def test_export_mailmerge_neutralise_injection_formule(tmp_path: Path):
    """S1 : un nom hostile ('=…') est neutralisé dans l'export ESP."""
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    conn.execute(
        "INSERT INTO contacts (email, nom, segment, created_at, updated_at) "
        "VALUES ('evil@b.fr', '=cmd|calc!A0', 'AIR_EAU', ?, ?)", (now, now),
    )
    conn.commit()
    drafts.generate_drafts(conn, position="J0")
    out = tmp_path / "drafts.csv"
    drafts.export_mailmerge(conn, out, position="J0")
    with out.open(encoding="utf-8", newline="") as fh:
        row = next(csv.DictReader(fh))
    assert row["nom"].startswith("'=")
    conn.close()
