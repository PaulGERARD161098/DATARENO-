"""Tests Phase 2 — état SQLite (schéma, import idempotent, requêtes)."""
from __future__ import annotations

import csv
from pathlib import Path

from src import config as C
from src import db
from src.tri import OUTPUT_FIELDS


def _make_segment(dirpath: Path, segment: str, contacts: list[dict[str, str]]) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    with (dirpath / f"{segment}.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for c in contacts:
            writer.writerow({k: c.get(k, "") for k in OUTPUT_FIELDS})


def _seed_segments(tmp_path: Path) -> Path:
    seg = tmp_path / "segments"
    _make_segment(seg, C.SEGMENT_AIR_EAU, [
        {"email": "a@b.fr", "chauffage": "GAZ", "surface": "120.0", "froid_plus": "True"},
        {"email": "b@b.fr", "chauffage": "FIOUL", "surface": "90.0", "froid_plus": "False"},
    ])
    _make_segment(seg, C.SEGMENT_AIR_AIR, [
        {"email": "c@b.fr", "chauffage": "ÉLECTRICITÉ", "surface": "60.0", "froid_plus": "True"},
    ])
    _make_segment(seg, C.SEGMENT_EXCLU, [
        {"email": "", "chauffage": "GAZ", "exclusion_reason": "tel_seul"},
    ])
    return seg


def test_purge_hygiene_blackliste_role_et_jetable(tmp_path: Path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    now = db._now()
    for email in ("jean@gmail.com", "contact@boite.fr", "x@yopmail.com"):
        conn.execute(
            "INSERT INTO contacts (email, segment, status, created_at, updated_at) "
            "VALUES (?, 'AIR_EAU', 'new', ?, ?)", (email, now, now),
        )
    conn.commit()
    r = db.purge_hygiene(conn)
    assert r["suppressed"] == 2  # contact@ (rôle) + yopmail (jetable)
    sup = {row["email"] for row in conn.execute("SELECT email FROM suppressions")}
    assert sup == {"contact@boite.fr", "x@yopmail.com"}
    assert not db.purge_hygiene(conn)["suppressed"]  # idempotent
    conn.close()


def test_init_cree_les_tables(tmp_path: Path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.init_db(conn)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"contacts", "messages", "events"} <= tables
    conn.close()


def test_import_active_seulement(tmp_path: Path):
    seg = _seed_segments(tmp_path)
    conn = db.connect(tmp_path / "s.sqlite")
    r = db.import_segments(conn, seg)
    assert r["inserted"] == 3          # EXCLU ignoré par défaut
    assert r["total"] == 3
    assert db.counts_by_segment(conn) == {C.SEGMENT_AIR_EAU: 2, C.SEGMENT_AIR_AIR: 1}
    conn.close()


def test_reimport_idempotent(tmp_path: Path):
    seg = _seed_segments(tmp_path)
    conn = db.connect(tmp_path / "s.sqlite")
    db.import_segments(conn, seg)
    r2 = db.import_segments(conn, seg)          # second passage
    assert r2["inserted"] == 0
    assert r2["updated"] == 3
    assert r2["total"] == 3                      # aucun doublon
    conn.close()


def test_import_all_inclut_exclu(tmp_path: Path):
    seg = _seed_segments(tmp_path)
    # EXCLU sans email est ignoré ; on ajoute un EXCLU avec email pour vérifier l'option --all.
    _make_segment(seg, C.SEGMENT_EXCLU, [
        {"email": "x@b.fr", "chauffage": "PAC", "exclusion_reason": "deja_pac"},
    ])
    conn = db.connect(tmp_path / "s.sqlite")
    r = db.import_segments(conn, seg, C.ALL_SEGMENTS)
    assert r["inserted"] == 4
    assert db.counts_by_segment(conn)[C.SEGMENT_EXCLU] == 1
    conn.close()


def test_froid_plus_et_surface_typés(tmp_path: Path):
    seg = _seed_segments(tmp_path)
    conn = db.connect(tmp_path / "s.sqlite")
    db.import_segments(conn, seg)
    row = conn.execute(
        "SELECT surface, froid_plus, status FROM contacts WHERE email=?", ("a@b.fr",)
    ).fetchone()
    assert row["surface"] == 120.0
    assert row["froid_plus"] == 1
    assert row["status"] == "new"
    conn.close()


def test_fk_message_et_event(tmp_path: Path):
    seg = _seed_segments(tmp_path)
    conn = db.connect(tmp_path / "s.sqlite")
    db.import_segments(conn, seg)
    cid = conn.execute("SELECT id FROM contacts WHERE email=?", ("a@b.fr",)).fetchone()["id"]
    now = db._now()
    conn.execute(
        "INSERT INTO messages (contact_id, position, status, created_at) VALUES (?,?,?,?)",
        (cid, "J0", "draft", now),
    )
    mid = conn.execute("SELECT id FROM messages WHERE contact_id=?", (cid,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO events (contact_id, message_id, type, created_at) VALUES (?,?,?,?)",
        (cid, mid, "sent", now),
    )
    conn.commit()
    # CASCADE : supprimer le contact purge messages + events.
    conn.execute("DELETE FROM contacts WHERE id=?", (cid,))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    conn.close()
