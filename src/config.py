"""config — constantes de segmentation, normalisation, garde-fous.

Aucun secret ici (la Phase 1 n'en requiert pas). Les secrets éventuels des
phases suivantes vivent dans .env (voir .env.example), jamais en dur.
"""
from __future__ import annotations

import unicodedata

# --- Segments (verrouillés, cf. SPEC.md) ---------------------------------
SEGMENT_AIR_EAU = "AIR_EAU"
SEGMENT_AIR_AIR = "AIR_AIR"
SEGMENT_AIR_EAU_A_QUALIFIER = "AIR_EAU_A_QUALIFIER"
SEGMENT_EXCLU = "EXCLU"

ALL_SEGMENTS = (
    SEGMENT_AIR_EAU,
    SEGMENT_AIR_AIR,
    SEGMENT_AIR_EAU_A_QUALIFIER,
    SEGMENT_EXCLU,
)

# Segments réellement adressables par email (EXCLU n'est pas démarché).
ACTIVABLE_SEGMENTS = (
    SEGMENT_AIR_EAU,
    SEGMENT_AIR_AIR,
    SEGMENT_AIR_EAU_A_QUALIFIER,
)

# Mapping chauffage normalisé -> segment.
# GAZ/FIOUL -> air/eau · ÉLEC -> air/air · BOIS -> air/eau à qualifier.
CHAUFFAGE_TO_SEGMENT = {
    "GAZ": SEGMENT_AIR_EAU,
    "FIOUL": SEGMENT_AIR_EAU,
    "ELECTRICITE": SEGMENT_AIR_AIR,
    "BOIS": SEGMENT_AIR_EAU_A_QUALIFIER,
}

# Synonymes -> clé canonique du mapping ci-dessus.
CHAUFFAGE_SYNONYMS = {
    "GAZ": "GAZ",
    "GAZ NATUREL": "GAZ",
    "GPL": "GAZ",
    "FIOUL": "FIOUL",
    "MAZOUT": "FIOUL",
    "ELECTRICITE": "ELECTRICITE",
    "ELEC": "ELECTRICITE",
    "ELECTRIQUE": "ELECTRICITE",
    "CONVECTEUR": "ELECTRICITE",
    "BOIS": "BOIS",
    "GRANULES": "BOIS",
    "GRANULE": "BOIS",
    "PELLET": "BOIS",
    "PELLETS": "BOIS",
    "POELE": "BOIS",
}

# Chauffages déjà en PAC -> exclus du ciblage PAC.
CHAUFFAGE_DEJA_PAC = {"PAC", "POMPE A CHALEUR", "POMPE A CHALEUR AIR EAU", "AEROTHERMIE"}

# Sous-tag froid+ si dernier contact au-delà de ce seuil (jours).
FROID_PLUS_DAYS = 365

# --- Raisons d'exclusion / d'isolement (stables pour les rapports) --------
REASON_TEL_SEUL = "tel_seul"
REASON_SANS_EMAIL = "sans_email"
REASON_DEJA_PAC = "deja_pac"
REASON_CHAUFFAGE_INCONNU = "chauffage_inconnu"

REASON_LIGNE_VIDE = "ligne_vide"
REASON_EMAIL_INVALIDE = "email_invalide"

# Validation email volontairement simple (filtre les évidences, pas une RFC).
EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

# Formats de date acceptés en entrée (ordre = priorité d'essai).
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y")


def strip_accents(value: str) -> str:
    """Retire les accents et met en forme NFKD -> ASCII."""
    nfkd = unicodedata.normalize("NFKD", value)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_chauffage(raw: str | None) -> str:
    """Normalise un libellé de chauffage : sans accents, majuscules, espaces compactés."""
    if raw is None:
        return ""
    cleaned = strip_accents(str(raw)).upper().strip()
    return " ".join(cleaned.split())
