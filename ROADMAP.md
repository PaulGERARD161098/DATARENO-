# ROADMAP — DATA RÉNO Pipeline → outil opérationnel

> But : passer d'un pipeline « tri → drafts → séquence planifiée » (fait) à un
> outil **opérationnel** où un humain valide et envoie chaque jour, et où les
> réponses/bounces reviennent alimenter l'état. Mise à jour à chaque phase.

## ✅ Acquis (Phases 1→5)
- **1 Tri** — `src/tri.py` : xlsx/csv → segments, dédup, isolés, liste « à rappeler », synthèse.
- **2 État** — `src/db.py` : SQLite `contacts`/`messages`/`events`, import idempotent.
- **3 Mails** — `src/templates.py` : 9 variantes + linter de claims (bloquant).
- **4 Brouillons** — `src/drafts.py` : 1 draft/contact, statut `draft`, export ESP, 0 envoi.
- **5 Séquence** — `src/sequence.py` : J0/J+4/J+8 + warm-up 30→50→100, arrêts, 0 envoi.

Chiffres réels : 14 676 lignes → **5 200 emailables** (3 521 / 983 / 696) · 8 678 « à rappeler ».
État : 5 200 contacts, 15 600 messages programmés (pic 100/j, horizon 157 j). **71 tests**.

---

## 🔜 Reste à implémenter

### Phase 6 — Traitement des réponses  *(code)*
`src/replies.py` + table `suppressions`.
- Classer une réponse : {Intéressé | RDV | Recontacter | PasIntéressé | STOP | Bounce} — l'IA propose, **l'humain valide**.
- Actions auto par classe : STOP → blacklist (suppression) · Bounce → purge · Intéressé → lien Calendly · Recontacter → file 3 mois.
- Annuler les touches en attente (`scheduled` → `cancelled`) dès qu'un arrêt arrive.
- **Acceptation** : jeu de réponses test pré-classé correctement ; un STOP blackliste et empêche tout futur envoi/planif.

### Phase 7 — Reporting & A/B  *(code)*
`src/report.py`.
- Funnel jusqu'au RDV : programmé → envoyé → délivré → ouvert → répondu → RDV.
- A/B sur l'objet : variantes + reco du gagnant (**l'humain décide**, pas de bascule auto).
- **Acceptation** : rapport lisible (CLI/CSV) + reco de variant.

### Phase 8 — Connecteur d'envoi (chaînon opérationnel)  *(code — clé de l'« opérationnel »)*
`src/sender.py`.
- Lister les messages `scheduled` **dus aujourd'hui** → file de validation humaine.
- Envoi **déclenché par l'humain** via le domaine dédié : SMTP/ESP, sinon export Gmail/mailmerge.
- À l'envoi : vérifier la **suppression list**, écrire un event `sent`, passer le message en `sent`, respecter le plafond du jour.
- Ingestion retours : bounces / ouvertures / réponses → `events` (webhooks ESP ou poll IMAP).
- Mode `--dry-run` par défaut (0 envoi) ; envoi réel explicite.
- **Acceptation** : dry-run = 0 envoi ; en réel, 1 message test parti + event `sent` + retour bounce capté.

### Phase 9 — Dashboard HTML local  *(optionnel)*
Vue état pipeline + file de validation drafts/réponses (lecture SQLite).

---

