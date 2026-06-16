# Déployer le panneau complet sur Render (accessible depuis n'importe quel navigateur)

Objectif : ouvrir le **vrai panneau** (boutons, leads nominatifs, envoi) depuis
ton ordi OU ton téléphone, via une **URL HTTPS protégée par mot de passe**, sans
gérer de serveur Linux. Render héberge le conteneur en continu ; la base SQLite
vit sur un **disque persistant** ; tes identifiants ne sont jamais dans le dépôt.

> Pourquoi pas Vercel ? Le panneau est *stateful* (SQLite/SMTP/IMAP) → Vercel
> (sans état, sans disque) ne convient pas. Render/Railway/Fly, oui.

---

## 1. Déployer (≈10 min, sans SSH)

1. Crée un compte sur **https://render.com** et connecte ton compte **GitHub**.
2. **New +** → **Blueprint** → sélectionne ce dépôt → Render lit `render.yaml`.
3. Render demande **WEB_USER** et **WEB_PASSWORD** (ils ne sont pas dans le dépôt) :
   mets un identifiant et un **mot de passe long et unique**.
4. **Apply**. Render build l'image (`deploy/Dockerfile`) et démarre le service.
5. Tu obtiens une URL du type **`https://datareno-panel.onrender.com`**.

✅ **Vérif** : ouvre l'URL → le navigateur demande identifiant/mot de passe →
tu vois le panneau. (Tant que la base est vide, les compteurs sont à zéro.)

> Le panneau **refuse de démarrer sans WEB_USER/WEB_PASSWORD** quand il est exposé
> (`WEB_EXPOSED=1` dans `render.yaml`) → impossible d'exposer la PII sans mot de passe.

---

## 2. Charger ta base (la PII ne se versionne pas)

Le disque `/data` démarre **vide**. On y copie l'état SQLite construit **en local**.

```bash
# (en local) construire l'état depuis ta base, si pas déjà fait
python -m src.tri data/base.csv --outdir out      # → out/state.sqlite
```

Puis l'envoyer sur le disque Render via **SSH** (réservé aux plans payants) :

1. Render → ton service → onglet **SSH** : ajoute ta **clé SSH publique**
   (`~/.ssh/id_ed25519.pub`) et copie l'adresse SSH affichée.
2. Copie la base :
   ```bash
   scp out/state.sqlite <adresse-ssh-affichée>:/data/state.sqlite
   ```
3. Render → **Manual Deploy / Restart** pour recharger proprement.

✅ **Vérif** : recharge l'URL → KPIs, funnel et leads nominatifs s'affichent.

> Alternative sans scp : ouvre le **Shell** Render (dans le dashboard) et
> reconstruis l'état sur l'instance — mais il faut alors y déposer `base.csv`
> (PII) ; le scp ci-dessus est plus propre.

---

## 3. Passer de la simulation à l'envoi réel (plus tard)

Au départ, sans identifiants SMTP/IMAP, le bouton « Relever + Envoyer » répond
**« Simulation »** (rien ne part) — c'est voulu. Quand la conformité est prête
(cf. `LAUNCH.md`), ajoute dans Render → **Environment** :

```
SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM
IMAP_HOST, IMAP_USER, IMAP_PASSWORD            # pour relever les réponses
CALENDLY_URL, OPTOUT_URL                        # liens des messages
```

Le coupe-circuit (preflight) et la règle « jamais d'auto-envoi » restent actifs :
l'envoi réel reste **ton clic** (case à cocher + bouton).

---

## 🔒 Sécurité — ce que ce déploiement implique

- **PII chez un tiers** : tes contacts vivent désormais sur Render. Atténuations :
  région **frankfurt (UE)**, **HTTPS** forcé, **auth obligatoire**, en-têtes
  `noindex`, disque non public. À toi de juger l'acceptabilité RGPD (sous-traitant).
- **Image sans données** : `.dockerignore` exclut `data/`, `out/`, `.env`, `*.sqlite`
  → aucune PII ni secret dans l'image.
- **Secrets** : WEB_USER/WEB_PASSWORD et SMTP/IMAP sont des variables Render
  (`sync:false`), jamais dans le dépôt.
- **Sauvegarde** : le disque persiste mais n'est pas sauvegardé automatiquement —
  garde ta base source en local.

## ⚡ Coût & alternatives

- Render **starter** ≈ 7 $/mois (always-on + disque 1 Go). Le tier gratuit ne
  permet ni disque persistant ni service toujours allumé → inadapté ici.
- Équivalents possibles avec le même `Dockerfile` : **Railway** (volume + ~5 $/mois)
  ou **Fly.io** (volumes, `fly.toml`). Le code (port `$PORT`, base `$WEB_DB`,
  `WEB_EXPOSED`) est déjà générique ; seul le fichier de déploiement change.
