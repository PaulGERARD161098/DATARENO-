"""Tests — personnalisation prénom + hygiène d'adresses (cold email)."""
from __future__ import annotations

import pytest

from src import config as C


@pytest.mark.parametrize("nom,attendu", [
    ("Jean Dupont", "Jean"),
    ("DUPONT Jean", "Jean"),       # NOM en capitales d'abord → on prend le prénom
    ("Jean DUPONT", "Jean"),
    ("M. Jean Dupont", "Jean"),    # civilité retirée
    ("jean", "Jean"),
    ("Jean-Pierre Martin", "Jean-Pierre"),
    ("JEAN DUPONT", "Jean"),       # tout en capitales → 1er token, best effort
    ("", ""),
    (None, ""),
    ("   ", ""),
    ("M.", ""),                    # que la civilité → rien
])
def test_first_name(nom, attendu):
    assert C.first_name(nom) == attendu


def test_is_role_email():
    assert C.is_role_email("contact@boite.fr")
    assert C.is_role_email("NoReply@boite.fr")
    assert not C.is_role_email("jean.dupont@boite.fr")
    assert not C.is_role_email("")


def test_is_disposable_email():
    assert C.is_disposable_email("x@yopmail.com")
    assert not C.is_disposable_email("x@gmail.com")
