# deploy/ — faire tourner l'outil sur un serveur/VPS

L'outil opérationnel (pipeline + panneau + SMTP/IMAP + cron) tourne sur **ta** machine
ou un **petit VPS** (Debian/Ubuntu suffit). Trois façons, de la plus simple à la plus
isolée : **systemd**, **cron**, **Docker**. Aucune n'utilise Vercel (sans état).

> Pré-requis métier rappelés (cf. `LAUNCH.md`) : base légale opt-in (B2) + DNS
> SPF/DKIM/DMARC (A5). Sans gate **GO**, le run quotidien n'envoie pas.

---

## 0. Installation (commune)
```bash
sudo useradd -m -d /opt/datareno datareno          # un utilisateur dédié
sudo -u datareno git clone <repo_url> /opt/datareno
cd /opt/datareno && sudo -u datareno bash deploy/install.sh
sudo -u datareno cp .env.example .env && sudo chmod 600 .env
sudo -u datareno nano .env                          # remplir les secrets
```
Puis préparer la base une fois :
```bash
sudo -u datareno bash -lc 'cd /opt/datareno && . .venv/bin/activate \
  && python -m src.tri data/base.csv --outdir out \
  && python -m src.db --db out/state.sqlite import out/segments \
  && python -m src.db --db out/state.sqlite hygiene \
  && python -m src.drafts --db out/state.sqlite generate \
  && python -m src.sequence --db out/state.sqlite plan \
  && python -m src.preflight --db out/state.sqlite check'
```

---

## Option A — systemd (recommandée)
Le **panneau** tourne en service ; le **run quotidien** est déclenché par un timer.
```bash
sudo cp deploy/systemd/datareno-*.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now datareno-web.service     # panneau (localhost:8765)
sudo systemctl enable --now datareno-daily.timer     # run quotidien (Lun-Ven 9h)
systemctl status datareno-web.service
journalctl -u datareno-daily.service -n 50 --no-pager
```
Adapte `User=`, `WorkingDirectory=` et le chemin du venv dans les unités si besoin.

## Option B — cron (sans systemd)
```bash
crontab -u datareno deploy/crontab.example     # édite les chemins d'abord
```

## Option C — Docker
```bash
cd deploy
docker compose up -d web                        # panneau sur 127.0.0.1:8765 (hôte)
docker compose run --rm daily                   # run quotidien (à mettre en cron hôte)
```
`docker-compose.yml` monte `out/` (état + sauvegarde), `data/`, `web/` et charge `.env`.

---

## Accéder au panneau à distance — SANS l'exposer (PII)
Le panneau écoute en **localhost** : il contient des données personnelles, **ne l'ouvre
jamais sur Internet**. Pour y accéder depuis ton poste, tunnel SSH :
```bash
ssh -L 8765:127.0.0.1:8765 datareno@TON_VPS
# puis ouvre http://127.0.0.1:8765 dans ton navigateur local
```
**Accès « partout dans le navigateur » (recommandé) :** tunnel **Tailscale** (privé) ou
**Cloudflare Tunnel** (URL publique), avec l'**auth du panneau** (`WEB_USER`/`WEB_PASSWORD`).
Guide complet : **`deploy/REMOTE_ACCESS.md`**.
(Alternative avancée : reverse proxy Caddy/nginx avec auth + HTTPS — à toi de sécuriser.)

## Sauvegarde & exploitation
- **Sauvegarder `out/state.sqlite`** (tout l'état y est) : `cp out/state.sqlite backups/…` régulier.
- Logs run quotidien : `journalctl -u datareno-daily.service` (ou `out/daily.log` en cron).
- Suivi distant sans PII : déployer aussi le **dashboard Vercel** (cf. `web/README.md`),
  rafraîchi par le run quotidien (`webexport` est inclus dans la commande quotidienne).

## Sécurité
- `.env` en `chmod 600`, jamais committé. Pare-feu : n'ouvrir que SSH (22) ; **pas** le 8765.
- TLS vérifié sur SMTP/IMAP (intégré). Aucune PII dans les logs.
