#!/usr/bin/env bash
# Rend le panneau accessible depuis N'IMPORTE QUEL navigateur, GRATUITEMENT,
# sans serveur ni VPS : il tourne sur TA machine et un tunnel Cloudflare gratuit
# lui donne une URL HTTPS publique. La PII ne quitte jamais ta machine.
#
#   bash deploy/serve_public.sh
#
# Prérequis :
#   - WEB_USER / WEB_PASSWORD définis dans .env (sinon le panneau refuse de s'exposer).
#   - cloudflared installé (le script te dit comment si absent).
#
# Limite assumée : l'URL ne marche que tant que cette commande tourne (ordi allumé).
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8765}"

# 1. Garde-fou auth : on s'apprête à exposer la PII publiquement.
#    On laisse src/web.py trancher (WEB_EXPOSED=1 => refuse de démarrer sans auth).
export WEB_EXPOSED=1

# 2. cloudflared présent ?
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "⛔ cloudflared introuvable. Installe-le (gratuit, sans compte) :"
  echo "   • macOS    : brew install cloudflared"
  echo "   • Linux    : https://pkg.cloudflare.com/  (paquet cloudflared)"
  echo "   • Windows  : winget install --id Cloudflare.cloudflared"
  exit 1
fi

# 3. Lancer le panneau en local (127.0.0.1) ; seul le tunnel y accédera.
echo "▶ Démarrage du panneau sur http://127.0.0.1:${PORT} …"
python -m src.web --host 127.0.0.1 --port "${PORT}" --no-open &
PANEL_PID=$!
# Couper le panneau quand on arrête le script (Ctrl+C).
trap 'echo; echo "Arrêt…"; kill "${PANEL_PID}" 2>/dev/null || true' EXIT INT TERM

# Laisser le panneau démarrer (et échouer vite s'il manque l'auth).
sleep 2
if ! kill -0 "${PANEL_PID}" 2>/dev/null; then
  echo "⛔ Le panneau n'a pas démarré (probablement WEB_USER/WEB_PASSWORD manquants dans .env)."
  exit 2
fi

# 4. Ouvrir le tunnel public gratuit → imprime une URL https://….trycloudflare.com
echo "▶ Ouverture du tunnel Cloudflare gratuit (URL publique ci-dessous)…"
echo "  → Ouvre l'URL https://….trycloudflare.com dans ton navigateur, puis connecte-toi."
echo "  → Ctrl+C pour tout arrêter."
cloudflared tunnel --url "http://127.0.0.1:${PORT}"
