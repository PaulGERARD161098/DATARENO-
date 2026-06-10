"""preflight — gate Go/No-Go automatique avant un envoi réel.

Matérialise la checklist §6 de PREMORTEM.md en un seul verdict. Un FAIL = NO-GO
(l'outil ne doit pas envoyer) ; un WARN n'empêche pas mais doit être lu.

Ce que ça NE vérifie PAS (hors code, responsabilité métier) : la base légale
opt-in (B2) et la configuration DNS SPF/DKIM/DMARC (A5) — rappelées en sortie.

CLI :
    python -m src.preflight check [--db state.sqlite]   # exit 0 si GO, 1 si NO-GO
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass

from . import config as _C
from . import db as _db
from .calendly import CalendlyConfig
from .inbox import ImapConfig
from .logging_setup import get_logger
from .sender import SmtpConfig
from .templates import MessageContext, unfilled_placeholders

logger = get_logger("datareno.preflight")

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _https(url: str | None) -> bool:
    return isinstance(url, str) and url.startswith("https://")


def _filled(value: str | None) -> bool:
    return bool(value) and not value.strip().startswith("[")


def check_config(
    ctx: MessageContext, smtp: SmtpConfig, imap: ImapConfig, calendly: CalendlyConfig
) -> list[Check]:
    """Vérifie .env : liens, expéditeur, transports. Liens non-https = NO-GO (B1)."""
    out = [
        Check("calendly_url", PASS if _https(ctx.calendly_url) else FAIL,
              "CTA Calendly en https://" if _https(ctx.calendly_url) else "manquant / placeholder"),
        Check("optout_url", PASS if _https(ctx.optout_url) else FAIL,
              "opt-out en https://" if _https(ctx.optout_url) else "manquant / placeholder (RGPD)"),
        Check("sender_name", PASS if _filled(ctx.sender_name) else FAIL,
              ctx.sender_name if _filled(ctx.sender_name) else "non renseigné"),
        Check("reassurance", PASS if _filled(ctx.reassurance) else WARN,
              "renseignée" if _filled(ctx.reassurance) else "placeholder (crédibilité réduite)"),
        Check("smtp_config", PASS if not smtp.missing() else FAIL,
              "complète" if not smtp.missing() else f"manque {', '.join(smtp.missing())}"),
        Check("imap_config", PASS if not imap.missing() else WARN,
              "complète" if not imap.missing() else "ingestion des retours désactivée"),
        Check("calendly_token", PASS if not calendly.missing() else WARN,
              "présent" if not calendly.missing() else "RDV non remontés automatiquement"),
    ]
    return out


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def check_db(conn: sqlite3.Connection) -> list[Check]:
    """Vérifie l'état : contacts, file d'envoi, placeholders résiduels, hygiène d'adresses."""
    contacts = _scalar(conn, "SELECT COUNT(*) FROM contacts")
    scheduled = _scalar(conn, "SELECT COUNT(*) FROM messages WHERE status='scheduled'")

    placeholder_msgs = 0
    for row in conn.execute("SELECT body FROM messages WHERE status IN ('draft','scheduled')"):
        if unfilled_placeholders(row["body"]):
            placeholder_msgs += 1

    role = 0
    for row in conn.execute(
        "SELECT email FROM contacts WHERE email NOT IN (SELECT email FROM suppressions)"
    ):
        if _C.is_role_email(row["email"]) or _C.is_disposable_email(row["email"]):
            role += 1

    suppressed = _scalar(conn, "SELECT COUNT(*) FROM suppressions")

    return [
        Check("contacts", PASS if contacts > 0 else FAIL, f"{contacts} en base"),
        Check("file_envoi", PASS if scheduled > 0 else WARN,
              f"{scheduled} messages programmés" if scheduled else "rien de programmé (lancer `sequence plan`)"),
        Check("placeholders_residuels", PASS if placeholder_msgs == 0 else FAIL,
              "aucun" if placeholder_msgs == 0 else f"{placeholder_msgs} message(s) à liens non renseignés"),
        Check("hygiene_adresses", PASS if role == 0 else WARN,
              "aucune adresse rôle/jetable active" if role == 0 else f"{role} adresse(s) rôle/jetable à purger"),
        Check("suppression_list", PASS, f"{suppressed} adresse(s) en liste de suppression"),
    ]


def run_preflight(
    conn: sqlite3.Connection, *, ctx: MessageContext | None = None,
    smtp: SmtpConfig | None = None, imap: ImapConfig | None = None,
    calendly: CalendlyConfig | None = None,
) -> list[Check]:
    ctx = ctx or MessageContext.from_env()
    smtp = smtp or SmtpConfig.from_env()
    imap = imap or ImapConfig.from_env()
    calendly = calendly or CalendlyConfig.from_env()
    return check_config(ctx, smtp, imap, calendly) + check_db(conn)


def verdict(checks: list[Check]) -> str:
    """GO sauf si au moins un FAIL → NO-GO."""
    return "NO-GO" if any(c.status == FAIL for c in checks) else "GO"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate Go/No-Go avant envoi réel.")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="Lance la checklist et rend le verdict.")
    args = parser.parse_args(argv)

    conn = _db.connect(args.db)
    try:
        checks = run_preflight(conn)
    finally:
        conn.close()
    icon = {PASS: "✅", WARN: "⚠️ ", FAIL: "⛔"}
    for c in checks:
        print(f"  {icon[c.status]} {c.name:24} {c.detail}")  # noqa: T201
    v = verdict(checks)
    print(f"\nVERDICT : {v}")  # noqa: T201
    print(  # noqa: T201
        "Rappel HORS CODE (non vérifiable ici) : B2 base légale opt-in email · "
        "A5 SPF/DKIM/DMARC du domaine dédié."
    )
    return 0 if v == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
