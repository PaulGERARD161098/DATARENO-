# deploy/REMOTE_ACCESS.md — piloter le panneau depuis n'importe où (option B)

But : accéder au **panneau interactif** (`src/web.py`) depuis ton navigateur, partout,
**sans exposer la PII**. Le panneau reste sur `127.0.0.1:8765` (VPS ou ta machine) ; un
**tunnel** fait le pont, et une **auth** protège l'accès.

## 0. Activer l'auth du panneau (obligatoire dès qu'on expose)
Dans `.env` :
```
WEB_USER=paul
WEB_PASSWORD=un-mot-de-passe-long-et-unique
```
Le panneau exige alors un login (Basic Auth). Sans ça, refuse de l'exposer.
(Si déjà lancé en service : `sudo systemctl restart datareno-web.service`.)

---

## Option 1 — Tailscale (recommandé : privé, zéro port public)
Réseau privé entre tes appareils ; rien n'est exposé sur Internet.
```bash
# sur le VPS
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale serve --bg 8765        # publie 127.0.0.1:8765 dans ton tailnet (HTTPS)
sudo tailscale serve status           # affiche l'URL https://<machine>.<tailnet>.ts.net
```
Installe Tailscale sur ton portable/téléphone (même compte) → ouvre l'URL `*.ts.net`.
Accès limité à TES appareils + login WEB_USER/WEB_PASSWORD. Le plus sûr.

## Option 2 — Cloudflare Tunnel (URL publique + auth)
Donne une URL publique `https://…trycloudflare.com` (ou ton domaine). **Auth panneau
indispensable** (URL devinable).
```bash
# sur le VPS
curl -fsSL https://pkg.cloudflare.com/cloudflared-stable-linux-amd64.deb -o cf.deb && sudo dpkg -i cf.deb
cloudflared tunnel --url http://127.0.0.1:8765      # test rapide → imprime l'URL
```
Pour du durable : `cloudflared tunnel login` + un tunnel nommé + (idéalement)
**Cloudflare Access** (2ᵉ couche d'auth par e-mail/SSO) devant l'URL.

---

## Rappels sécurité
- **Toujours** `WEB_USER`/`WEB_PASSWORD` quand c'est exposé (le panneau montre emails, drafts, leads).
- Le panneau **agit** (envoi, suppression) : garde le mot de passe secret, change-le si fuite.
- Le pare-feu du VPS ne doit ouvrir que **SSH (22)** ; le 8765 reste sur la loopback (le
  tunnel s'y connecte localement). Ne publie jamais le 8765 en clair.
- Sauvegarde `out/state.sqlite` régulièrement.

## Pourquoi pas « sur Vercel » ?
Agir = exécuter du code là où sont la base + SMTP/IMAP. Vercel est sans état : il ne peut
qu'afficher (le dashboard agrégé `web/`). Le tunnel donne le même confort (navigateur,
partout) tout en gardant l'outil autonome et la PII chez toi.
