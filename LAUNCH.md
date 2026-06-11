# LAUNCH.md — runbook de la 1ʳᵉ campagne réelle

> Séquence opératoire pas-à-pas, du feu vert au régime de croisière. À suivre une
> fois `DEPLOY.md` fait (install + `.env`). Chaque étape a un **critère de passage**.

## Étape 0 — Pré-requis HORS outil (bloquants)
- [ ] **B2** Base légale opt-in email vérifiée et **archivée** (preuve nominative).
- [ ] **A5** DNS du domaine dédié : **SPF + DKIM + DMARC** → `mail-tester.com` ≥ 9/10.
- [ ] `.env` complet (liens https, SMTP, IMAP, Calendly, réassurance).
> Tant que ces 3 cases ne sont pas cochées : **ne pas lancer**.

## Étape 1 — Préparer l'état
```bash
python -m src.tri data/base.csv --outdir out
python -m src.db   --db out/state.sqlite import out/segments
python -m src.db   --db out/state.sqlite hygiene      # purge rôle/jetable
python -m src.drafts   --db out/state.sqlite generate
python -m src.sequence --db out/state.sqlite plan
```
**Passage :** `sequence plan` annonce un nombre de messages programmés cohérent.

## Étape 2 — Gate Go/No-Go
```bash
python -m src.preflight --db out/state.sqlite check    # exit 0 = GO
```
**Passage :** verdict **GO** (aucun FAIL). Les WARN (IMAP/Calendly/hygiène) sont à lire.

## Étape 3 — Micro-lot test (20-30 envois)
Le vrai pre-mortem grandeur réelle. On envoie un tout petit lot et on observe.
```bash
python -m src.daily --db out/state.sqlite run --confirm --smtp --limit 25
```
**Observer pendant 48-72 h :**
- [ ] Les mails arrivent en **inbox** (pas spam) — tester sur Gmail + Outlook perso.
- [ ] Bounces remontés : `python -m src.inbox --db out/state.sqlite poll`.
- [ ] L'**opt-out** est cliquable et fonctionnel (cliquer pour de vrai).
- [ ] Un **RDV test** réservé via le lien est capté : `python -m src.calendly --db ... poll`.
- [ ] `python -m src.report` et `python -m src.scoring report` se remplissent.
**Passage :** 0 plainte, bounce-rate < 5 %, inbox OK, opt-out OK, 1 RDV test capté.

## Étape 4 — Montée en volume (warm-up automatique)
Brancher le cron quotidien (voir `DEPLOY.md §6`). Le warm-up s'applique seul
(30 → 50 → 100/j selon les jours déjà envoyés). **Sans `--limit`**, le run du jour
respecte le plafond warm-up.
```cron
0 9 * * 1-5  cd /opt/datareno && . .venv/bin/activate && \
             python -m src.preflight --db out/state.sqlite check && \
             python -m src.daily --db out/state.sqlite run --confirm --smtp >> out/daily.log 2>&1
```
**Surveiller chaque jour :** `out/daily.log` (cherchez `circuit_breaker`, `blocked_*`),
le bounce-rate, et le taux d'arrivée en inbox.

## Étape 5 — Exploitation commerciale (le pipe)
- **Leads chauds** : `python -m src.scoring report` → relancer en priorité les
  **CLIQUEURS sans réponse** (intention montrée, pas encore booké). C'est là que sont les RDV.
- **Réponses** : valider la classe proposée par le poll : `python -m src.replies apply <id> <CLASSE>`.
- **Recontact 3 mois** (hebdo) : `python -m src.recontact --db ... requeue --and-plan`.
- **Pilotage** : `python -m src.report` (funnel + reco A/B) et
  `python -m src.dashboard out/dashboard.html` (RDV, leads chauds, paliers, A/B).

## Si ça dérape
- **Bounce-rate qui monte** → le coupe-circuit bloque l'envoi (logge `circuit_breaker`).
  Nettoyer la liste (`db hygiene`, vérifier la qualité des emails) avant de reprendre.
- **Spam / réputation** → ralentir (relancer avec `--limit` bas), vérifier DNS, contenu.
- **Plainte / demande RGPD** → le STOP/opt-out blackliste ; vérifier l'archivage du consentement.
