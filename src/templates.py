"""templates — Phase 3 : moteur de mails + linter de claims (garde-fou bloquant).

9 variantes = 3 segments × 3 touches (J0 / J+4 / J+8). Variables : chauffage,
dept, prenom (fallback). 1 seul CTA = Calendly. Opt-out présent. Ton « vous ».

Le **linter de claims** rejette ce qui expose à la DGCCRF :
- « 1 € » (et variantes),
- pourcentages non sourcés (« -40 % »),
- montants chiffrés (« 9 000 € d'économies »),
- « installation 48h » (→ « RDV expert sous 48h »).

Réassurance + liens restent des placeholders tant qu'ils ne sont pas fournis
(décennale, nb chantiers, Calendly, opt-out). Aucun chiffre n'est inventé.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

from . import config as C

POSITIONS = ("J0", "J4", "J8")

# --- Linter de claims -------------------------------------------------------
# Patterns appliqués sur le texte sans accents, en minuscules.
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # « 1 € » / « 1 euro » (le symbole € est un caractère non-mot : pas de \b après).
    ("claim_1_euro", re.compile(r"(?<!\d)1\s*€")),
    ("claim_1_euro", re.compile(r"(?<!\d)1\s*euros?\b")),
    ("pourcentage_non_source", re.compile(r"-?\s*\d+([.,]\d+)?\s*%")),
    # Montant chiffré : « 9 000 € », « 9000 euros ».
    ("montant_chiffre", re.compile(r"\d[\d.,\s]*€")),
    ("montant_chiffre", re.compile(r"\d[\d.,\s]*\beuros?\b")),
    # « installation/pose 48h » (mais « RDV expert sous 48h » reste autorisé).
    ("installation_48h", re.compile(r"(install|pose|pos[ée]\w*)\D{0,20}48\s*h")),
    ("installation_48h", re.compile(r"48\s*h\D{0,20}(install|pose)")),
]


def lint_claims(text: str) -> list[str]:
    """Retourne la liste (triée, unique) des claims interdits détectés."""
    haystack = C.strip_accents(text).lower()
    found = {name for name, pat in FORBIDDEN_PATTERNS if pat.search(haystack)}
    return sorted(found)


# Détecteur de placeholders non renseignés ([VOTRE_LIEN_CALENDLY], [LIEN_DESINSCRIPTION]…).
# Aucun template légitime n'utilise de crochets : tout « [..] » résiduel = champ vide.
# Garde-fou B1 (pre-mortem) : on refuse d'EXPORTER ou d'ENVOYER un corps qui en contient
# (opt-out / CTA morts = violation RGPD + funnel cassé), même si le linter de claims passe.
_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")


def unfilled_placeholders(text: str) -> list[str]:
    """Liste triée/unique des placeholders « [..] » encore présents dans le texte."""
    return sorted(set(_PLACEHOLDER_RE.findall(text)))


def validate_message(subject: str, body: str, *, calendly_url: str, optout_url: str) -> list[str]:
    """Linter de claims + règles structurelles (1 CTA Calendly, opt-out présent)."""
    violations = lint_claims(subject + "\n" + body)
    if optout_url not in body:
        violations.append("optout_absent")
    if body.count(calendly_url) != 1:
        violations.append("cta_calendly_unique_requis")
    return violations


# --- Contexte (placeholders tant que non fournis) ---------------------------
@dataclass
class MessageContext:
    calendly_url: str = "[VOTRE_LIEN_CALENDLY]"
    optout_url: str = "[LIEN_DESINSCRIPTION]"
    sender_name: str = "[VOTRE_NOM]"
    # Réassurance : aucun chiffre inventé. Placeholder tant que non fourni.
    reassurance: str = "[réassurance à compléter : RGE / décennale / nb chantiers réalisés]"

    @classmethod
    def from_env(cls) -> "MessageContext":
        decennale = os.getenv("REASSURANCE_DECENNALE", "").strip()
        nb = os.getenv("REASSURANCE_NB_CHANTIERS", "").strip()
        rge = os.getenv("REASSURANCE_RGE", "").strip()
        bits = [b for b in (rge, decennale, (f"{nb} chantiers réalisés" if nb else "")) if b]
        return cls(
            calendly_url=os.getenv("CALENDLY_URL", "").strip() or cls.calendly_url,
            optout_url=os.getenv("OPTOUT_URL", "").strip() or cls.optout_url,
            sender_name=os.getenv("SENDER_NAME", "").strip() or cls.sender_name,
            reassurance=", ".join(bits) if bits else cls.reassurance,
        )


# --- Contenu des variantes --------------------------------------------------
# Tonalité = réactivation (base 2023, 100 % froid+). Aides en qualitatif, 0 chiffre.
SEGMENT_PITCH = {
    C.SEGMENT_AIR_EAU: "le remplacement de votre chauffage par une pompe à chaleur air-eau",
    C.SEGMENT_AIR_AIR: "l'installation d'une pompe à chaleur air-air en relais de vos convecteurs",
    C.SEGMENT_AIR_EAU_A_QUALIFIER: "l'étude d'une pompe à chaleur air-eau adaptée à votre chauffage actuel",
}

# A/B objet : 2 variantes par position. Variante A = canonique (rétro-compat).
# Le report compare ensuite les objets réellement envoyés (groupé par subject) :
# l'humain décide du gagnant, aucune bascule auto (cf. report.recommend_subject).
SUBJECT_VARIANTS = {
    "J0": [
        "On reprend votre projet de chauffage ?",
        "Et si on relançait votre projet de chauffage ?",
    ],
    "J4": [
        "Les aides pour votre pompe à chaleur, pendant qu'elles sont ouvertes",
        "Pompe à chaleur : vérifions votre éligibilité aux aides",
    ],
    "J8": [
        "Dernier message au sujet de votre projet de pompe à chaleur",
        "On clôt votre projet de pompe à chaleur ?",
    ],
}
AB_LABELS = ("A", "B")

# Objet « par défaut » = variante A (utilisé par les appels sans A/B explicite).
SUBJECTS = {pos: variants[0] for pos, variants in SUBJECT_VARIANTS.items()}


def subject_for(position: str, variant: str = "A") -> str:
    """Objet d'une (position, variante A/B). Variante inconnue → A."""
    if position not in SUBJECT_VARIANTS:
        raise ValueError(f"Position inconnue : {position}")
    idx = AB_LABELS.index(variant) if variant in AB_LABELS else 0
    variants = SUBJECT_VARIANTS[position]
    return variants[idx % len(variants)]


