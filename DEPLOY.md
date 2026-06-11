# DEPLOY.md — mise en production (outil autonome, prod-léger)

> L'outil est une **CLI autonome** (SQLite local, pas de serveur). « Déployer » =
> l'installer sur une machine qui tourne, remplir `.env`, passer la **gate**, puis
> planifier le **run quotidien** en cron. Les deux seuls gestes humains restent :
> **valider/envoyer** (déclenché par le cron `--confirm`) et **booker** (le prospect).

## 0. Pré-requis HORS outil (bloquants — voir PREMORTEM.md §6)
- **B2** Base légale opt-in email vérifiée et archivée. *Sans ça, on n'envoie pas.*
- **A5** Domaine d'envoi dédié + DNS **SPF / DKIM / DMARC** (viser 9-10/10 sur mail-tester.com).

## 1. Installation
```bash
git clone <repo> && cd DATARENO-
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # puis remplir (voir §2)
python -m pytest -q         # doit afficher tout vert
```

## 2. Configuration `.env`
Renseigner : `CALENDLY_URL`, `OPTOUT_URL`, `SENDER_NAME`, `CALENDLY_TOKEN`,
`SENDING_DOMAIN`, `SENDER_EMAIL`, `UNSUBSCRIBE_MAILTO`, réassurance (`REASSURANCE_*`),
SMTP (`SMTP_HOST/PORT/USER/PASSWORD/STARTTLS`), IMAP (`IMAP_HOST/PORT/USER/PASSWORD`),
`BOUNCE_RATE_LIMIT`, `WARMUP_J1/J2/MAX`, `DB_PATH`.
> Secrets jamais committés (`.env` est gitignored). TLS vérifié sur SMTP/IMAP.

## 3. Préparation de la base (une fois)
```bash
python -m src.tri data/base.csv --outdir out
python -m src.db   --db out/state.sqlite import out/segments
python -m src.db   --db out/state.sqlite hygiene        # purge adresses rôle/jetable
python -m src.drafts   --db out/state.sqlite generate
python -m src.sequence --db out/state.sqlite plan
```

## 4. Gate Go/No-Go (à repasser avant le 1ᵉʳ envoi)
```bash
python -m src.preflight --db out/state.sqlite check   # exit 0 = GO, 1 = NO-GO
```
Ne pas activer le cron `--confirm` tant que ce n'est pas **GO** (et B2/A5 OK).

## 5. Micro-lot test avant le volume
Sur 20-30 contacts d'abord (cf. PREMORTEM.md). Vérifier : inbox vs spam, bounces,
1ʳᵉ réponse remontée par le poll, opt-out cliquable, 1 RDV de test capté.

## 6. Run quotidien en cron
`src.daily run` enchaîne : ingestion retours (IMAP) + RDV (Calendly) **puis** envoi du
dû (warm-up auto, suppression, coupe-circuit). Exemple crontab (9h en semaine) :
```cron
# m h  dom mon dow   commande
  0 9   *   *  1-5   cd /opt/datareno && . .venv/bin/activate && \
                     python -m src.preflight --db out/state.sqlite check && \
                     python -m src.daily     --db out/state.sqlite run --confirm --smtp \
                     >> out/daily.log 2>&1
```
- Le `preflight && daily` n'envoie que si la gate est **GO** (sécurité).
- Hebdo : `python -m src.recontact --db out/state.sqlite requeue --and-plan` (remise en file 3 mois).

## 7. Supervision
- Logs JSON sur stderr (sans PII) → `out/daily.log`. Surveiller `coupe-circuit` (bounce-rate),
  `blocked_placeholder`, `blocked_claim`.
- Suivi commercial : `python -m src.report` (funnel + reco A/B) et
  `python -m src.dashboard out/dashboard.html` (vue HTML locale).
- **Tableau web (Vercel)** : rafraîchir l'instantané agrégé après le run quotidien et
  (option repo) le committer pour redéployer :
  ```bash
  python -m src.webexport web/data.json --db out/state.sqlite
  git add web/data.json && git commit -m "maj dashboard" && git push   # Vercel redéploie
  ```
  Détails : `web/README.md`.

## 8. Sauvegarde / reprise
- Tout l'état est dans `out/state.sqlite` (gitignored). **Sauvegarder ce fichier** (le
  conteneur/VM est jetable). Les preuves de consentement restent côté métier.
