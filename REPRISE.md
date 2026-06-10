# REPRISE.md — prompt d'ouverture de session (coller tel quel, puis suivre)

> Mis à jour en fin de chaque session. Objectif : zéro perte de contexte, reprise immédiate.

---

## 📋 PROMPT MAÎTRE DE REPRISE (à coller en ouverture)

```
Projet : DATA RÉNO Pipeline — cold outreach EMAIL d'une base réno (B2C, 5 200 emailables)
vers RDV PAC. Python + SQLite local, autonome. Repo : paggerard-boop/DATARENO-.
Tout auto SAUF 2 clics humains : envoyer + booker. Conformité DGCCRF/RGPD = cœur.

ÉTAT À LA FERMETURE (2026-06-10) :
- Branche de travail : claude/datareno-pipeline-setup-km56q4 (PR #2 draft vers main,
  CI verte). 128 tests verts, ruff clean. Working tree propre, tout poussé.
- OUTIL COMPLET ET OPÉRATIONNEL (build terminé) :
  src/ = tri, db, templates(+linter claims+placeholders+A/B), drafts, sequence,
  sender(SMTP réel+export .eml+dry-run défaut), inbox(poll IMAP), daily(run quotidien),
  recontact(remise en file 3 mois), replies, report(A/B), dashboard, config, models,
  logging_setup(JSON sans PII).
- Garde-fous actifs (issus du pre-mortem, voir PREMORTEM.md) :
  warm-up AUTO (day_index déduit des envois passés, départ 30/j) · refus placeholders
  [..] à l'export ET à l'envoi · liste de suppression appliquée partout (envoi + export
  ESP) · coupe-circuit bounce-rate (BOUNCE_RATE_LIMIT=5%, échantillon min 50) ·
  TLS vérifié + timeout SMTP/IMAP · anti header-injection · jamais d'auto-envoi.

GESTE QUOTIDIEN CIBLE (déjà câblé) :
  python -m src.daily run --confirm --smtp        # ingère retours PUIS envoie le dû
  python -m src.recontact requeue --and-plan      # hebdo : réinjecte les 3 mois échus
  python -m src.report                            # funnel + reco A/B (humain décide)

"MES CHOSES" EN ATTENTE (bloquant l'envoi réel — les CLI refusent tant que vide) :
  1. B2 = base légale opt-in email vérifiée/archivée → LE SEUL SHOWSTOPPER (légal).
  2. DNS SPF/DKIM/DMARC du domaine dédié + test mail-tester.com (A5).
  3. .env : SMTP_HOST/USER/PASSWORD, SENDER_EMAIL, UNSUBSCRIBE_MAILTO,
     IMAP_HOST/USER/PASSWORD, CALENDLY_URL, OPTOUT_URL, SENDER_NAME,
     REASSURANCE_RGE/DECENNALE/NB_CHANTIERS.
  4. UI GitHub : merger la PR #2 (la passer ready-for-review) ; supprimer la branche
     remote claude/intelligent-brahmagupta-5JMtm (proxy 403 → manuel).

CHANTIERS OUVERTS (par valeur décroissante) :
  a) Câbler le RDV réel : webhook/poll Calendly → event 'rdv' (ferme le funnel
     jusqu'à l'objectif final ; aujourd'hui la métrique RDV est manuelle). [C2]
  b) Micro-lot test 20-30 contacts après config .env + DNS (gate PREMORTEM.md §6),
     puis montée en volume sous warm-up.
  c) Cron/systemd-timer du daily run + alerting simple (le coupe-circuit logge mais
     ne notifie pas).
  d) Personnalisation prénom : table contacts a 'nom', template attend 'prenom',
     jamais peuplé → splitter nom→prénom dans drafts (engagement + anti-spam). [C1]
  e) Re-lint des corps stockés au moment de l'envoi (si .env change après génération). [B5]

DETTES TECHNIQUES (non bloquantes) :
  - plan_sequence O(contacts×horizon) : OK à 5k, revoir si ×10 (executemany,
    index events(type, created_at)).
  - _stopped_contacts et auto_day_index scannent events sans index sur type.
  - inbox._known_email : un DSN forgé peut supprimer un contact (fail-safe assumé,
    documenté — voir Retour sécurité du 2026-06-10).

VÉRIF INITIALE : git status && git log --oneline -5
  puis pip install -r requirements.txt && python -m pytest -q && ruff check src tests
LECTURES : PREMORTEM.md (gate Go/No-Go §6) · ROADMAP.md (acquis opérationnels) ·
  GUIDE = README.md.

QUESTION D'OUVERTURE — choisis une porte avant de coder :
  a) Câbler le RDV Calendly → event 'rdv' (fermer le funnel).
  b) Préparer le micro-lot test (checklist gate + script de vérification pré-envoi
     automatisé : .env complet, DNS, opt-out cliquable, suppression à jour).
  c) Cron + alerting du daily run.
  d) Personnalisation prénom (C1).
Si je réponds « go » : prendre (b) puis (a), hypothèses explicites, zéro question.
```

---

## Rappels de méthode (CLAUDE.md, inchangés)
- Travail substantiel = Template A avant de coder ; `ok S{n}` valide un bloc ; `go` = stop questions.
- TEST POV (1 adversaire) sur tout livrable tiers. Pre-mortem avant tout lancement → **fait**, voir `PREMORTEM.md`.
- Fin de livraison code = bloc 🔒 Retour sécurité + ⚡ Retour optimisation.
- Fin de session = nettoyage code mort + audit sécu + mise à jour de ce fichier.
