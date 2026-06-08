# TASKS.md — Séquencement du build (pour Claude Code)

Chaque phase a un **critère d'acceptation**. Ne pas passer à la suivante sans le valider.
Phase 1 reste à construire dans Claude Code (on repart de zéro — le code Phase 1 n'a
jamais été poussé dans ce dépôt).

---

## ✅ Phase 1 — TRI par chauffage  *(LIVRÉ)*
- `src/tri.py`, `src/models.py`, `src/config.py`, `src/logging_setup.py`,
  `tests/test_tri.py`, `tests/test_logging_setup.py`.
- **Acceptation** : `python -m pytest -q` → 32 passed. `python -m src.tri data/base.csv`
  produit `out/segments/*.csv`, `out/_isoles_qualite.csv`, `out/synthese.xlsx`.
- **Action immédiate (humain)** : déposer le vrai CSV dans `data/`, lancer, vérifier les comptes réels.

## ✅ Phase 2 — État & schéma SQLite  *(LIVRÉ)*
- `src/db.py`, `tests/test_db.py`. Tables `contacts` / `messages` / `events` (FK + CASCADE).
- Import idempotent depuis les CSV de segments. Dédup sur email (UNIQUE). EXCLU exclu par défaut (`--all` pour l'inclure).
- **Acceptation** : ré-import sans doublon (5 200 → 0 inséré / 5 200 mis à jour) ; `stats` = contacts par segment OK.
- CLI : `python -m src.db init|import out/segments|stats [--db state.sqlite]`.

## ✅ Phase 3 — Moteur de templates (mails)  *(LIVRÉ)*
- `src/templates.py`, `tests/test_templates.py`. 9 variantes (3 segments × {J0,J+4,J+8}),
  ton réactivation (base 100 % froid+), variables `dept`/`prenom` (fallback).
- **Linter de claims** (bloquant) : « 1€ », « X% », montants « X € », « installation 48h ».
  Règles structurelles : opt-out présent + 1 seul CTA Calendly. TEST POV adversaire inclus.
- Réassurance + Calendly + opt-out = placeholders `.env` (décennale & nb chantiers **à fournir**).
- **Acceptation** : les 9 variantes passent ; un message piégé est bloqué en test. CLI `python -m src.templates`.

## ✅ Phase 4 — Génération des brouillons  *(LIVRÉ)*
- `src/drafts.py`, `tests/test_drafts.py`. Un brouillon par contact (J0 par défaut), statut `draft`.
- **Aucun envoi déclenché par le code** (pas de réseau ici) ; idempotent sur (contact, position).
- Filet de sécurité : chaque draft repasse le linter avant insertion (jamais de message non conforme stocké).
- Export ESP : `python -m src.drafts export out/drafts_J0.csv`. CLI generate/export.
- **Acceptation** : 5 200 drafts générés/marqués `draft`, 0 event, 0 message envoyé.

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
