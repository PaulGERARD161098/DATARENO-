"""models — schémas Pydantic du domaine (Phase 1 : Contact + résultats de tri).

Phases 2+ étendront avec Message (séquence) et Event (envoi/ouverture/réponse).
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Contact(BaseModel):
    """Contact normalisé et classé par le tri.

    Champs source conservés + champs dérivés (segment, froid_plus, raison).
    `exclusion_reason` n'est renseigné que pour le segment EXCLU.
    """

    nom: str | None = None
    email: str | None = None
    tel: str | None = None
    cp: str | None = None
    dept: str | None = None
    chauffage: str | None = None
    surface: float | None = None
    campagne: str | None = None
    date_contact: date | None = None

    # Dérivés du tri.
    segment: str
    froid_plus: bool = False
    exclusion_reason: str | None = None


class InvalidRow(BaseModel):
    """Ligne isolée pour raison qualité (jamais droppée silencieusement)."""

    line: int
    reason: str
    raw: dict[str, str]


class TriResult(BaseModel):
    """Résultat agrégé d'un tri (sans PII : ne contient que des comptes)."""

    total_rows: int = 0
    counts_by_segment: dict[str, int] = {}
    froid_plus_by_segment: dict[str, int] = {}
    invalid_count: int = 0
    duplicate_count: int = 0
