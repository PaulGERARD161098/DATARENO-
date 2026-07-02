"""Tests Phase 3 — moteur de templates + linter de claims.

Inclut un TEST POV adversaire (consigne CLAUDE.md) : un rédacteur qui tente
de glisser un claim interdit doit être bloqué par le linter.
"""
from __future__ import annotations

import pytest

from src import config as C
from src.templates import (
    POSITIONS,
    MessageContext,
    lint_claims,
    render,
    render_all,
    validate_message,
)


# --- linter : claims interdits ---------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Votre pompe à chaleur à 1€ seulement", "claim_1_euro"),
        ("Jusqu'à -40% sur votre facture", "pourcentage_non_source"),
        ("Économisez 9 000 € par an", "montant_chiffre"),
        ("Installation en 48h garantie", "installation_48h"),
        ("Pose sous 48 h", "installation_48h"),
    ],
)
def test_linter_detecte_claims(text, expected):
    assert expected in lint_claims(text)


def test_linter_accepte_texte_conforme():
    ok = "Vous êtes éligible aux aides. RDV avec un expert sous 48h."
    assert lint_claims(ok) == []


def test_rdv_48h_autorise_mais_pas_installation_48h():
    assert lint_claims("RDV expert sous 48h") == []
    assert "installation_48h" in lint_claims("installation sous 48h")


# --- POV adversaire ---------------------------------------------------------
def test_pov_adversaire_message_piege():
    ctx = MessageContext()
    piege = (
        "Bonjour, profitez de votre PAC à 1€ et -50% sur la facture, "
        "installation 48h !\n" + ctx.calendly_url + "\n" + ctx.optout_url
    )
    violations = validate_message("Offre 1€", piege, calendly_url=ctx.calendly_url, optout_url=ctx.optout_url)
    assert "claim_1_euro" in violations
    assert "pourcentage_non_source" in violations
    assert "installation_48h" in violations


# --- règles structurelles ---------------------------------------------------
def test_optout_obligatoire():
    ctx = MessageContext()
    body = f"Bonjour,\nRDV : {ctx.calendly_url}\n"  # pas d'opt-out
    assert "optout_absent" in validate_message("s", body, calendly_url=ctx.calendly_url, optout_url=ctx.optout_url)


def test_cta_calendly_unique():
    ctx = MessageContext()
    deux = f"{ctx.calendly_url} et encore {ctx.calendly_url}\n{ctx.optout_url}"
    assert "cta_calendly_unique_requis" in validate_message("s", deux, calendly_url=ctx.calendly_url, optout_url=ctx.optout_url)


# --- rendu des 9 variantes --------------------------------------------------
def test_render_all_neuf_variantes_conformes():
    variants = render_all()
    assert len(variants) == len(C.ACTIVABLE_SEGMENTS) * len(POSITIONS) == 9
    for v in variants:
        assert v["violations"] == [], f"{v['segment']}/{v['position']} : {v['violations']}"


def test_render_injecte_variables():
    ctx = MessageContext()
    subject, body = render(C.SEGMENT_AIR_EAU, "J0", {"dept": "44", "prenom": "Marie"}, ctx)
    assert "Marie" in body
    assert "44" in body
    assert ctx.calendly_url in body
    assert ctx.optout_url in body
    assert subject


def test_prenom_fallback_sans_prenom():
    ctx = MessageContext()
    _, body = render(C.SEGMENT_AIR_AIR, "J0", {"dept": "13"}, ctx)
    assert body.startswith("Bonjour,")  # pas de « Bonjour  , » disgracieux


def test_from_env_compose_reassurance(monkeypatch):
    monkeypatch.setenv("REASSURANCE_RGE", "Certifié RGE")
    monkeypatch.setenv("REASSURANCE_NB_CHANTIERS", "1200")
    monkeypatch.setenv("REASSURANCE_DECENNALE", "assurance décennale")
    ctx = MessageContext.from_env()
    assert "RGE" in ctx.reassurance
    assert "1200 chantiers" in ctx.reassurance
    # même avec la réassurance remplie, aucun claim interdit n'est introduit.
    assert lint_claims(ctx.reassurance) == []


def test_v2_objets_distincts_par_position():
    """U7 : trois objets distincts (A/B par objet exige la différenciation)."""
    from src.templates import SUBJECTS
    assert len(set(SUBJECTS.values())) == 3