def assign_ab(key: str) -> str:
    """Assignation A/B déterministe et stable (même contact → même bras)."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return AB_LABELS[int(digest, 16) % len(AB_LABELS)]

_BODY_J0 = """Bonjour{prenom},

Vous nous aviez sollicités au sujet de votre chauffage. Votre logement dans le {dept} reste tout à fait pertinent pour {pitch}.

Vous êtes potentiellement éligible aux aides à la rénovation énergétique. Le plus simple est d'en parler quelques minutes avec un expert CVC, qui fait le point sur votre situation — sans engagement.

Réservez le créneau qui vous arrange : {calendly}

{reassurance}

Bien à vous,
{sender}

Pour ne plus recevoir nos messages : {optout}"""

_BODY_J4 = """Bonjour{prenom},

Petit suivi concernant votre projet de chauffage. Les dispositifs d'aide à la rénovation évoluent régulièrement : vérifier votre éligibilité maintenant évite de passer à côté d'une fenêtre favorable pour {pitch}.

Un expert CVC peut vous recevoir en RDV sous 48h pour faire le point.

Choisissez votre créneau ici : {calendly}

{reassurance}

Bien à vous,
{sender}

Pour ne plus recevoir nos messages : {optout}"""

_BODY_J8 = """Bonjour{prenom},

Je me permets un dernier message au sujet de votre projet dans le {dept}. Si {pitch} vous intéresse toujours, l'échange avec un expert CVC reste la meilleure façon d'y voir clair.

Sans retour de votre part, je ne vous solliciterai plus.

Votre créneau, si vous le souhaitez : {calendly}

{reassurance}

Bien à vous,
{sender}

Pour ne plus recevoir nos messages : {optout}"""

_BODIES = {"J0": _BODY_J0, "J4": _BODY_J4, "J8": _BODY_J8}


def _prenom_fragment(contact: dict[str, str]) -> str:
    prenom = (contact.get("prenom") or "").strip()
    return f" {prenom}" if prenom else ""


def render(
    segment: str, position: str, contact: dict[str, str], ctx: MessageContext,
    variant: str = "A",
) -> tuple[str, str]:
    """Rend (objet, corps) pour un (segment, position[, variante A/B]). Lève si inconnus."""
    if segment not in SEGMENT_PITCH:
        raise ValueError(f"Segment inconnu : {segment}")
    if position not in _BODIES:
        raise ValueError(f"Position inconnue : {position}")
    dept = (contact.get("dept") or "votre département").strip() or "votre département"
    body = _BODIES[position].format(
        prenom=_prenom_fragment(contact),
        dept=dept,
        pitch=SEGMENT_PITCH[segment],
        calendly=ctx.calendly_url,
        optout=ctx.optout_url,
        reassurance=ctx.reassurance,
        sender=ctx.sender_name,
    )
    return subject_for(position, variant), body


def render_all(ctx: MessageContext | None = None) -> list[dict[str, object]]:
    """Rend les 9 variantes + leur résultat de validation (placeholders neutres)."""
    ctx = ctx or MessageContext()
    sample = {"dept": "44"}
    out: list[dict[str, object]] = []
    for segment in C.ACTIVABLE_SEGMENTS:
        for position in POSITIONS:
            subject, body = render(segment, position, sample, ctx)
            out.append({
                "segment": segment,
                "position": position,
                "subject": subject,
                "body": body,
                "violations": validate_message(
                    subject, body, calendly_url=ctx.calendly_url, optout_url=ctx.optout_url
                ),
            })
    return out


def main(argv: list[str] | None = None) -> int:
    ctx = MessageContext.from_env()
    variants = render_all(ctx)
    ko = 0
    for v in variants:
        flag = "OK" if not v["violations"] else f"⚠ {v['violations']}"
        if v["violations"]:
            ko += 1
        print(f"\n===== {v['segment']} / {v['position']} — {flag} =====")  # noqa: T201
        print(f"Objet : {v['subject']}")  # noqa: T201
        print(v["body"])  # noqa: T201
    print(f"\n{len(variants)} variantes · {ko} non conforme(s).")  # noqa: T201
    return 1 if ko else 0


if __name__ == "__main__":
    raise SystemExit(main())
