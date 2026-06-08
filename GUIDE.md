# GUIDE — DATA RÉNO Pipeline

Deux parties : **(1) ce que tu dois faire**, **(2) comment marche l'outil**.

---

## Partie 1 — Ce que TU dois faire

### A. Une seule fois (mise en place)
1. **Installer** :
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```
2. **Remplir `.env`** (ce sont « tes choses » mises de côté) :
   - `CALENDLY_URL`, `OPTOUT_URL`, `SENDER_NAME`
   - `REASSURANCE_DECENNALE`, `REASSURANCE_NB_CHANTIERS`, `REASSURANCE_RGE`
   - `SENDING_DOMAIN`
   > Tant qu'ils sont vides, les mails affichent des placeholders et **le linter
   > empêche tout chiffre non sourcé** — rien ne part de travers.
3. **Domaine d'envoi dédié** + **DNS SPF / DKIM / DMARC** configurés.
4. **Preuve d'opt-in email** archivée et accessible (base légale RGPD/DGCCRF).

### B. À chaque campagne (le « run » quotidien)
Les étapes 1→5 **n'envoient rien**. L'envoi (étape 7) n'a lieu qu'avec `--confirm`.
```bash
# 1. déposer ta base dans data/ (export Excel/CSV)
# 2. tri  → vérifier out/synthese.xlsx (comptes par segment)
python -m src.tri data/ta_base.xlsx --outdir out
# 3. charger l'état SQLite
python -m src.db --db out/state.sqlite import out/segments
# 4. générer les brouillons (statut draft)
python -m src.drafts --db out/state.sqlite generate
# 5. planifier la séquence + vérifier le warm-up
python -m src.sequence --db out/state.sqlite plan
python -m src.sequence --db out/state.sqlite simulate --days 7
# 6. RELIRE quelques brouillons : out/drafts_J0.csv   (← ta validation humaine)
# 7. ENVOYER : d'abord en simulation, puis pour de vrai
python -m src.sender --db out/state.sqlite send                      # DRY-RUN (rien envoyé)
python -m src.sender --db out/state.sqlite send --confirm --export-dir out/outbox --day-index 0
# 8. importer les retours (depuis ton ESP : bounce / ouverture / réponse / opt-out)
python -m src.sender --db out/state.sqlite ingest <email> bounce
# 9. traiter une réponse (tu valides la classe proposée)
python -m src.replies --db out/state.sqlite classify "son texte"     # propose
python -m src.replies --db out/state.sqlite apply <contact_id> INTERESSE
# 10. suivre
python -m src.report --db out/state.sqlite
python -m src.dashboard out/dashboard.html --db out/state.sqlite
```
> **`--day-index`** situe le jour dans le warm-up : `0` = 1ᵉʳ jour (plafond 30),
> `1` = 2ᵉ jour (50), `2` et + = plateau (100).

### C. Liste « à rappeler »
Les contacts **sans email** (8 678) sont dans `out/_a_rappeler_telephone.csv`.
⚠️ L'appel de prospection rénovation reste **juridiquement à risque** (DGCCRF) :
à utiliser selon ta décision / ton conseil juridique. L'outil n'appelle jamais.

### D. Règles à ne jamais enfreindre
- **Jamais d'auto-envoi** : c'est toujours toi qui lances `--confirm`.
- **Zéro claim** « 1 € » / « -X % » / « X € » non sourcé (le linter bloque déjà).
- **STOP / opt-out / bounce** → suppression automatique et définitive.

---

## Partie 2 — Comment marche l'outil

### Le flux
```
   ta base (.xlsx/.csv)
        │  src/tri.py        segmente, déduplique, isole, sort « à rappeler »
        ▼
   out/segments/*.csv ──► src/db.py ──►  state.sqlite (contacts)
                                          │
        src/templates.py (9 mails + linter de claims)
                                          │
        src/drafts.py  ─► messages (statut draft)   ◄─ aucun envoi
                                          │
        src/sequence.py ─► messages (scheduled, J0/J+4/J+8, warm-up)
                                          │
        src/sender.py  ─► [TON CLIC --confirm] ─► envoi ─► events(sent)
                                          │
        retours ESP ─► src/sender.py ingest ─► events(open/reply/bounce/optout)
                                          │
        src/replies.py ─► classe la réponse (tu valides) ─► actions auto
                                          │
        src/report.py / src/dashboard.py ─► funnel, A/B, vue HTML
```

### La base de données (`state.sqlite`)
| Table | Contenu |
|---|---|
| `contacts` | un prospect (email unique), son segment, son statut (`new`→`contacted`→`interested`/`rdv`/`stopped`…) |
| `messages` | les touches J0/J+4/J+8 par contact, statut `draft`→`scheduled`→`sent`/`cancelled` |
| `events` | journal : `sent`, `open`, `reply`, `bounce`, `optout`, `click` |
| `suppressions` | liste noire (STOP / bounce / opt-out) — plus jamais contactés |

### La segmentation (figée)
GAZ/FIOUL → **AIR_EAU** · ÉLEC → **AIR_AIR** · BOIS → **AIR_EAU_À_QUALIFIER** ·
déjà-PAC / inconnu / sans email → **EXCLU**. Priorité = surface croissante.

### Les garde-fous intégrés
- **Linter de claims** : un mail non conforme n'est jamais stocké ni envoyé.
- **Double verrou d'envoi** : il faut `--confirm` **et** un transport explicite.
- **Warm-up** : plafond 30 → 50 → 100 envois/jour, sur le total des touches.
- **Arrêts** : réponse / clic / opt-out / bounce → relances annulées immédiatement.
- **RGPD** : aucune PII dans les logs ; `data/` et `out/` jamais versionnés.

### Tester / vérifier à tout moment
```bash
python -m pytest -q      # 93 tests
ruff check src tests     # lint
```

### Quand l'outil est-il « opérationnel » ?
Dès que `.env` + DNS sont configurés : tu peux faire tourner le cycle complet
(étapes B.1→B.10) chaque jour, l'envoi restant déclenché par ton clic.
