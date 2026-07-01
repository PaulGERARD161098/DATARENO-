# PRELAUNCH — Checklist opérationnelle (canal : domaine dédié + ESP/SMTP)

> But : passer du pipeline **fait** (code 100 %, 93 tests) à une **1ʳᵉ campagne réelle**
> sûre. Canal V1 verrouillé : **domaine d'envoi dédié via ESP/SMTP** (pas d'adresse perso,
> pas de démarchage tél). Cocher dans l'ordre ; ne pas lancer tant qu'un bloqueur ⛔ reste.
> Rappel garde-fous : email seul · zéro claim « 1€ »/non sourcé · **jamais d'auto-envoi**.

## 0. Décisions figées
- [x] Canal = **domaine dédié + ESP/SMTP**.
- [ ] Choix de l'ESP : Brevo / Mailjet / Postmark / autre. → `__________`
- [ ] Domaine d'envoi dédié acheté (≠ domaine principal de l'entreprise). → `__________`
- [ ] Adresse expéditrice décidée (ex. `contact@<domaine-dédié>`). → `__________`

## 1. ⛔ Délivrabilité — DNS (bloqueur dur)
Sans ça, 5 200 envois finissent en spam et grillent le domaine.
- [ ] **SPF** : enregistrement TXT autorisant l'ESP (`v=spf1 include:<esp> -all`).
- [ ] **DKIM** : clé fournie par l'ESP publiée (CNAME/TXT), signature active.
- [ ] **DMARC** : TXT `_dmarc` en `p=none` d'abord (monitoring), puis `p=quarantine`.
- [ ] **rDNS / PTR** cohérent si IP dédiée ; sinon IP partagée ESP acceptée.
- [ ] Domaine **âgé ≥ quelques jours** avant 1er envoi (pas de domaine créé la veille).
- [ ] Test délivrabilité (mail-tester.com ou équivalent) ≥ 9/10 sur un mail témoin.

## 2. ⛔ Base légale — RGPD / DGCCRF (bloqueur dur)
- [ ] **Preuve d'opt-in email** archivée et accessible (date, source, formulaire).
      Localisation : `__________`
- [ ] Contenu des mails relu : **aucun** « 1€ », **aucun** « -X % facture »/« X € économisés »
      non sourcé. Aides en qualitatif + ≤ 1 chiffre sourcé. (linter `templates.py` = filet, pas dispense)
- [ ] Pas de promesse « installation 48h » → formulation « **RDV expert CVC sous 48h** ».
- [ ] **Opt-out** présent et fonctionnel dans chaque mail (`OPTOUT_URL`).
- [ ] Mentions expéditeur / identité conformes (qui envoie, pourquoi).

## 3. `.env` à renseigner (copié de `.env.example`)
```
CALENDLY_URL=            # lien de prise de RDV expert CVC
OPTOUT_URL=              # page de désinscription (opt-out)
SENDER_NAME=             # nom affiché de l'expéditeur
SENDING_DOMAIN=          # domaine dédié
DRAFT_MODE=esp           # export mailmerge/ESP (déjà le défaut)
REASSURANCE_RGE=         # n° / mention RGE
REASSURANCE_DECENNALE=   # assurance décennale
REASSURANCE_NB_CHANTIERS=# nb de chantiers (réassurance)
DB_PATH=state.sqlite
WARMUP_J1=30
WARMUP_J2=50
WARMUP_MAX=100
# + secrets ESP au moment du câblage SMTP (voir §5) — jamais en dur, jamais commit
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
```
- [ ] `.env` rempli, **hors git** (déjà dans `.gitignore`).
- [ ] Secrets ESP jamais dans le code ni les logs (RGPD : pas de PII en logs).

## 4. Données — préparer la base
- [ ] Base réelle `.xlsx`/`.csv` déposée dans `data/` (gitignored).
- [ ] `python -m src.tri data/<base> --outdir out` → vérifier la synthèse (segments, isolés, « à rappeler »).
- [ ] `python -m src.db --db out/state.sqlite import out/segments` (import idempotent).
- [ ] `python -m src.drafts --db out/state.sqlite generate` → **0 draft non conforme** (sinon corriger templates).
- [ ] `python -m src.sequence --db out/state.sqlite plan` puis `simulate --days 7` → plafonds warm-up OK.

## 5. ⛔ Câblage du transport SMTP (reste à coder)
Aujourd'hui `src/sender.py` fournit uniquement `export_transport` (écrit des `.eml`).
Le **transport SMTP réel n'est pas implémenté** → à ajouter avant envoi automatisable :
- [ ] `smtp_transport(host, port, user, password, from_addr)` (TLS, timeout, retour True/False).
- [ ] Secrets lus depuis `.env` (jamais d'argument en clair, jamais loggés).
- [ ] Tests : envoi simulé (mock SMTP) + échec réseau → `failed++` sans tuer le batch.
- [ ] En attendant : mode **export `.eml`** validé à la main via l'ESP (déjà dispo).

## 6. Warm-up & premier envoi (déclenché par un humain)
- [ ] **Dry-run obligatoire** d'abord : `python -m src.sender --db out/state.sqlite send`
      → vérifier `dus` / `enverrait` / plafond, **0 envoi**.
- [ ] 1 mail témoin réel vers **une boîte à toi** (Gmail + Outlook) : arrive en **Inbox**, pas spam.
- [ ] Vérifier un `event sent` en base + un **bounce test** capté via `sender ingest <email> bounce`.
- [ ] Respecter le warm-up : J1 = 30, J2 = 50, plateau 100/j (déjà codé, `--day-index`).
- [ ] Envoi réel = `--confirm` + transport **explicite** (jamais par défaut).

## 7. Boucle quotidienne opérationnelle (routine cible)
1. `sender send` (dry-run) → voir les dus du jour.
2. Valider humainement → envoi réel (`--confirm`).
3. Ingestion retours (webhook ESP ou poll IMAP) → `events`.
4. `replies apply <contact_id> <classe>` → STOP blackliste, Intéressé → Calendly.
5. `report` (funnel + A/B) et `dashboard` pour le suivi.
- [ ] Ingestion des retours ESP câblée (webhook → `sender ingest`) — sinon suivi funnel partiel.

## 8. Avant la 1ʳᵉ campagne (méthode CLAUDE.md)
- [ ] **Pre-mortem** : « si ça a foiré dans 2 semaines, pourquoi ? » (délivrabilité, plaintes, opt-out ignorés, RDV nuls).
- [ ] **TEST POV** sur les mails finalisés : 3 POV dont **1 adversaire** (ex. DGCCRF, destinataire agacé, spam filter).
- [ ] Décision go/no-go tracée.

---

### Ordre de déblocage recommandé
`§1 DNS` (le plus long, à lancer en premier) → `§2 opt-in` → `§3 .env` → `§4 données` →
`§5 SMTP (code)` → `§6 warm-up témoin` → `§8 pre-mortem/POV` → **campagne**.

### Ce qui est déjà fait (rien à refaire)
Tri/segmentation, état SQLite, templates + linter de claims, génération de brouillons,
séquençage J0/J+4/J+8 + warm-up, traitement des réponses, reporting/A-B, dashboard, export `.eml`.
**93 tests passent.** Il ne manque que la config ci-dessus + le transport SMTP (§5).
