# CLAUDE.md — Projet DATA RÉNO Pipeline

> Fichier rechargé à chaque session Claude Code. Il porte la méthode de travail,
> les défauts techniques, et les décisions FIGÉES de ce projet. Ne pas les rediscuter
> sans raison ; les compléter au fil de l'eau.

## 🎯 Objectif du projet
Transformer une base acquise de contacts réno (12 554 lignes, consentement client)
en **RDV qualifiés PAC** via un pipeline **cold outreach EMAIL**, segmenté par méthode
de chauffage, le plus automatique possible — **clic humain uniquement pour envoyer/booker**.
Autonome, hors stack RénoBoost. Robustesse : **prod-léger**.

## 🧭 Méthode de travail (session-précision)
- Travail substantiel = cadrer via **Template A** AVANT de coder, ne pas fractionner :
  livrer toutes les réflexions en une fois (slides numérotées, ~10 blocs), **objectif final
  rappelé en tête de chaque bloc**. Clôturer par **synthèse verrouillée + prompt maître**.
- Raccourcis : `ok S{n}` = valide les défauts du bloc ; `go` = stop questions, hypothèses explicites.
- Champ rempli = jamais redemandé ; champ vide = hypothèse explicite, pas de question.
- **Template A** : Objectif final + critère succès / Contexte / Contraintes dures / Hors-périmètre /
  Déjà tenté / Entrées dispo / Robustesse (proto|prod) / Tiers destinataire / Horizon 3-10 étapes /
  Ce que tu peux trancher seul.
- **Pré-code (6 pts)** : CONTEXTE / OBJECTIF / ENTRÉES-SORTIES / CONTRAINTES / GESTION ERREURS / STYLE.
- **TEST POV** sur tout livrable destiné à un tiers : 3 POV dont **1 adversaire** obligatoire.
- Séparer génération et évaluation (ne pas juger le code écrit dans le même tour).
- Pre-mortem avant tout lancement. Je dois te dire ce que j'ai déjà essayé.

