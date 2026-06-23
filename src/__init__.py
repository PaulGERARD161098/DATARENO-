"""DATA RÉNO Pipeline — package source.

Cold outreach email d'une base de contacts réno → RDV qualifiés PAC.
Autonome (SQLite local), hors stack RénoBoost. Voir CLAUDE.md / SPEC.md / TASKS.md.
"""

# Charge .env au démarrage de tout point d'entrée (`python -m src.*`) si présent.
# Robuste : ne casse jamais si python-dotenv absent ou .env manquant. N'écrase pas
# les variables déjà définies (override=False). Désactivé sous pytest pour garder
# les tests isolés du .env local (ils valident sur des placeholders).
import sys as _sys  # noqa: E402

if "pytest" not in _sys.modules:  # pragma: no cover - amorçage best-effort
    try:
        from dotenv import load_dotenv as _load_dotenv

        _load_dotenv(override=False)
    except Exception:  # noqa: BLE001 - l'absence de .env / dotenv ne doit jamais bloquer
        pass
