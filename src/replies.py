"""replies — Phase 6 : traitement des réponses.

Classe une réponse entrante en {INTERESSE | RDV | RECONTACTER | PAS_INTERESSE |
STOP | BOUNCE}. **L'IA/heuristique propose, l'humain valide** : la classification
n'agit pas seule, c'est `apply_action` (déclenché après validation) qui exécute
les effets de bord.

Actions auto par classe :
- STOP    → liste de suppression + annulation des touches en attente + statut `stopped`.
- BOUNCE  → suppression (purge) + annulation + statut `bounced`.
- INTERESSE → statut `interested` (+ lien Calendly à envoyer) + annulation des relances.
- RDV     → statut `rdv` + annulation des relances.
- RECONTACTER → statut `recontact_3m`, `recontact_at` = +3 mois, annulation.
- PAS_INTERESSE → statut `not_interested` + annulation.

Aucune PII dans les logs.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, timedelta

from . import config as C
from . import db as _db
from .logging_setup import get_logger
from .templates import MessageContext

logger = get_logger("datareno.replies")

# Classes de réponse.
INTERESSE = "INTERESSE"
RDV = "RDV"
RECONTACTER = "RECONTACTER"
PAS_INTERESSE = "PAS_INTERESSE"
STOP = "STOP"
BOUNCE = "BOUNCE"
ALL_LABELS = (INTERESSE, RDV, RECONTACTER, PAS_INTERESSE, STOP, BOUNCE)

RECONTACT_DAYS = 90

# Heuristiques (ordre = priorité). Texte normalisé sans accents, minuscules.
_RULES: list[tuple[str, tuple[str, ...]]] = [
    (BOUNCE, ("mailer-daemon", "delivery status notification", "adresse introuvable",
              "undeliverable", "mail delivery failed", "address not found")),
    (STOP, ("desabonner", "desinscri", "stop", "ne plus recevoir", "ne plus me contacter",
            "unsubscribe", "rgpd", "supprimez mes donnees", "harcelement")),
    (RDV, ("rendez-vous", "rdv", "calendly", "j'ai reserve", "creneau", "disponible le")),
    (INTERESSE, ("interesse", "ca m'interesse", "intéressé", "devis", "en savoir plus",
                 "rappelez-moi", "comment ca marche", "tarif", "oui")),
    (RECONTACTER, ("plus tard", "pas maintenant", "recontact", "l'annee prochaine",
                   "dans quelques mois", "occupe en ce moment")),
    (PAS_INTERESSE, ("pas interesse", "non merci", "aucun interet", "deja equipe",
                     "deja une pac", "pas concerne", "non")),
]


def classify_reply(text: str) -> str:
    """Propose une classe (heuristique). À valider par un humain avant action."""
    haystack = C.strip_accents(text or "").lower()
    for label, keywords in _RULES:
        if any(k in haystack for k in keywords):
            return label
    return RECONTACTER  # défaut prudent : ni STOP ni envoi, on remet à plus tard


def _contact_email(conn: sqlite3.Connection, contact_id: int) -> str | None:
    row = conn.execute("SELECT email FROM contacts WHERE id=?", (contact_id,)).fetchone()
    return row["email"] if row else None


def cancel_pending(conn: sqlite3.Connection, contact_id: int) -> int:
    """Annule les touches non encore envoyées (draft/scheduled → cancelled)."""
    cur = conn.execute(
        "UPDATE messages SET status='cancelled' "
        "WHERE contact_id=? AND status IN ('draft','scheduled')",
        (contact_id,),
    )
    return cur.rowcount


def suppress(conn: sqlite3.Connection, email: str, reason: str) -> None:
    conn.execute(
        "INSERT INTO suppressions (email, reason, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(email) DO UPDATE SET reason=excluded.reason",
        (email.lower(), reason, _db._now()),
    )


def is_suppressed(conn: sqlite3.Connection, email: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM suppressions WHERE email=?", (email.lower(),)
    ).fetchone()
    return row is not None


def record_reply(conn: sqlite3.Connection, contact_id: int, label: str) -> None:
    """Journalise la réponse comme event (sans stocker le texte brut = pas de PII)."""
    conn.execute(
        "INSERT INTO events (contact_id, type, payload, created_at) VALUES (?, 'reply', ?, ?)",
        (contact_id, label, _db._now()),
    )
    conn.commit()


def apply_action(
    conn: sqlite3.Connection,
    contact_id: int,
    label: str,
    ctx: MessageContext | None = None,
    today: date | None = None,
) -> dict[str, object]:
    """Exécute l'effet de bord d'une classe **validée par un humain**."""
    if label not in ALL_LABELS:
        raise ValueError(f"Classe inconnue : {label}")
    ctx = ctx or MessageContext()
    today = today or date.today()
    email = _contact_email(conn, contact_id)
    result: dict[str, object] = {"label": label, "cancelled": 0, "suppressed": False}

    new_status = {
        INTERESSE: "interested", RDV: "rdv", RECONTACTER: "recontact_3m",
        PAS_INTERESSE: "not_interested", STOP: "stopped", BOUNCE: "bounced",
    }[label]

    # Toutes les classes stoppent la séquence en cours.
    result["cancelled"] = cancel_pending(conn, contact_id)

    if label in (STOP, BOUNCE) and email:
        suppress(conn, email, "stop" if label == STOP else "bounce")
        result["suppressed"] = True

    recontact_at = None
    if label == RECONTACTER:
        recontact_at = (today + timedelta(days=RECONTACT_DAYS)).isoformat()

    if label == INTERESSE:
        result["calendly_url"] = ctx.calendly_url  # lien à envoyer (action humaine)

    conn.execute(
        "UPDATE contacts SET status=?, recontact_at=?, updated_at=? WHERE id=?",
        (new_status, recontact_at, _db._now(), contact_id),
    )
    conn.commit()
    logger.info("action réponse", extra={"context": {
        "contact_id": contact_id, "label": label, "status": new_status,
        "cancelled": result["cancelled"], "suppressed": result["suppressed"],
    }})
    return result


def handle_reply(
    conn: sqlite3.Connection,
    contact_id: int,
    text: str,
    *,
    validated_label: str | None = None,
    ctx: MessageContext | None = None,
) -> dict[str, object]:
    """Bout-en-bout : propose une classe, journalise, et applique si validée.

    `validated_label` = la classe confirmée par l'humain. Si None, on ne fait que
    proposer (aucun effet de bord) — respect du « humain valide ».
    """
    proposed = classify_reply(text)
    if validated_label is None:
        return {"proposed": proposed, "applied": False}
    record_reply(conn, contact_id, validated_label)
    action = apply_action(conn, contact_id, validated_label, ctx=ctx)
    return {"proposed": proposed, "applied": True, "action": action}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Traitement des réponses (humain valide).")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classify", help="Propose une classe pour un texte.")
    c.add_argument("text")
    a = sub.add_parser("apply", help="Applique une classe validée à un contact.")
    a.add_argument("contact_id", type=int)
    a.add_argument("label", choices=ALL_LABELS)
    args = parser.parse_args(argv)

    if args.cmd == "classify":
        print(classify_reply(args.text))  # noqa: T201
        return 0

    conn = _db.connect(args.db)
    try:
        record_reply(conn, args.contact_id, args.label)
        r = apply_action(conn, args.contact_id, args.label, ctx=MessageContext.from_env())
        print(  # noqa: T201
            f"Action {args.label} — touches annulées={r['cancelled']} · "
            f"suppression={'oui' if r['suppressed'] else 'non'}"
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
