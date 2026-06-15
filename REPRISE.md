# REPRISE.md — prompt d'ouverture de session (coller tel quel, puis suivre)

> Mis à jour en fin de chaque session. Objectif : zéro perte de contexte, reprise immédiate.

---

## 📋 PROMPT MAÎTRE DE REPRISE (à coller en ouverture)

```
Projet : DATA RÉNO Pipeline — cold outreach EMAIL d'une base réno (B2C, 5 200 emailables)
vers RDV PAC. Python + SQLite local, autonome. Repo : paggerard-boop/DATARENO-.
Tout auto SAUF 2 clics humains : envoyer + booker. Conformité DGCCRF/RGPD = cœur.

ÉTAT (v1.3 — outil complet + 2 interfaces ; démo end-to-end) :
- main à jour (PR #2→#8 mergées). 172 tests verts, ruff clean.
  Dév sur claude/datareno-pipeline-setup-km56q4 (repartir de main).
- INTERFACES :
  · PANNEAU LOCAL / DISTANT (le plus simple) : `python -m src.web` → http://127.0.0.1:8765,
    boutons (relever retours, envoyer la file, valider réponse, leads chauds nominatifs).
    Stdlib, .env auto-chargé. AUTH Basic optionnelle (WEB_USER/WEB_PASSWORD) → exposable
    via tunnel (Tailscale/Cloudflare, cf. deploy/REMOTE_ACCESS.md) sans fuite de PII.
    Actions = web.action_run / web.action_reply ; auth = web.auth_ok (testées sans socket).
  · DASHBOARD VERCEL (distant, lecture seule, agrégats SANS PII) : web/ + src.webexport,
    déployable (vercel.json racine outputDirectory=web). Voir web/README.md.
- DÉPLOIEMENT OPÉRATIONNEL : kit deploy/ (config-only, sans changement de code) :
  install.sh, systemd (datareno-web.service + datareno-daily.timer), crontab.example,
  Dockerfile + docker-compose.yml. Env fourni par le service (EnvironmentFile/env_file/
  source .env). Accès panneau à distance = tunnel SSH (jamais d'expo PII). Voir deploy/README.md.
- PIPELINE COMPLET & RUNNABLE :
  tri → db(import+hygiene) → drafts(perso prénom + A/B) → sequence → PREFLIGHT(gate
  Go/No-Go) → daily run(ingestion retours IMAP + RDV Calendly PUIS envoi SMTP, --limit
  micro-lot) → report(funnel+A/B) → scoring(paliers + leads chauds) → dashboard.
  + recontact(remise en file 3 mois). Runbook lancement = LAUNCH.md.
- GARDE-FOUS : warm-up auto · refus placeholders · re-lint claims à l'envoi · suppression
  partout · coupe-circuit bounce · TLS vérifié SMTP/IMAP · anti header-injection ·
  bounce hard→purge / soft→escalade · auto-reply/OOO ne stoppe pas la séquence ·
  hygiène adresses rôle/jetable · jamais d'auto-envoi.

GESTE QUOTIDIEN (cron-ready, voir DEPLOY.md) :
  python -m src.preflight --db out/state.sqlite check        # gate, exit 1 = NO-GO
  python -m src.daily run --confirm --smtp                   # ingère retours+RDV puis envoie
  python -m src.recontact requeue --and-plan                 # hebdo : 3 mois échus
  python -m src.report                                       # funnel + reco A/B

"MES CHOSES" EN ATTENTE (bloquent l'envoi réel — les CLI refusent tant que vide) :
  1. B2 = base légale opt-in email vérifiée/archivée → LE SEUL SHOWSTOPPER (légal).
  2. DNS SPF/DKIM/DMARC du domaine dédié + mail-tester.com (A5).
  3. .env : SMTP_*, SENDER_EMAIL, UNSUBSCRIBE_MAILTO, IMAP_*, CALENDLY_URL, CALENDLY_TOKEN,
     OPTOUT_URL, SENDER_NAME, REASSURANCE_*.
  4. UI GitHub : supprimer les branches mergées/obsolètes (proxy bloque la suppression).
  5. Brancher le cron du run quotidien (DEPLOY.md §6) + sauvegarder out/state.sqlite.

CHANTIERS DE RAFFINEMENT (l'outil tourne déjà sans ; par valeur) :
  a) Micro-lot test 20-30 en réel après gate GO (outillé : daily run --limit ; LAUNCH.md).
  b) Délivrabilité avancée : jitter d'envoi + throttle par domaine destinataire,
     seed-list de monitoring inbox/spam.
  c) Alerting sur coupe-circuit bounce (aujourd'hui loggé, pas notifié).
  [FAIT cette session : scoring d'engagement + leads chauds + dashboard RDV/A-B + micro-lot.]

DETTES TECHNIQUES (non bloquantes) :
  - plan_sequence O(contacts×horizon) : OK à 5k, revoir si ×10 (executemany, index
    events(type, created_at)).
  - first_name : heuristique « NOM en capitales = prénom ailleurs » ; cas tout-capitales
    = best effort (1er token). Conservateur : préfère '' à un mauvais prénom.
  - bounce ambigu = traité HARD par défaut (réputation prime) ; soft seulement si
    marqueur temporaire explicite. Escalade après 3 soft.
  - calendly/_default_fetch et inbox/imap : réseau non testé (logique testée via fetcher
    injecté). DSN forgé peut suppr. un contact (fail-safe assumé).

VÉRIF INITIALE : git status && git log --oneline -5
  puis pip install -r requirements.txt && python -m pytest -q && ruff check src tests
DÉMO END-TO-END (reproductible) : voir le bloc « démo » de l'historique ou DEPLOY.md.
LECTURES : DEPLOY.md (mise en prod) · PREMORTEM.md (gate §6) · ROADMAP.md · README.md.

QUESTION D'OUVERTURE — l'outil fait déjà le travail prévu. Choisir :
  a) Accompagner le 1ᵉʳ lancement réel (gate + micro-lot) quand B2/A5/.env sont prêts.
  b) Délivrabilité avancée (jitter, throttle/domaine, seed-list).
  c) Scoring d'engagement + dashboard RDV/A/B.
Si je réponds « go » : (a) si la config est prête, sinon (b). Hypothèses explicites.
```

---

## Rappels de méthode (CLAUDE.md, inchangés)
- Travail substantiel = Template A avant de coder ; `ok S{n}` valide un bloc ; `go` = stop questions.
- TEST POV (1 adversaire) sur tout livrable tiers. Pre-mortem avant lancement → fait (`PREMORTEM.md`).
- Fin de livraison code = bloc 🔒 Retour sécurité + ⚡ Retour optimisation.
- Fin de session = nettoyage code mort + audit sécu + mise à jour de ce fichier.