## 🧰 Pré-lancement (hors code — à fournir / configurer)
1. **Entrées métier** : assurance décennale, nombre de chantiers, URL Calendly, URL opt-out, nom expéditeur. → `.env`.
2. **Domaine d'envoi dédié** + DNS **SPF / DKIM / DMARC** configurés ; warm-up réel respecté.
3. **Choix du canal d'envoi** : ESP (SMTP) du domaine dédié **ou** Gmail Workspace.
4. **Preuve d'opt-in email** archivée et accessible (base légale RGPD/DGCCRF).
5. **Pre-mortem** fait — voir `PREMORTEM.md`. **Gate Go/No-Go** à respecter avant le 1ᵉʳ envoi :
   - **B2** base légale opt-in email vérifiée/archivée *(seul showstopper, hors code)* ·
   - **B1** `CALENDLY_URL` + `OPTOUT_URL` réels en `https://`, opt-out testé cliquable ·
   - **A5** SPF/DKIM/DMARC validés · **A1** warm-up réellement appliqué (départ 30/j) ·
   - test **micro-lot 20-30** avant les 5 200.
   Landmines code désamorcés (A1 warm-up auto, B1 garde-fou placeholders, A3 suppression
   à l'export, A4 coupe-circuit bounce) ; reste B2/A5 (ops) + B4 ingestion auto.

## ✅ Acquis opérationnels (v1.0 — l'outil fait le travail prévu)
- **Envoi réel** : transport **SMTP** du domaine dédié (`src.sender --smtp`), MIME avec
  `List-Unsubscribe` 1-clic, TLS vérifié, derrière les garde-fous (warm-up auto, refus
  placeholders, re-lint claims, suppression, coupe-circuit bounce).
- **Ingestion** : poll **IMAP** (`src.inbox poll`) — bounce **hard→purge / soft→escalade**,
  **auto-reply/OOO** (séquence maintenue), réponse→arrêt + classe proposée (humain valide).
- **RDV** : poll **Calendly** (`src.calendly poll`) → event `rdv` + relances annulées (funnel fermé).
- **Run quotidien** : `src.daily run` = ingérer retours + RDV **puis** envoyer le dû (un appel, cron-ready).
- **Gate** : `src.preflight check` = Go/No-Go automatique (exit 1 si NO-GO).
- **Hygiène** : `src.db hygiene` blackliste les adresses rôle/jetable.
- **Personnalisation** : prénom extrait du nom dans l'accroche (fallback « Bonjour, »).
- **Recontact 3 mois** : `src.recontact requeue [--and-plan]` (marqueur `requeue`).
- **A/B objet** : 2 variantes par position, bras stable par contact ; `src.report` compare.
- **Scoring d'engagement** : `src.scoring report` — paliers froid→chaud + **leads chauds**
  (cliqueurs sans réponse) à relancer en priorité.
- **Dashboard enrichi** : funnel, RDV pris, leads chauds, paliers, A/B objet.
- **Micro-lot** : `src.daily run --limit N` (ou `src.sender send --limit N`) pour le 1ᵉʳ test.
- **Déploiement & lancement** : `DEPLOY.md` (cron) + `LAUNCH.md` (runbook 1ʳᵉ campagne).
- **Cockpit de travail** (v1.4, `src/web.py`) : « À envoyer » = envoi **message par message,
  objet+corps éditables** (`sender.send_one`, mêmes garde-fous que le batch) ; « Réponses à
  traiter » = classe proposée + Appliquer (texte non stocké, RGPD) ; « Relever les retours ».
- **Accès navigateur gratuit** (v1.4) : `bash deploy/serve_public.sh` (tunnel Cloudflare,
  0 €, PII sur la machine) ; option 24/7 payante Render (`render.yaml`, cf. `deploy/RENDER.md`).
- Reste **hors code** : **B2** (base légale opt-in, showstopper), **A5** (SPF/DKIM/DMARC),
  remplir `.env`, brancher le cron. Futurs raffinements : jitter/throttle par domaine
  destinataire, seed-list de délivrabilité, alerting sur coupe-circuit.

## 🔑 Variables `.env` attendues
`CALENDLY_URL`, `OPTOUT_URL`, `SENDER_NAME`, `SENDING_DOMAIN`,
`REASSURANCE_RGE`, `REASSURANCE_DECENNALE`, `REASSURANCE_NB_CHANTIERS`,
`WARMUP_J1/J2/MAX`, `BOUNCE_RATE_LIMIT`, `DB_PATH`,
`SMTP_*` / `SENDER_EMAIL` / `UNSUBSCRIBE_MAILTO`, `IMAP_*` (au moment du branchement).

## 📍 Définition de « opérationnel »
L'outil est opérationnel quand, chaque jour, un humain peut :
voir les drafts dus → valider → envoyer via le domaine dédié → recevoir les retours
(bounce/ouverture/réponse) → voir STOP/opt-out/bounce auto-traités → router les
« Intéressé » vers Calendly → suivre le funnel jusqu'au RDV.
→ Atteint à la fin des **Phases 6, 7 et 8** (+ pré-lancement configuré).
