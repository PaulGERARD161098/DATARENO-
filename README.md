# DATA RÉNO Pipeline

Pipeline **cold outreach email** d'une base de contacts réno → **RDV qualifiés PAC**.
Segmentation par méthode de chauffage, conforme (DGCCRF + canal), max automatique
avec **clic humain pour envoyer/booker**. Autonome (SQLite local), hors stack RénoBoost.

## Démarrer dans Claude Code
1. Ouvrir ce dossier comme repo dans Claude Code (`claude` dans le terminal, ou app/IDE).
   `CLAUDE.md` est chargé automatiquement : méthode + décisions figées + garde-fous.
2. Installer :
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env        # renseigner au fil des phases
   ```
3. Phase 1 (tri) — déposer le CSV de la base puis :
   ```bash
   python -m src.tri data/<ta_base>.csv --outdir out
   python -m pytest -q
   ```
4. Suite : suivre `TASKS.md` phase par phase. `SPEC.md` = contrat de build figé.

## Structure
```
CLAUDE.md      méthode + défauts + décisions + garde-fous (chargé par Claude Code)
SPEC.md        synthèse verrouillée + prompt maître
TASKS.md       plan de build séquencé (phases + critères d'acceptation)
src/           config, models (Pydantic), logging_setup (JSON sans PII), tri, db,
               templates, drafts, sequence, replies, report  (placeholders par phase)
tests/         pytest (cas limites)
templates/     variantes de mails (segment × position)
data/          CSV d'entrée (gitignored)
out/           segments + rapport qualité + synthèse (gitignored)
```

## Non négociable
Email seul en V1 · « Tel seul » exclus (démarchage tél réno interdit) · zéro « 1€ » / claim non sourcé ·
jamais d'auto-envoi · opt-out systématique. Détail dans `CLAUDE.md`.
