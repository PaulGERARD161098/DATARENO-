# REPRISE.md — prompt d'ouverture de session (coller tel quel, puis suivre)

> Mis à jour en fin de chaque session. Objectif : zéro perte de contexte, reprise immédiate.

---

## 🟢 DERNIÈRE SESSION — 2026-06-28
- **Piège branche re-confirmé** : la session web cloné l'ANCIENNE branche par défaut (93 tests)
  au lieu de `main` (v1.4, 177→181 tests). → **CORRIGER : GitHub Settings → Branches → default = `main`**
  (toujours pas fait). Réflexe d'ouverture : `git branch -a` + vérifier la default AVANT de coder.
- **Livré & MERGÉ dans `main` (PR #17)** : bouton **« Importer la base »** dans le cockpit
  (`src.web`) → upload `.csv/.xlsx` depuis le navigateur → `tri→import→hygiène→séquence`,
  aucun envoi, idempotent. Parseur multipart maison, cap 30 Mo. **181 tests verts, ruff clean.**
- **Opt-out → Vercel (à faire par Paul, navigateur, sans CLI)** : vercel.com → Add New → Project →
  importe le repo (branche `main`) → `vercel.json` publie `web/` → `OPTOUT_URL=https://<projet>.vercel.app/desinscription.html`.
- **LE GATE du 100 % web reste l'HÉBERGEMENT du cockpit** (Paul n'a pas d'ordi) : Render
  (`render.yaml`) ou tunnel depuis une petite machine. Le bouton import ne sert qu'une fois le cockpit hébergé.

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

SETUP EN COURS — PC de Paul (Windows) — session 2026-06-16(b) :
  - ✅ Python 3.14.6 + Git installés ; repo cloné dans C:\Users\User\DATARENO-.
  - ⚠️ Branche par défaut du dépôt GitHub = ANCIENNE (HEAD≠main → clone donne 93 tests).
    Contournement appliqué : `git checkout main` (puis 177 tests verts). À CORRIGER :
    GitHub → Settings → Branches → default = main (+ supprimer claude/intelligent-brahmagupta-*).
  - ✅ venv + deps OK, 177 tests verts. Panneau lancé (localhost:8765), cockpit visible (NO-GO normal).
  - .env créé/rempli : SENDER_NAME=Réno à domicile, SENDER_EMAIL/UNSUBSCRIBE/OPTOUT
    (=https://renoadomicile.fr/desinscription.html — page PAS encore en ligne), CALENDLY_URL,
    RGE+DECENNALE remplis, NB_CHANTIERS VIDE (omis proprement = OK), WEB_USER/WEB_PASSWORD posés.
    SMTP/IMAP/CALENDLY_TOKEN laissés VIDES → simulation (sûr, rien ne part).
  - ✅ Fichier contacts déposé : data\DATA_RENO_1EUROS_PROPRE.(xlsx ?) — extension à confirmer (`dir data`).
  - 🔒 RGPD : Paul a proposé d'envoyer le fichier PII → REFUSÉ (reste sur sa machine). À maintenir.

⏭️ REPRENDRE ICI (Étape 6) — sur le PC, dans C:\Users\User\DATARENO- :
     .venv\Scripts\python.exe -m src.tri "data\DATA_RENO_1EUROS_PROPRE.xlsx" --outdir out
     .venv\Scripts\python.exe -m src.db --db out/state.sqlite init
     .venv\Scripts\python.exe -m src.db --db out/state.sqlite import out/segments
     .venv\Scripts\python.exe -m src.db --db out/state.sqlite hygiene
     .venv\Scripts\python.exe -m src.drafts --db out/state.sqlite generate
     .venv\Scripts\python.exe -m src.sequence --db out/state.sqlite plan
   → attendu ~5 200 emailables / ~15 600 messages programmés ; relancer `python -m src.web`
     → cockpit PLEIN (file d'envois + leads). NB : drafts OK car CALENDLY_URL+OPTOUT+RGE+décennale
     remplis (sinon placeholders → drafts bloqués).
   PUIS Étape 7 : `bash deploy/serve_public.sh` (Git Bash + cloudflared) → URL tél + auth.

ENCORE À FAIRE avant le VRAI envoi (hors setup) :
  - Générer CALENDLY_TOKEN (scopes read scheduled_events/invitees/user) → .env.
  - Ajouter SMTP/IMAP Infomaniak (mdp boîte) dans .env quand prêt (sort de la simulation).
  - Mettre web/desinscription.html EN LIGNE (Infomaniak) → OPTOUT_URL réel cliquable.
  - DKIM Infomaniak + mail-tester ≥ 9/10 (A5). NB_CHANTIERS quand connu.
  - preflight check → GO, puis micro-lot 25 (LAUNCH.md).
  - GitHub : corriger branche par défaut (main) + supprimer branches obsolètes.

TODO CODE PROMIS (workflow 100 % navigateur) :
  - [FAIT 2026-06-23] Bouton « Importer la base » dans le cockpit (src.web) : upload
    .csv/.xlsx depuis le navigateur → déroule tri → import → hygiène → séquence (aucun
    envoi). Parseur multipart maison (cgi supprimé en 3.13). Cap 30 Mo. Tests : import_base
    (pipeline + idempotence), parse_multipart, refus format/sans fichier. Plus besoin du CLI.
  - RESTE pour le 100 % web : HÉBERGER le cockpit (Paul n'a pas d'ordi). Options navigateur :
    Render (render.yaml présent ; free tier = SQLite éphémère, payant ~7 €/mois = disque UE
    persistant) ou tunnel depuis une petite machine (deploy/serve_public.sh). Sans hôte,
    le bouton import ne sert que sur une machine locale.

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
