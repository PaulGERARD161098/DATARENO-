# SPEC.md — Contrat de build figé (session-précision)

🎯 *12 554 contacts → RDV qualifiés PAC, segmenté chauffage, max auto + compliant.*

## Décisions verrouillées

| Bloc | Décision |
|---|---|
| **Data** | Base = CSV. Consentement affirmé (preuve archivée côté métier). Périmètre = 12 554 + sous-tag `froid+` si dernier contact > 365 j. |
| **Segments** | GAZ/FIOUL→`AIR_EAU` · ÉLEC→`AIR_AIR` · BOIS→`AIR_EAU_A_QUALIFIER` · déjà-PAC/inconnu→`EXCLU`. Priorité = surface ↑. Géo = national (tant que zones CVC non fournies). |
| **Canal** | **Email seul (V1).** « Tel seul » exclus (appel réno interdit). Domaine dédié. Opt-out obligatoire. Warm-up 30→50→100/j. |
| **Offre** | Aides qualitatives + ≤1 chiffre sourcé. **Zéro « 1€ », zéro « -X% » non sourcé.** Audit = appel découverte. « RDV expert sous 48h » (pas « installation 48h »). CTA = Calendly. Réassurance RGE/décennale/chantiers. Ton vous, direct. |
| **Séquence** | 3 touches : J0 valeur / J+4 fenêtre aides / J+8 dernière chance. Arrêts : réponse/clic/opt-out/bounce. Non-répondeurs → recycler à 3 mois. |
| **Mails** | 9–12 variantes (segment × position). Variables : chauffage + dept (prénom si présent, fallback). Sortie = drafts validés 1×1. **Jamais d'auto-envoi.** |
| **Réponses** | Classes : Intéressé / RDV pris / À recontacter / Pas intéressé / STOP / Bounce. IA propose → humain valide. Actions auto : Intéressé→Calendly, STOP→blacklist, Bounce→purge, Recontacter→file 3 mois. |
| **Outil** | SQLite local autonome, hors stack RénoBoost. Auto = tri + génération + classement + reporting ; clic humain pour envoyer/booker. CLI now, dashboard HTML phase 2. Prod-léger. |
| **Mesure** | KPIs jusqu'au RDV (délivré→ouvert→répondu→RDV). A/B objet. Ajustement = reco, l'humain décide. |

## 🏷️ PROMPT MAÎTRE v1 — DATA RÉNO
```
CONTEXTE : Base acquise de contacts réno (consentement client). Colonnes : Nom, Email, Tel,
CP, Dept, Chauffage{GAZ|FIOUL|BOIS|ÉLECTRICITÉ}, Surface, Campagne, Date.
OBJECTIF : Pipeline cold outreach EMAIL → RDV qualifiés PAC, segmenté par chauffage.
Max auto, clic humain seulement pour envoyer/booker. Compliant DGCCRF + canal.
ENTRÉES/SORTIES : in = CSV. out = segments/, drafts mail, base SQLite état, reporting.
SEGMENTATION : GAZ/FIOUL→air/eau ; ÉLEC→air/air ; BOIS→air/eau à qualifier ;
déjà-PAC/inconnu→exclu. Priorité surface ↑. Exclure « Tel seul » du canal tél.
MESSAGE : 3 touches (J0/J+4/J+8), 1 CTA = Calendly. Aides qualitatives + ≤1 chiffre sourcé.
Interdits : « 1€ », « -X% » non sourcé, « installation 48h » (→ « RDV expert sous 48h »).
RÉPONSES : classer {Intéressé|RDV|Recontacter|PasIntéressé|STOP|Bounce}, IA propose→humain valide.
CONTRAINTES : Python, SQLite local, hors stack tiers. Prod-léger : Pydantic, try/except typé,
logs JSON sans PII, reprise sur erreur, tests cas limites. Secrets en .env. HTTPS+timeout.
GESTION ERREURS : lignes invalides isolées + reportées (jamais droppées). STYLE : typé, fonctions pures, CLI.
```

## 🏷️ GABARIT GÉNÉRIQUE (futurs projets)
```
▶️ MODE : session-précision
🎯 OBJECTIF FINAL + critère succès :
🧭 CONTEXTE :        ⛓️ CONTRAINTES DURES :      🚫 HORS-PÉRIMÈTRE :
🔁 DÉJÀ TENTÉ :      📥 ENTRÉES DISPO :          🛡️ ROBUSTESSE : proto|prod
👥 TIERS DESTINATAIRE :   🔭 HORIZON (3-10 étapes) :   ✅ TU PEUX TRANCHER SEUL :
+ 6 pts pré-code : CONTEXTE / OBJECTIF / ENTRÉES-SORTIES / CONTRAINTES / GESTION ERREURS / STYLE
```
