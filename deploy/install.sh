#!/usr/bin/env bash
# install.sh — prépare l'outil dans APP_DIR (venv + deps + dossiers + DB).
# Idempotent : relançable sans danger. Le code doit déjà être présent (git clone).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/datareno}"
PYTHON="${PYTHON:-python3}"

cd "$APP_DIR"

echo "→ venv + dépendances…"
[ -d .venv ] || "$PYTHON" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

echo "→ dossiers d'état…"
mkdir -p out data

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "→ .env créé depuis .env.example — REMPLIS les secrets puis relance la préparation."
fi

echo "→ schéma SQLite (si absent)…"
[ -f out/state.sqlite ] || python -m src.db --db out/state.sqlite init

echo "→ vérification (tests)…"
python -m pytest -q || { echo "⚠️  tests KO — corrige avant de continuer"; exit 1; }

echo "✅ Installé dans $APP_DIR."
echo "Suite : remplir .env, importer la base, 'sequence plan', 'preflight check' (cf. deploy/README.md)."
