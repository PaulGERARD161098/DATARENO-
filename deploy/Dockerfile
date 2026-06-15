# Image de l'outil DATA RÉNO. Contexte de build = racine du repo :
#   docker build -f deploy/Dockerfile -t datareno .
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Panneau de pilotage. Dans le conteneur on écoute 0.0.0.0, mais on ne PUBLIE que sur
# 127.0.0.1 côté hôte (cf. docker-compose) → jamais exposé sur Internet (PII).
EXPOSE 8765
CMD ["python", "-m", "src.web", "--db", "out/state.sqlite", "--host", "0.0.0.0", "--port", "8765", "--no-open"]
