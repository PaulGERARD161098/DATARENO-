"""calendly — ingestion des RDV pris (ferme le funnel jusqu'à l'objectif).

Le CTA des mails pointe vers Calendly ; quand un prospect réserve, ce module
le remonte dans l'état :
- event `rdv` (horodaté) + contact `status='rdv'` ;
- annulation des relances restantes (le prospect a booké, plus de cold).

Sans ce maillon, la métrique « RDV » du report reste creuse (saisie manuelle).
Réseau (API Calendly) isolé derrière un *fetcher* injectable → testable hors ligne.
Aucune PII dans les logs. Le token vit dans `.env` (CALENDLY_TOKEN), jamais en dur.

CLI :
    python -m src.calendly poll [--db state.sqlite] [--since AAAA-MM-JJ]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator

from . import db as _db
from . import replies as _replies
from .logging_setup import get_logger

logger = get_logger("datareno.calendly")

API = "https://api.calendly.com"

# Un booking = (email_invité, date/heure ISO du RDV).
Booking = tuple[str, str]
# Un fetcher rend les bookings depuis une date donnée.
Fetcher = Callable[["CalendlyConfig", datetime], Iterator[Booking]]


@dataclass
class CalendlyConfig:
    token: str
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "CalendlyConfig":
        return cls(token=os.getenv("CALENDLY_TOKEN", "").strip())

    def missing(self) -> list[str]:
        return [] if self.token else ["CALENDLY_TOKEN"]


def ingest_bookings(conn: sqlite3.Connection, bookings: list[Booking]) -> dict[str, int]:
    """Enregistre les RDV pour les contacts connus. Idempotent (1 event `rdv` / contact)."""
    summary = {"bookings": len(bookings), "matched": 0, "already": 0, "unknown": 0}
    for email, when in bookings:
        row = conn.execute(
            "SELECT id FROM contacts WHERE email=?", ((email or "").lower(),)
        ).fetchone()
        if not row:
            summary["unknown"] += 1
            continue
        cid = row["id"]
        if conn.execute(
            "SELECT 1 FROM events WHERE contact_id=? AND type='rdv'", (cid,)
        ).fetchone():
            summary["already"] += 1
            continue
        now = _db._now()
        conn.execute(
            "INSERT INTO events (contact_id, type, payload, created_at) VALUES (?, 'rdv', ?, ?)",
            (cid, when, now),
        )
        _replies.cancel_pending(conn, cid)  # booké → plus de relance cold
        conn.execute("UPDATE contacts SET status='rdv', updated_at=? WHERE id=?", (now, cid))
        summary["matched"] += 1
    conn.commit()
    logger.info("ingestion RDV Calendly", extra={"context": summary})
    return summary


def _api_get(cfg: CalendlyConfig, url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {cfg.token}", "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:  # noqa: S310 (https constant)
        return json.loads(resp.read().decode("utf-8"))


def _default_fetch(cfg: CalendlyConfig, since: datetime) -> Iterator[Booking]:
    """Relève les RDV actifs via l'API Calendly (HTTPS + timeout)."""
    me = _api_get(cfg, f"{API}/users/me")
    user_uri = me["resource"]["uri"]
    events = _api_get(
        cfg,
        f"{API}/scheduled_events?user={user_uri}&status=active"
        f"&min_start_time={since.astimezone(timezone.utc).isoformat()}",
    )
    for ev in events.get("collection", []):
        start = ev.get("start_time", "")
        invitees = _api_get(cfg, f"{ev['uri']}/invitees")
        for inv in invitees.get("collection", []):
            email = inv.get("email", "")
            if email:
                yield email, start


def poll_calendly(
    conn: sqlite3.Connection, cfg: CalendlyConfig, *,
    since: datetime | None = None, fetcher: Fetcher | None = None,
) -> dict[str, int]:
    """Relève les RDV depuis `since` (défaut: 30 j) et les ingère."""
    fetcher = fetcher or _default_fetch
    since = since or (datetime.now(timezone.utc) - timedelta(days=30))
    bookings = list(fetcher(cfg, since))
    return ingest_bookings(conn, bookings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestion des RDV Calendly (ferme le funnel).")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("poll", help="Relève les RDV récents et les enregistre.")
    p.add_argument("--since", default=None, help="Depuis cette date AAAA-MM-JJ (défaut: 30 j).")
    args = parser.parse_args(argv)

    cfg = CalendlyConfig.from_env()
    if cfg.missing():
        print(f"⛔ Calendly non configuré : {', '.join(cfg.missing())}. Rien relevé.")  # noqa: T201
        return 2
    since = (
        datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        if args.since else None
    )
    conn = _db.connect(args.db)
    try:
        s = poll_calendly(conn, cfg, since=since)
        print(  # noqa: T201
            f"RDV Calendly — reçus={s['bookings']} · nouveaux={s['matched']} · "
            f"déjà connus={s['already']} · contacts inconnus={s['unknown']}"
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
