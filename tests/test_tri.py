"""Tests Phase 1 — tri par chauffage (cas limites inclus)."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from src import config as C
from src.tri import (
    classify_row,
    is_froid_plus,
    parse_date,
    parse_surface,
    run,
    segment_for,
)

TODAY = date(2026, 6, 8)


# --- segmentation chauffage ------------------------------------------------
@pytest.mark.parametrize(
    "chauffage,expected",
    [
        ("GAZ", C.SEGMENT_AIR_EAU),
        ("Fioul", C.SEGMENT_AIR_EAU),
        ("Mazout", C.SEGMENT_AIR_EAU),
        ("Électricité", C.SEGMENT_AIR_AIR),
        ("elec", C.SEGMENT_AIR_AIR),
        ("Bois", C.SEGMENT_AIR_EAU_A_QUALIFIER),
        ("granulés", C.SEGMENT_AIR_EAU_A_QUALIFIER),
    ],
)
def test_segment_mapping(chauffage, expected):
    segment, reason = segment_for("a@b.fr", "", chauffage)
    assert segment == expected
    assert reason is None


def test_deja_pac_exclu():
    segment, reason = segment_for("a@b.fr", "", "Pompe à chaleur")
    assert segment == C.SEGMENT_EXCLU
    assert reason == C.REASON_DEJA_PAC


def test_chauffage_inconnu_exclu():
    segment, reason = segment_for("a@b.fr", "", "charbon")
    assert segment == C.SEGMENT_EXCLU
    assert reason == C.REASON_CHAUFFAGE_INCONNU


# --- exclusion "tel seul" (canal email) ------------------------------------
def test_tel_seul_exclu():
    segment, reason = segment_for("", "0601020304", "GAZ")
    assert segment == C.SEGMENT_EXCLU
    assert reason == C.REASON_TEL_SEUL


def test_sans_aucun_contact():
    segment, reason = segment_for("", "", "GAZ")
    assert segment == C.SEGMENT_EXCLU
    assert reason == C.REASON_SANS_EMAIL


# --- isolement qualité -----------------------------------------------------
def test_email_invalide_isole():
    row = {"email": "pasunmail", "chauffage": "GAZ"}
    result = classify_row(row, line=2, today=TODAY)
    assert result.reason == C.REASON_EMAIL_INVALIDE
    assert result.line == 2


def test_ligne_vide_isolee():
    result = classify_row({"email": "", "chauffage": ""}, line=2, today=TODAY)
    assert result.reason == C.REASON_LIGNE_VIDE


# --- parsing --------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [("120", 120.0), ("90,5", 90.5), ("1 200 m2", 1200.0), ("", None), ("abc", None)])
def test_parse_surface(raw, expected):
    assert parse_surface(raw) == expected


@pytest.mark.parametrize("raw,expected", [("2025-01-15", date(2025, 1, 15)), ("15/01/2025", date(2025, 1, 15)), ("xx", None)])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


# --- froid+ ----------------------------------------------------------------
def test_froid_plus_au_dela_365j():
    assert is_froid_plus(date(2025, 1, 1), TODAY) is True


def test_pas_froid_plus_recent():
    assert is_froid_plus(date(2026, 5, 1), TODAY) is False


def test_froid_plus_sans_date():
    assert is_froid_plus(None, TODAY) is False


# --- dérivation dept depuis CP ---------------------------------------------
def test_dept_derive_du_cp():
    c = classify_row({"email": "a@b.fr", "chauffage": "GAZ", "cp": "69003"}, 2, TODAY)
    assert c.dept == "69"


# --- run complet (intégration) ---------------------------------------------
def _write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_run_produit_les_sorties(tmp_path: Path):
    fields = ["Nom", "Email", "Tel", "CP", "Chauffage", "Surface", "Date"]
    rows = [
        {"Nom": "A", "Email": "a@b.fr", "Tel": "", "CP": "69003", "Chauffage": "GAZ", "Surface": "150", "Date": "2026-05-01"},
        {"Nom": "B", "Email": "b@b.fr", "Tel": "", "CP": "75010", "Chauffage": "GAZ", "Surface": "80", "Date": "2024-01-01"},
        {"Nom": "C", "Email": "c@b.fr", "Tel": "", "CP": "13001", "Chauffage": "Électricité", "Surface": "60", "Date": ""},
        {"Nom": "D", "Email": "", "Tel": "0600000000", "CP": "", "Chauffage": "GAZ", "Surface": "", "Date": ""},
        {"Nom": "E", "Email": "pasunmail", "Tel": "", "CP": "", "Chauffage": "GAZ", "Surface": "", "Date": ""},
    ]
    src = tmp_path / "base.csv"
    _write_csv(src, rows, fields)

    result = run(src, tmp_path / "out", today=TODAY)

    assert result.total_rows == 5
    assert result.counts_by_segment[C.SEGMENT_AIR_EAU] == 2
    assert result.counts_by_segment[C.SEGMENT_AIR_AIR] == 1
    assert result.counts_by_segment[C.SEGMENT_EXCLU] == 1  # tel seul
    assert result.invalid_count == 1  # email invalide
    assert result.froid_plus_by_segment[C.SEGMENT_AIR_EAU] == 1  # B (2024)

    assert (tmp_path / "out" / "segments" / "AIR_EAU.csv").exists()
    assert (tmp_path / "out" / "_isoles_qualite.csv").exists()
    assert (tmp_path / "out" / "synthese.xlsx").exists()


def test_run_tri_surface_croissante(tmp_path: Path):
    fields = ["Email", "Chauffage", "Surface"]
    rows = [
        {"Email": "x@b.fr", "Chauffage": "GAZ", "Surface": "200"},
        {"Email": "y@b.fr", "Chauffage": "GAZ", "Surface": "50"},
        {"Email": "z@b.fr", "Chauffage": "GAZ", "Surface": ""},
    ]
    src = tmp_path / "base.csv"
    _write_csv(src, rows, fields)
    run(src, tmp_path / "out", today=TODAY)

    with (tmp_path / "out" / "segments" / "AIR_EAU.csv").open(encoding="utf-8") as fh:
        emails = [r["email"] for r in csv.DictReader(fh)]
    assert emails == ["y@b.fr", "x@b.fr", "z@b.fr"]  # 50, 200, puis sans surface


def test_separateur_point_virgule(tmp_path: Path):
    src = tmp_path / "base.csv"
    src.write_text("Email;Chauffage;Surface\na@b.fr;GAZ;100\n", encoding="utf-8")
    result = run(src, tmp_path / "out", today=TODAY)
    assert result.counts_by_segment[C.SEGMENT_AIR_EAU] == 1
