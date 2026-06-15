"""config — constantes de segmentation, normalisation, garde-fous.

Aucun secret ici (la Phase 1 n'en requiert pas). Les secrets éventuels des
phases suivantes vivent dans .env (voir .env.example), jamais en dur.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

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


def load_env(path: str | Path = ".env") -> int:
    """Charge un fichier `.env` (KEY=VALUE) dans os.environ, sans écraser l'existant.

    Stdlib only (pas de dépendance). Les lignes vides / commentaires (#) sont ignorées ;
    les guillemets entourant la valeur sont retirés. Retourne le nb de variables posées.
    """
    p = Path(path)
    if not p.exists():
        return 0
    posed = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            posed += 1
    return posed


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


# --- Personnalisation & hygiène d'adresses (cold email) -------------------
# Civilités retirées avant d'extraire un prénom.
_CIVILITES = {"M", "MR", "MME", "MLLE", "MX", "DR", "ME", "MONSIEUR", "MADAME", "MADEMOISELLE"}
# Un prénom plausible : lettres (accents/trait d'union/apostrophe), 2 à 25 caractères.
_PRENOM_RE = re.compile(r"^[a-zà-ÿ][a-zà-ÿ'\-]{1,24}$", re.IGNORECASE)

# Préfixes d'adresses « rôle » (génériques) : à éviter en cold email (plaintes/bounces).
ROLE_LOCALPARTS = {
    "contact", "info", "infos", "noreply", "no-reply", "ne-pas-repondre", "nepasrepondre",
    "postmaster", "admin", "webmaster", "sav", "abuse", "support", "commercial",
    "compta", "comptabilite", "accueil", "direction", "hello", "bonjour", "mailer-daemon",
}
# Domaines jetables/temporaires les plus courants : zéro valeur, risque de spamtrap.
DISPOSABLE_DOMAINS = {
    "mailinator.com", "yopmail.com", "yopmail.fr", "guerrillamail.com", "10minutemail.com",
    "trashmail.com", "tempmail.com", "temp-mail.org", "jetable.org", "throwawaymail.com",
}


def first_name(nom: str | None) -> str:
    """Extrait un prénom présentable d'un nom complet, ou '' si incertain.

    Conservateur (un mauvais prénom est pire que pas de prénom) : si un token est en
    Titlecase et d'autres en CAPITALES, le Titlecase est le prénom (les bases écrivent
    souvent le NOM en capitales) ; sinon on prend le 1ᵉʳ token plausible.
    """
    if not nom:
        return ""
    raw = [t for t in re.split(r"[\s.]+", nom.strip()) if t]
    tokens = [t for t in raw if strip_accents(t).upper().rstrip(".") not in _CIVILITES]
    if not tokens:
        return ""
    titlecased = [t for t in tokens if t[:1].isupper() and len(t) > 1 and t[1:].islower()]
    allcaps = [t for t in tokens if t.isupper() and len(t) > 1]
    candidate = titlecased[0] if (len(titlecased) == 1 and allcaps) else tokens[0]
    return candidate.title() if _PRENOM_RE.match(candidate) else ""


def is_role_email(email: str | None) -> bool:
    """True si l'adresse est générique (contact@, info@…) — à éviter en cold email."""
    if not email or "@" not in email:
        return False
    return email.split("@", 1)[0].strip().lower() in ROLE_LOCALPARTS


def is_disposable_email(email: str | None) -> bool:
    """True si le domaine est jetable/temporaire."""
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[-1].strip().lower() in DISPOSABLE_DOMAINS