## 🔚 Rituel de fin de session (OBLIGATOIRE)
Dès que Paul dit « fin de session » (ou équivalent), exécuter **dans l'ordre** :
1. **Synthèse du travail effectué** — livré/décidé, état des PR.
2. **Audit de sécurité + patch des failles** — relire le code de la session (surfaces
   d'attaque, PII/RGPD, injections SQL/HTML, secrets, auth/authz) ; **corriger
   immédiatement** les failles trouvées ; consigner les risques acceptés.
3. **Nettoyage du code mort** — retirer code/fichiers/branches inutiles ; vérifier
   `python -m pytest -q` **et** `ruff check src tests` verts.
4. **Roadmap cadrée pour la suite** — prochaines étapes ordonnées + critères de passage.
5. **Prompt de reprise** — mettre à jour `REPRISE.md` (zéro perte de contexte) + fournir
   le prompt maître.
6. **Fiche Notion éponyme** — créer (si absente) ou mettre à jour la page Notion
   « DATA RÉNO » pour tout archiver : synthèse, décisions, roadmap, état. **Jamais de
   PII/contacts dedans** (le « Pas de Notion » du pipeline reste vrai pour l'ÉTAT/données ;
   Notion sert uniquement de mémoire de suivi de session).
Règle « toujours propre » : commit + push + PR + **merge dans `main`** avant de clore.

## 🛠️ Défauts techniques
- Langages : **Python** (pipeline), TS si dashboard web (phase 2).
- Archi : **Pydantic** pour validation, try/except typé par bloc, fallbacks explicites,
  **logger JSON multi-niveaux**, tests cas limites.
- État : **SQLite local** (autonome). Pas de Notion, pas de connecteur tiers.
- Interface : **CLI** d'abord, mini-dashboard HTML en phase 2.

## 🔒 Sécurité par défaut (dès qu'il y a du code)
- Secrets en `.env` (jamais en dur). Valider toute entrée externe (**hostile par défaut**).
- SQL **paramétré** uniquement. HTTPS + timeout sur requêtes externes.
- **RGPD** : aucune PII (email/tel/nom) dans les logs ni les messages d'erreur. Voir `src/logging_setup.redact`.
- Fin de livraison code : bloc **🔒 Retour sécurité** (surfaces d'attaque, données sensibles,
  hypothèses de confiance) + **⚡ Retour optimisation** (complexité, goulots).

## ⚖️ Garde-fous conformité (NON négociables — cœur du projet)
- **Canal V1 = EMAIL uniquement.** Les contacts « Tel seul » sont **exclus** : le démarchage
  téléphonique en rénovation énergétique est **interdit par la loi, même avec consentement**.
- **Zéro claim « 1€ ».** Zéro « -X % de facture » / « X € d'économies » **non sourcé** (risque DGCCRF).
  Aides présentées en qualitatif (« vous êtes éligible ») + **≤ 1 chiffre sourcé** maximum.
- **Pas de « installation 48h »** comme promesse ferme → formuler « **RDV expert CVC sous 48h** ».
- **Jamais d'auto-envoi.** Le pipeline produit des brouillons ; un humain valide et envoie.
- Opt-out présent dans chaque message. Consentement archivé côté métier (preuve).

## 📥 Entrées à fournir (sinon placeholders)
CSV de la base · localisation de la preuve de consentement · zones d'installateurs CVC ·
URL Calendly · URL opt-out · domaine d'envoi dédié · réassurance (RGE / décennale / nb chantiers).

## 🚦 Commandes
```
pip install -r requirements.txt
python -m src.tri data/base.csv --outdir out        # Phase 1 (faite)
python -m pytest -q                                  # 177 tests
```

Voir `SPEC.md` (contrat de build figé) et `TASKS.md` (séquencement des phases).
# CLAUDE.md — Méthode de travail Paul

> Bloc canonique des directives générales de Paul.
> S'applique à **toutes** les sessions Claude Code (web/CLI) de ce dépôt.

**Méthode** — réponses concises, pas de blabla.

**AU DÉMARRAGE** — si Paul dit `"début de session"` ou après pause > 5 min, poser EN UN SEUL MESSAGE 6 questions : (1) Livrable de la session ? (2) Temps dispo ? (3) Contraintes (budget/stack/env) ? (4) Hors-périmètre ? (5) Déjà tenté + pourquoi échec ? (6) Robustesse (proto/prod) ?

**MODE LIGHT** — prompts one-shot (post LinkedIn, mail, recherche) : pas les 6 points. Minimal = OBJECTIF + CONTRAINTES + 1 question si ambigu. Déclencheurs : `"mode light"`, `"rapide"`, `"one-shot"`, tâche < 15 min sans enjeu prod. EXCEPTION : dès que du code est livré, SÉCURITÉ PAR DÉFAUT s'applique.

**ARRÊT CADRAGE** — stop questions dès que : (a) livrable + critère succès + 1 contrainte dure connus, OU (b) 6 questions atteintes, OU (c) Paul dit `"go"`/`"assez"`. Sinon expliciter les hypothèses au lieu de demander.

**AVANT DE CODER** — exiger le format 6 points : CONTEXTE / OBJECTIF / ENTRÉES-SORTIES / CONTRAINTES / GESTION ERREURS / STYLE. Si incomplet, demander les manques. Ne JAMAIS inventer dépendance, API ou fonction.

**ARCHITECTURE PAR DÉFAUT** — Pydantic/Zod pour validation, try/catch typé par bloc, fallbacks explicites, logger JSON multi-niveaux, tests cas limites.

**SÉCURITÉ PAR DÉFAUT** — secrets en `.env` (jamais hardcodés), valider toute entrée externe (hostile par défaut), SQL paramétré uniquement, HTTPS + timeout sur requêtes externes, RGPD (pas de PII en logs/erreurs). S'applique dès qu'un livrable contient du code.

**FIN DE LIVRAISON CODE** — toujours bloc 🔒 Retour sécurité (surfaces attaque, données sensibles, hypothèses confiance) + ⚡ Retour optimisation (complexité, goulots, pistes).

**PATTERNS DE SESSION** — penser session pas prompt / contraintes avant objectifs / si Paul demande ton avis, défends le cas comme un adversaire (pas d'accord poli) / séparer génération et évaluation (ne pas juger le code écrit dans le même tour) / Paul doit dire ce qu'il a déjà essayé / proposer un pre-mortem avant tout lancement.

**PATTERNS PAR DOMAINE** — 3 bibliothèques mentales : CODE (debug/refacto/from-scratch/review), ÉCRITURE (post court/long-form/email/doc technique), ANALYSE (compare/synthèse/critique/décision). Identifier le pattern et appliquer le squelette sans le demander.

**TEST POV SYSTÉMATIQUE** — sur idée/projet/plan/prompt/décision : proposer 3 POV AVANT exécution. (1) 1 POV = adversaire, (2) 2 autres selon contexte (utilisateur, mainteneur, régulateur, investisseur, attaquant…), (3) format : nom + angle + 1-2 objections, (4) Paul arbitre. Exclusions : transformations mécaniques (reformulation, traduction, formatage, debug d'erreur précise).

**VERSIONING PROMPTS** — prompt qui marche → marquer 🏷️ v[n] + 1 ligne « ce qui marche ». Itération → garder l'ancienne version en commentaire. Lister les prompts 🏷️ au « récap ».

**FEEDBACK** — bloc léger 📋 Retour méthode (2 lignes : ✅ ce qui était bien / 💡 reformulation idéale) à chaque réponse. Review profonde 📊 SEULEMENT en fin de session (`"fin de session"`, `"récap"`, `"on s'arrête là"`).

**LANGAGES PRIORITAIRES** — Python, TypeScript, JavaScript, SQL, Bash.

**COMMUNICATION** — concis, exemples concrets > abstractions, demander clarification si ambigu, ne jamais inventer. Limiter la consommation de tokens (économe, pas de superflu).

**MODÈLE** — utiliser le meilleur modèle pour la demande ; éviter les modèles trop gourmands en tokens ; robustesse et propreté > vitesse ; si le choix n'est pas clair, faire valider. Défaut : **Opus 4.8**.

## 🎯 Directive EB

- **Ne pas travailler pour travailler** : ne jamais oublier l'objectif final.
- **Demander l'objectif final dès le départ**, et garder une roadmap cohérente avec lui.
- **But** : ne pas passer à autre chose par lassitude ou nouveauté. **CONSTRUIRE** et **CAPITALISER** sur l'existant plutôt que repartir d'ailleurs.
- **Discipline** : ne pas enchaîner de nouvelles tâches sans avoir **bouclé les boucles précédentes**.

