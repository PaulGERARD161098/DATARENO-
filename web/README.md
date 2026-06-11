# web/ — tableau de pilotage déployable sur Vercel

Interface **en lecture seule** (statique, sans build, sans dépendance) : `index.html`
lit `data.json` (un instantané **agrégé, sans PII**) et l'affiche. Vercel étant sans état,
le pipeline (SQLite, SMTP, IMAP) reste en local ; cette page n'en est qu'une **vue**.

## 1. Générer / rafraîchir les données
```bash
python -m src.webexport web/data.json --db out/state.sqlite
```
À relancer après chaque run quotidien (ou dans le cron).

## 2. Déployer sur Vercel
**Option A — CLI (le plus simple) :**
```bash
npm i -g vercel        # une fois
cd web && vercel --prod
```
**Option B — depuis le repo GitHub :**
Dans Vercel → *New Project* → importer le repo → **Root Directory = `web`** →
*Framework Preset = Other* (statique). Chaque push qui modifie `web/` redéploie.

> Avec l'option B, committe le `data.json` rafraîchi : `git add web/data.json && git commit && git push`
> → Vercel redéploie automatiquement la nouvelle photo.

## 3. Confidentialité
- `data.json` ne contient **que des agrégats** (funnel, KPIs, paliers, A/B, comptes) — **aucun email**.
- En-têtes `noindex` (cf. `vercel.json`). Pour une vue nominative, reste en local : `python -m src.scoring report`.
- Si un jour tu veux une vue authentifiée avec PII : passer par un déploiement protégé
  (Vercel Password Protection / SSO) + un export séparé — à ne pas exposer publiquement.

## Pourquoi pas d'envoi depuis le web ?
Envoyer/poller sont des opérations longues et **stateful** (mauvais fit serverless), et
le projet impose *« jamais d'auto-envoi »* : le clic d'envoi reste sur ta machine (CLI/cron).
