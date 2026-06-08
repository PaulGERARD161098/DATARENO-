# TASKS.md — Séquencement du build (pour Claude Code)

Chaque phase a un **critère d'acceptation**. Ne pas passer à la suivante sans le valider.
Phase 1 reste à construire dans Claude Code (on repart de zéro — le code Phase 1 n'a
jamais été poussé dans ce dépôt).

---

## ⬜ Phase 1 — TRI par chauffage
- `src/tri.py`, `src/models.py`, `src/config.py`, `src/logging_setup.py`, `tests/test_tri.py`.
- **Acceptation** : `python -m pytest -q` vert. `python -m src.tri data/base.csv` produit
  `out/segments/*.csv`, `out/_isoles_qualite.csv`, `out/synthese.xlsx`.
- **Action immédiate** : déposer le vrai CSV dans `data/`, lancer, vérifier les comptes réels.

## ⬜ Phase 2 — État & schéma SQLite
- Table `contacts` (depuis segments), `messages` (séquence), `events` (envoi/ouverture/réponse).
- Import idempotent depuis les CSV de segments. Dédup sur email.
- **Acceptation** : ré-import sans doublon ; requête « contacts par segment » OK.

## ⬜ Phase 3 — Moteur de templates (mails)
- 9–12 variantes (segment × {J0, J+4, J+8}). Variables : `chauffage`, `dept`, `prenom` (fallback).
- **Garde-fous (bloquants au build)** : linter de claims → rejeter tout « 1€ », « X% », « X € »
  non whitelisté, « installation 48h ». 1 seul CTA = Calendly. Opt-out présent. Ton vous.
- **Acceptation** : rendu des 12 variantes ; le linter bloque un message non conforme en test.

## ⬜ Phase 4 — Génération des brouillons
- Produire les drafts (Gmail si Workspace, sinon export mailmerge CSV pour l'ESP du domaine dédié).
- **Jamais d'auto-envoi.** Statut `draft` en base ; envoi = action humaine.
- **Acceptation** : N drafts générés, marqués `draft`, aucun envoi déclenché par le code.

## ⬜ Phase 5 — Séquençage & warm-up
- Planifier J0/J+4/J+8 par contact. Respect du warm-up (30→50→100/j). Conditions d'arrêt.
- **Acceptation** : simulation 7 jours respectant le plafond quotidien et les arrêts.

## ⬜ Phase 6 — Traitement des réponses
- Classer {Intéressé|RDV|Recontacter|PasIntéressé|STOP|Bounce} : IA propose → humain valide.
- Actions auto par classe (STOP→blacklist immédiate, Bounce→purge, Intéressé→lien Calendly).
- **Acceptation** : jeu de réponses test correctement pré-classé ; STOP blackliste sans envoi futur.

## ⬜ Phase 7 — Reporting & A/B
- KPIs jusqu'au RDV (délivré→ouvert→répondu→RDV). A/B sur objet. Sortie = reco (humain décide).
- **Acceptation** : rapport lisible + reco de variant gagnant, sans bascule auto.

## ⬜ Phase 8 — Dashboard HTML local *(optionnel)*
- Vue état pipeline + file de validation des drafts/réponses. Local, lecture SQLite.

---

### Règles transverses (rappel CLAUDE.md)
- TEST POV (dont 1 adversaire) avant chaque livrable destiné à un tiers (= les mails).
- Bloc 🔒 sécurité + ⚡ optimisation en fin de chaque phase de code.
- Pre-mortem avant la première campagne réelle.
