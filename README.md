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
3. Pipeline complet (déposer la base `.xlsx`/`.csv` dans `data/`) :
   ```bash
   # 1. Tri : segments + dédup + isolés + liste « à rappeler » + synthèse
   python -m src.tri data/<ta_base>.xlsx --outdir out
   # 2. État SQLite (import idempotent des contacts activables)
   python -m src.db --db out/state.sqlite import out/segments
   # 3. Brouillons (statut draft, aucun envoi)
   python -m src.drafts --db out/state.sqlite generate
   # 4. Séquençage J0/J+4/J+8 + warm-up (aucun envoi)
   python -m src.sequence --db out/state.sqlite plan
   python -m src.sequence --db out/state.sqlite simulate --days 7
   # 5. Envoi — DRY-RUN par défaut ; envoi réel = --confirm + transport
   python -m src.sender --db out/state.sqlite send                      # simulation
   python -m src.sender --db out/state.sqlite send --confirm --export-dir out/outbox
   # 6. Ingestion d'un retour (webhook/IMAP côté infra)
   python -m src.sender --db out/state.sqlite ingest <email> bounce
   # 7. Réponses (l'humain valide la classe proposée)
   python -m src.replies --db out/state.sqlite apply <contact_id> STOP
   # 8. Reporting & A/B + dashboard
   python -m src.report --db out/state.sqlite
   python -m src.dashboard out/dashboard.html --db out/state.sqlite
   ```
   Tests + lint :
   ```bash
   python -m pytest -q && ruff check src tests
   ```
4. `TASKS.md` = phases + critères · `ROADMAP.md` = chemin vers l'opérationnel · `SPEC.md` = contrat figé.

## Structure
```
CLAUDE.md      méthode + défauts + décisions + garde-fous (chargé par Claude Code)
SPEC.md        synthèse verrouillée + prompt maître
TASKS.md       plan de build séquencé (phases + critères d'acceptation)
src/           config, models (Pydantic), logging_setup (JSON sans PII), tri, db,
               templates (+linter), drafts, sequence, replies, report, sender, dashboard
tests/         pytest (cas limites)
templates/     variantes de mails (segment × position)
data/          CSV d'entrée (gitignored)
out/           segments + rapport qualité + synthèse (gitignored)
```

## Non négociable
Email seul en V1 · « Tel seul » exclus (démarchage tél réno interdit) · zéro « 1€ » / claim non sourcé ·
jamais d'auto-envoi · opt-out systématique. Détail dans `CLAUDE.md`.
