"""Tests Phase 4 — génération des brouillons (et garantie : aucun envoi)."""
from __future__ import annotations

import csv
from pathlib import Path

from src import db
from src import drafts
from src import replies
from src.templates import MessageContext
from tests.test_db import _seed_segments

# Contexte « réel » (liens https) : un export/envoi exige des liens renseignés (garde-fou B1).
REAL_CTX = MessageContext(
    calendly_url="https://calendly.com/expert-cvc/30min",
    optout_url="https://exemple.fr/desinscription",
    sender_name="Équipe CVC",
    reassurance="RGE, décennale",
)


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
    drafts.generate_drafts(conn, ctx=REAL_CTX, position="J0")  # liens réels = exportables
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


def test_export_exclut_les_supprimes(tmp_path: Path):
    """A3 : le chemin ESP ne doit jamais exporter un contact en liste de suppression."""
    conn = _db_with_contacts(tmp_path)
    drafts.generate_drafts(conn, ctx=REAL_CTX, position="J0")
    email = conn.execute("SELECT email FROM contacts ORDER BY id LIMIT 1").fetchone()["email"]
    replies.suppress(conn, email, "stop")
    conn.commit()
    n = drafts.export_mailmerge(conn, tmp_path / "drafts.csv", position="J0")
    assert n == 2  # le contact supprimé est écarté
    conn.close()


def test_export_saute_les_placeholders(tmp_path: Path):
    """B1 : un brouillon avec liens non renseignés (placeholders) n'est jamais exporté."""
    conn = _db_with_contacts(tmp_path)
    drafts.generate_drafts(conn, position="J0")  # ctx par défaut = placeholders [..]
    n = drafts.export_mailmerge(conn, tmp_path / "drafts.csv", position="J0")
    assert n == 0  # tout est bloqué tant que CALENDLY_URL/OPTOUT_URL ne sont pas réels
    conn.close()


def test_draft_personnalise_le_prenom(tmp_path: Path):
    """Le prénom extrait du nom apparaît dans l'accroche ; sinon « Bonjour, »."""
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    conn.execute(
        "INSERT INTO contacts (email, nom, segment, status, created_at, updated_at) "
        "VALUES ('jean@b.fr', 'DUPONT Jean', 'AIR_EAU', 'new', ?, ?)", (now, now),
    )
    conn.execute(
        "INSERT INTO contacts (email, nom, segment, status, created_at, updated_at) "
        "VALUES ('x@b.fr', '', 'AIR_EAU', 'new', ?, ?)", (now, now),
    )
    drafts.generate_drafts(conn, ctx=REAL_CTX, position="J0")
    jean = conn.execute("SELECT body FROM messages WHERE contact_id=1").fetchone()["body"]
    sans = conn.execute("SELECT body FROM messages WHERE contact_id=2").fetchone()["body"]
    assert jean.startswith("Bonjour Jean,")
    assert sans.startswith("Bonjour,")
    conn.close()


def test_drafts_portent_un_bras_ab(tmp_path: Path):
    """A/B : chaque draft encode un bras A ou B dans `variant`, stable par contact."""
    from src.templates import SUBJECT_VARIANTS, assign_ab
    conn = _db_with_contacts(tmp_path)
    drafts.generate_drafts(conn, ctx=REAL_CTX, position="J0")
    for row in conn.execute("SELECT contact_id, variant, subject FROM messages"):
        ab = row["variant"].rsplit(":", 1)[-1]
        assert ab in ("A", "B")
        # Le bras est déterministe (fonction de l'id du contact)…
        assert ab == assign_ab(str(row["contact_id"]))
        # …et l'objet correspond bien à la variante du bras.
        idx = 0 if ab == "A" else 1
        assert row["subject"] == SUBJECT_VARIANTS["J0"][idx]
    conn.close()
