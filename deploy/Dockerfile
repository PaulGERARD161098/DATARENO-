# Image de l'outil DATA RÉNO. Contexte de build = racine du repo :
#   docker build -f deploy/Dockerfile -t datareno .
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Panneau de pilotage. Dans le conteneur on écoute 0.0.0.0.
#  - En local (docker-compose) : on ne PUBLIE que sur 127.0.0.1 → jamais sur Internet.
#  - Sur un PaaS (Render/Railway/Fly) : exposé en HTTPS, donc WEB_USER/WEB_PASSWORD
#    sont OBLIGATOIRES (le panneau refuse de démarrer sans, cf. src/web.py).
# Le port vient de $PORT (injecté par le PaaS, défaut 8765) et la base de $WEB_DB
# (à placer sur un disque persistant, ex. /data/state.sqlite).
EXPOSE 8765
CMD ["python", "-m", "src.web", "--host", "0.0.0.0", "--no-open"]
