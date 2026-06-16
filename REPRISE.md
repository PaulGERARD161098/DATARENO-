# REPRISE.md — prompt d'ouverture de session (coller tel quel, puis suivre)

> Mis à jour en fin de chaque session. Objectif : zéro perte de contexte, reprise immédiate.

---

## 📋 PROMPT MAÎTRE DE REPRISE (à coller en ouverture)

```
Projet : DATA RÉNO Pipeline — cold outreach EMAIL d'une base réno (B2C, 5 200 emailables)
vers RDV PAC. Python + SQLite local, autonome. Repo : paggerard-boop/DATARENO-.
Tout auto SAUF 2 clics humains : envoyer + booker. Conformité DGCCRF/RGPD = cœur.

ÉTAT (v1.4 — outil complet + COCKPIT de travail + accès navigateur gratuit) :
- main : Phases 1→9 livrées. 177 tests verts, ruff clean.
  Dév sur claude/datareno-pipeline-setup-km56q4. PR #12 OUVERTE (CI verte) =
  cockpit de travail + déploiement navigateur ; à merger dans main.
- INTERFACES :
  · COCKPIT DE TRAVAIL (`python -m src.web` → http://127.0.0.1:8765) — le quotidien :
    « À envoyer aujourd'hui » = un éditeur PAR message dû (objet+corps modifiables) +
    boutons Envoyer (clic humain, envoi unitaire) / Enregistrer ; « Réponses à traiter »
    = contacts ayant répondu, classe proposée pré-sélectionnée + Appliquer (texte NON
    stocké = RGPD, lu dans la boîte mail) ; bouton « Relever les retours » (IMAP/Calendly,
    n'envoie rien) ; + KPIs/gate/leads chauds/A-B. Stdlib, .env auto-chargé.
    Actions = web.action_message / web.action_reply / web.action_poll ;
    envoi unitaire = sender.send_one (mêmes garde-fous que send_due) ;
    file réponses = web.pending_replies ; auth = web.auth_ok (testées sans socket).
  · ACCÈS NAVIGATEUR GRATUIT (depuis partout, sans serveur) : `bash deploy/serve_public.sh`
    = panneau local + tunnel Cloudflare gratuit → URL HTTPS (tél/PC). PII reste sur la
    machine. AUTH obligatoire si exposé (WEB_EXPOSED=1 → refuse sans WEB_USER/PASSWORD).
    Option 24/7 payante : Render (render.yaml, ~7 €/mois, disque UE) cf. deploy/RENDER.md.
  · DASHBOARD VERCEL (distant, lecture seule, agrégats SANS PII) : web/ + src.webexport.
- DÉPLOIEMENT OPÉRATIONNEL : kit deploy/ (config-only) : install.sh, systemd
  (datareno-web.service + datareno-daily.timer), crontab.example, Dockerfile +
  docker-compose.yml. + serve_public.sh (tunnel gratuit) et render.yaml (PaaS 24/7).
  Accès distant sans PaaS = tunnel (Cloudflare gratuit / Tailscale / SSH). Voir deploy/README.md.
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

PRÉPA LANCEMENT — DÉCISIONS PRISES (session 2026-06-16) :
  - B2 opt-in : ✅ déclaré ARCHIVÉ par Paul (showstopper levé).
  - Domaine dédié : ✅ renoadomicile.fr CRÉÉ chez Infomaniak (+ boîte contact@renoadomicile.fr).
  - Envoi : ESP abandonné (Brevo payant) → on envoie GRATUITEMENT via le SMTP de la boîte
    Infomaniak (mail.infomaniak.com 587/993) ; Infomaniak gère SPF/DKIM/DMARC. Runbook =
    deploy/EMAIL_SETUP.md (.env littéral renoadomicile.fr).
  - Calendly : ✅ CALENDLY_URL = https://calendly.com/paul-gerard-renoboostia/rdv-expert-cvc-30-min
    (figé dans EMAIL_SETUP.md). Token PAT (scopes read: scheduled_events/invitees/user) à
    générer + garder secret. NB : compte Calendly encore brandé « renoboostia » (cosmétique).
  - Opt-out : ✅ page web/desinscription.html créée (mailto unsubscribe@ → IMAP → STOP).
    À METTRE EN LIGNE (Infomaniak) → OPTOUT_URL=https://renoadomicile.fr/desinscription.html.
  - HÉBERGEMENT : Paul est 100 % web (pas d'ordi perso). Décision = il récupère un PETIT
    ORDI (Mac/PC ou Linux/Chromebook) → option tunnel GRATUITE (deploy/serve_public.sh),
    PII chez lui. (Alternatives écartées : Render ~7 €/mois, Oracle Free VM trop technique.)

"MES CHOSES" RESTANTES avant le 1er envoi :
  1. RÉCUPÉRER UN PETIT ORDI → puis setup ~20 min : Python+Git, clone, deploy/install.sh,
     remplir .env, importer la base, preflight check, serve_public.sh. (= déblocage n°1)
  2. Secrets à mettre dans .env (gardés au chaud d'ici là) : CALENDLY_TOKEN, mot de passe
     boîte (SMTP_PASSWORD/IMAP_PASSWORD), REASSURANCE_RGE/DECENNALE/NB_CHANTIERS.
  3. Mettre web/desinscription.html en ligne chez Infomaniak (→ OPTOUT_URL).
  4. Vérifier DKIM Infomaniak + mail-tester ≥ 9/10 (A5).
  5. UI GitHub : supprimer les branches mergées/obsolètes (proxy bloque la suppression).

TODO CODE PROMIS (pour le workflow 100 % navigateur, sans CLI) :
  - Ajouter un bouton « Importer la base (CSV) » dans le panneau (src.web) → charger les
    5 200 contacts depuis le navigateur (aujourd'hui c'est python -m src.tri/db en CLI).

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
  - SÉCURITÉ (risque accepté) : panneau web sans jeton CSRF sur les POST (message/reply/
    poll). Risque faible (mono-utilisateur, Basic Auth + tunnel, pas d'URL publique
    indexée). À durcir si multi-utilisateurs/exposition large (jeton anti-CSRF + SameSite).
  - Audit sécu session 2026-06-16 : send_one rejoue les garde-fous de send_due
    (suppression/placeholders/lint claims/coupe-circuit/cap) ; entrées panneau échappées
    (_esc) ; SQL paramétré ; /healthz sans PII ; refus de démarrer si exposé sans auth. RAS.

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
