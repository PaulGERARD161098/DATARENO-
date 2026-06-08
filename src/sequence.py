"""sequence — Phase 5 : séquençage J0/J+4/J+8 & warm-up.

Planifie les 3 touches de chaque contact dans le temps, en respectant :
- le **warm-up** du domaine (plafond d'envois/jour : 30 → 50 → 100, puis 100) ;
- les **conditions d'arrêt** : un contact ayant déjà un event d'arrêt
  (reply / click / optout / bounce) n'est pas planifié.

Le plafond s'applique au **total** des envois d'une journée (J0 + relances J+4
et J+8 des cohortes précédentes) : l'allocation réserve les 3 créneaux d'un
contact (jour d0, d0+4, d0+8) avant de le placer.

**Aucun envoi** n'est déclenché : on ne fait que poser `scheduled_at` et passer
les messages en statut `scheduled`. L'envoi reste une action humaine.

CLI :
    python -m src.sequence plan     [--db state.sqlite] [--start AAAA-MM-JJ]
    python -m src.sequence simulate [--db state.sqlite] [--start AAAA-MM-JJ] [--days 7]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from collections import defaultdict
from datetime import date, timedelta

from . import config as C
from . import db as _db
from . import drafts as _drafts
from .logging_setup import get_logger
from .templates import MessageContext

logger = get_logger("datareno.sequence")

# Décalages (en jours) des 3 touches par rapport au J0.
OFFSETS = {"J0": 0, "J4": 4, "J8": 8}

# Events qui stoppent la séquence d'un contact.
STOP_EVENTS = ("reply", "click", "optout", "bounce")

# Garde-fou : horizon maximum de recherche d'un créneau (évite toute boucle infinie).
MAX_HORIZON_DAYS = 3650


def warmup_caps() -> tuple[int, int, int]:
    """(jour1, jour2, plateau) depuis l'environnement, sinon 30/50/100."""
    def _int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, "").strip() or default)
        except ValueError:
            return default

    return _int("WARMUP_J1", 30), _int("WARMUP_J2", 50), _int("WARMUP_MAX", 100)


def cap_for_day(day_index: int, caps: tuple[int, int, int]) -> int:
    """Plafond d'envois autorisés pour le n-ième jour (0-indexé)."""
    j1, j2, mx = caps
    if day_index <= 0:
        return j1
    if day_index == 1:
        return j2
    return mx


def _stopped_contacts(conn: sqlite3.Connection) -> set[int]:
    placeholders = ",".join("?" for _ in STOP_EVENTS)
    cur = conn.execute(
        f"SELECT DISTINCT contact_id FROM events WHERE type IN ({placeholders})", STOP_EVENTS
    )
    return {r[0] for r in cur.fetchall()}


def plan_sequence(
    conn: sqlite3.Connection,
    start_date: date | None = None,
    caps: tuple[int, int, int] | None = None,
    ctx: MessageContext | None = None,
    segments: tuple[str, ...] = C.ACTIVABLE_SEGMENTS,
) -> dict[str, int]:
    """Planifie les 3 touches de chaque contact actif. Idempotent et borné."""
    start_date = start_date or date.today()
    caps = caps or warmup_caps()
    ctx = ctx or MessageContext.from_env()

    # S'assurer que les 3 brouillons existent (génère ceux qui manquent).
    for position in OFFSETS:
        _drafts.generate_drafts(conn, ctx=ctx, position=position, segments=segments)

    stops = _stopped_contacts(conn)
    placeholders = ",".join("?" for _ in segments)
    contacts = conn.execute(
        f"""
        SELECT id FROM contacts
        WHERE segment IN ({placeholders})
          AND email NOT IN (SELECT email FROM suppressions)
        ORDER BY (surface IS NULL), surface ASC, id ASC
        """,
        segments,
    ).fetchall()

    day_used: dict[int, int] = defaultdict(int)

    def can_place(di: int) -> bool:
        return day_used[di] < cap_for_day(di, caps)

    planned = 0
    skipped_stop = 0
    for row in contacts:
        cid = row["id"]
        if cid in stops:
            skipped_stop += 1
            continue
        d0 = 0
        while d0 <= MAX_HORIZON_DAYS:
            if all(can_place(d0 + off) for off in OFFSETS.values()):
                break
            d0 += 1
        else:
            logger.warning("horizon dépassé", extra={"context": {"contact_id": cid}})
            break
        for position, off in OFFSETS.items():
            di = d0 + off
            day_used[di] += 1
            send_at = (start_date + timedelta(days=di)).isoformat()
            conn.execute(
                "UPDATE messages SET status='scheduled', scheduled_at=? "
                "WHERE contact_id=? AND position=? AND status IN ('draft','scheduled')",
                (send_at, cid, position),
            )
        planned += 1
    conn.commit()

    horizon = max(day_used) if day_used else 0
    result = {
        "planned_contacts": planned,
        "skipped_stop": skipped_stop,
        "scheduled_messages": planned * len(OFFSETS),
        "horizon_days": horizon,
        "peak_per_day": max(day_used.values()) if day_used else 0,
    }
    logger.info("plan séquence", extra={"context": result})
    return result


def simulate(
    conn: sqlite3.Connection, start_date: date, days: int
) -> dict[str, int]:
    """Compte les envois planifiés par jour sur `days` jours (vérif. du plafond)."""
    counts: dict[str, int] = {}
    for i in range(days):
        d = (start_date + timedelta(days=i)).isoformat()
        n = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE status='scheduled' AND scheduled_at=?", (d,)
        ).fetchone()[0]
        counts[d] = n
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Séquençage J0/J+4/J+8 + warm-up (sans envoi).")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    parser.add_argument("--start", default=None, help="Date de départ AAAA-MM-JJ (défaut: aujourd'hui).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="Planifie la séquence.")
    s = sub.add_parser("simulate", help="Affiche les envois/jour planifiés.")
    s.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)

    start = date.fromisoformat(args.start) if args.start else date.today()
    conn = _db.connect(args.db)
    try:
        if args.cmd == "plan":
            r = plan_sequence(conn, start_date=start)
            caps = warmup_caps()
            print(  # noqa: T201
                f"Plan OK — contacts planifiés={r['planned_contacts']} · "
                f"messages programmés={r['scheduled_messages']} · "
                f"arrêtés (stop)={r['skipped_stop']} · horizon={r['horizon_days']} j · "
                f"pic/jour={r['peak_per_day']} (plafond {caps[2]})\nAucun envoi déclenché."
            )
        elif args.cmd == "simulate":
            counts = simulate(conn, start, args.days)
            caps = warmup_caps()
            print(f"Simulation {args.days} jours (plafond {caps}) :")  # noqa: T201
            for d, n in counts.items():
                print(f"  {d} : {n}")  # noqa: T201
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
