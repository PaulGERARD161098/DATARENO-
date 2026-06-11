# GUIDE — DATA RÉNO Pipeline

Mode d'emploi complet. Trois parties :
**(1) utiliser l'outil**, **(2) comment il marche**, **(3) travailler dessus (développer)**.

> Docs voisines : `DEPLOY.md` (mise en prod/cron) · `LAUNCH.md` (runbook 1ʳᵉ campagne) ·
> `PREMORTEM.md` (risques + gate) · `SPEC.md` (décisions figées) · `CLAUDE.md` (méthode).

---

# Partie 1 — Mode d'emploi (utiliser)

## A. Installation (une fois)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # puis remplir (section B)
python -m pytest -q           # doit être tout vert
```

## B. Configurer `.env` (« tes choses »)
| Variable | Rôle |
|---|---|
| `CALENDLY_URL`, `CALENDLY_TOKEN` | lien de prise de RDV + token API pour remonter les RDV |
| `OPTOUT_URL`, `UNSUBSCRIBE_MAILTO` | désinscription (obligatoire RGPD) |
| `SENDER_NAME`, `SENDING_DOMAIN`, `SENDER_EMAIL` | expéditeur (domaine dédié) |
| `REASSURANCE_RGE/_DECENNALE/_NB_CHANTIERS` | réassurance affichée (qualitatif) |
| `SMTP_HOST/PORT/USER/PASSWORD/STARTTLS` | envoi réel |
| `IMAP_HOST/PORT/USER/PASSWORD/FOLDER` | ingestion des retours |
| `WARMUP_J1/J2/MAX`, `BOUNCE_RATE_LIMIT`, `DB_PATH` | réglages |

> Tant qu'un lien (`CALENDLY_URL`/`OPTOUT_URL`) reste vide, **l'outil refuse d'exporter
> ou d'envoyer** ce message (garde-fou placeholder). Rien ne part de travers.

Hors `.env`, **bloquants** : base légale opt-in archivée (B2) + DNS SPF/DKIM/DMARC (A5).

## C. Préparer la base (une fois par base)
```bash
python -m src.tri  data/ta_base.xlsx --outdir out          # 1. segmente, déduplique, isole
python -m src.db   --db out/state.sqlite import out/segments  # 2. charge l'état SQLite
python -m src.db   --db out/state.sqlite hygiene           # 3. purge adresses rôle/jetable
python -m src.drafts   --db out/state.sqlite generate      # 4. brouillons (perso prénom, 0 envoi)
python -m src.sequence --db out/state.sqlite plan          # 5. planifie J0/J+4/J+8 (warm-up)
```
Vérifie `out/synthese.xlsx` (comptes par segment) et `sequence simulate --days 7`.

## D. La gate avant d'envoyer
```bash
python -m src.preflight --db out/state.sqlite check        # exit 0 = GO, 1 = NO-GO
```
Verdict **GO** requis. Voir `LAUNCH.md` pour le déroulé complet (micro-lot d'abord).

## E. Le geste quotidien (le seul à répéter)
```bash
# Simulation (n'envoie rien) :
python -m src.daily --db out/state.sqlite run --no-poll
# Réel : ingère retours (IMAP) + RDV (Calendly) PUIS envoie le dû via SMTP :
python -m src.daily --db out/state.sqlite run --confirm --smtp
# Micro-lot (1ᵉʳ test) : plafonne le batch
python -m src.daily --db out/state.sqlite run --confirm --smtp --limit 25
```
**Les 2 seuls gestes humains** : le `--confirm` (envoyer) et le prospect qui booke (Calendly).

## F. Piloter & exploiter (le pipe commercial)
```bash
python -m src.report   --db out/state.sqlite               # funnel + reco A/B objet
python -m src.scoring  --db out/state.sqlite report        # paliers + LEADS CHAUDS à relancer
python -m src.dashboard out/dashboard.html --db out/state.sqlite  # vue HTML
python -m src.replies  --db out/state.sqlite apply <id> INTERESSE  # valider une réponse
python -m src.recontact --db out/state.sqlite requeue --and-plan   # hebdo : 3 mois échus
```
> **Priorité commerciale** : les CLIQUEURS sans réponse (`scoring report`) = intention
> montrée, pas encore booké → c'est là que sont les RDV. Relance-les en premier.

## G. Règles à ne jamais enfreindre
- **Jamais d'auto-envoi** : c'est toujours ton `--confirm`.
- **Zéro claim** « 1 € » / « -X % » / « X € » non sourcé (le linter bloque, à la génération ET à l'envoi).
- **STOP / opt-out / bounce dur** → suppression automatique et définitive.
- Canal **email seul** ; les « tel seul » (`out/_a_rappeler_telephone.csv`) ne sont **jamais** appelés par l'outil.

---

# Partie 2 — Comment ça marche

## Le flux
```
ta base .xlsx/.csv
   └─ tri ─► out/segments/*.csv ─► db(import+hygiene) ─► state.sqlite(contacts)
        └─ templates(9 mails + linter) ─► drafts(messages: draft, perso prénom, A/B)
             └─ sequence(messages: scheduled, J0/J+4/J+8, warm-up)
                  └─ [preflight GO] ─► daily run :
                       ├─ inbox.poll (IMAP)  : bounce hard→purge/soft→escalade, OOO, réponse→arrêt
                       ├─ calendly.poll      : RDV pris → event rdv + relances annulées
                       └─ sender.send_due [--confirm] : SMTP, garde-fous, events(sent)
                            └─ report / scoring / dashboard : funnel, leads chauds, A/B
```

## La base (`state.sqlite`)
| Table | Contenu |
|---|---|
| `contacts` | prospect (email unique), segment, statut (`new`→`contacted`→`interested`/`rdv`/`stopped`…) |
| `messages` | touches J0/J4/J8 par contact, statut `draft`→`scheduled`→`sent`/`cancelled`, `variant` (bras A/B) |
| `events` | journal : `sent`, `open`, `click`, `reply`, `bounce`, `soft_bounce`, `auto_reply`, `optout`, `rdv`, `requeue` |
| `suppressions` | liste noire (stop/bounce/optout/hygiene) — plus jamais contactés |

## Segmentation (figée, cf. SPEC.md)
GAZ/FIOUL → **AIR_EAU** · ÉLEC → **AIR_AIR** · BOIS → **AIR_EAU_À_QUALIFIER** ·
déjà-PAC / inconnu / sans email → **EXCLU**. Priorité = surface croissante.

## Garde-fous intégrés
Linter de claims · refus de placeholder à l'export/envoi · re-lint à l'envoi · double
verrou (`--confirm` + transport) · **warm-up auto** (30→50→100/j, déduit des jours
envoyés) · **coupe-circuit bounce-rate** · suppression appliquée partout · TLS vérifié
SMTP/IMAP · anti header-injection · aucune PII dans les logs · `data/`+`out/` gitignored.

---

# Partie 3 — Travailler sur l'outil (développer)

## Disposition du repo
```
src/        un module = une responsabilité, chacun exécutable en CLI (python -m src.<mod>)
  config      constantes (segments, normalisation, prénom, hygiène) — aucun I/O
  models      schémas Pydantic (tri)
  logging_setup  logger JSON + redact() PII
  tri         base → segments (Phase 1)
  db          schéma SQLite + import idempotent + hygiene
  templates   mails + linter de claims + A/B + détecteur de placeholders
  drafts      génération des brouillons (perso prénom)
  sequence    planification J0/J4/J8 + warm-up + arrêts
  sender      envoi (dry-run/SMTP/export .eml) + garde-fous + ingestion d'1 event
  inbox       poll IMAP (classification bounce/OOO/réponse)
  calendly    poll des RDV → event rdv
  daily       orchestrateur quotidien (poll + send)
  replies     classification + actions validées par l'humain
  recontact   remise en file « 3 mois »
  report      funnel + A/B
  scoring     paliers d'engagement + leads chauds
  preflight   gate Go/No-Go
  dashboard   vue HTML statique
tests/      un test_<module>.py par module (pytest)
```

## Conventions (cf. CLAUDE.md — à respecter)
- **Python typé**, fonctions pures quand possible, `try/except` typé par bloc, fallbacks explicites.
- **SQLite local**, SQL **paramétré uniquement** (jamais de f-string de valeurs).
- **Secrets en `.env`** (jamais en dur) ; **aucune PII** (email/tel/nom) dans les logs.
- **Réseau injectable** : tout appel réseau (SMTP/IMAP/HTTP) passe par un *connecteur/fetcher*
  paramétrable, pour que la logique se teste **sans réseau** (voir `smtp_transport(connector=…)`,
  `poll_inbox(fetcher=…)`, `poll_calendly(fetcher=…)`).
- **Jamais d'auto-envoi** ; tout nouvel envoi reste derrière `confirm=True` + transport.
- HTTPS + timeout + TLS vérifié sur toute sortie réseau.

## Boucle de dev
```bash
python -m pytest -q            # 163 tests — doit rester vert
ruff check src tests           # lint — doit rester clean
ruff check --fix src tests     # corrige l'auto-fixable
```
Tout changement = **tests + ruff verts** avant commit.

## Ajouter une fonctionnalité (recette)
1. Code dans le module concerné (ou un nouveau `src/<mod>.py` avec un `main()` CLI + `if __name__`).
2. Garde-fous d'abord : un envoi/une suppression doit être sûr par défaut.
3. Réseau ? → derrière un fetcher injectable.
4. `tests/test_<mod>.py` : cas nominal **+ cas limites + 1 cas adverse** (TEST POV, cf. CLAUDE.md).
5. Mets à jour `README.md` (commandes), `ROADMAP.md`, et `REPRISE.md` (état).
6. `pytest -q && ruff check src tests` verts.
7. **Commit tout de suite** (un `git checkout`/`reset` perd le travail non commité),
   message clair, puis push sur la branche de dev et ouvre une PR (draft).

## Git (workflow du projet)
- Développer sur la **branche de feature** dédiée, jamais committer directement sur `main`.
- `git push -u origin <branche>` puis **ouvrir une PR** (la CI lance `pytest`).
- Merge via PR une fois la CI verte. Le conteneur est jetable : **rien n'existe tant que ce n'est pas poussé**.

## Pièges connus / dettes (cf. REPRISE.md)
- `plan_sequence` est en O(contacts×horizon) : OK à 5k, à optimiser si ×10.
- `config.first_name` est heuristique (NOM en capitales) ; conservateur (préfère vide à un mauvais prénom).
- Bounce ambigu = traité **hard** par défaut (la réputation prime).
- Le contenu IMAP est hostile par défaut : jamais exécuté, seulement classé ; seul un bounce dur supprime (fail-safe).
