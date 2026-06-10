# PREMORTEM — DATA RÉNO Pipeline (avant la 1ʳᵉ campagne réelle)

> Consigne `CLAUDE.md` : *pre-mortem avant tout lancement*. On se projette **3 mois
> après la 1ʳᵉ campagne réelle** : elle a échoué. On remonte des symptômes aux causes
> racines. Chaque cause est taguée **[CODE]** (corrigible dans ce repo) ou **[OPS]**
> (config / légal / infra — côté métier). Objectif rappelé : *base 2023 froid+ → RDV PAC
> qualifiés, max auto, 2 clics humains (envoyer/booker), conformité DGCCRF/RGPD = cœur.*

## 1. Le scénario catastrophe à éviter
> « Sur 5 200 envois, le domaine dédié blacklisté en J+6, 70 % en spam, 3 plaintes RGPD
> (dont 1 CNIL pour opt-out non fonctionnel), zéro RDV, domaine grillé 6 mois. »

Les causes se classent par **gravité × silence** : un risque silencieux est pire (rien
ne t'alerte avant le mur).

## 2. 🔴 Famille A — Délivrabilité / domaine grillé (la plus irréversible)

| # | Cause racine | Tag | Signal précoce | Parade |
|---|---|---|---|---|
| A1 | **Warm-up non appliqué auto** : `send_due(day_index=2)` ⇒ plafond 100/j dès le 1ᵉʳ envoi au lieu de 30. Le ramp 30→50→100 dépend d'un argument manuel. | CODE | aucun (silencieux) | `day_index` **auto** = nb de jours distincts déjà envoyés ✅ corrigé |
| A2 | **Le chemin ESP-mailmerge contourne tous les garde-fous** : aucun event `sent` ⇒ plafond aveugle, suppression aveugle, annulation STOP aveugle. | CODE | cap jamais atteint dans le tool | privilégier `send_due` (transport) ; garde-fous re-câblés à l'export ✅ partiel |
| A3 | **`export_mailmerge` n'applique pas la suppression** (≠ `due_messages`) ⇒ envoi possible à des STOP/bounce/optout. | CODE | plainte « j'avais dit STOP » | filtre suppression à l'export ✅ corrigé |
| A4 | **Aucun coupe-circuit bounce-rate** : base 2023 = adresses mortes ; > 5 % blackliste, rien ne stoppe. | CODE | bounces qui montent | circuit-breaker bounce-rate ✅ corrigé |
| A5 | **SPF/DKIM/DMARC + domaine neuf** sans historique : 5 200 mails = corde raide. | OPS | Postmaster Google/Outlook | DNS validés + warm-up réel + volume bas |

## 3. 🔴 Famille B — Conformité DGCCRF / RGPD (cœur du projet)

| # | Cause racine | Tag | Parade |
|---|---|---|---|
| B1 | **Les placeholders passent le linter** : `validate_message` vérifie la *présence* des liens, pas qu'ils soient réels ⇒ envoi possible avec `[LIEN_DESINSCRIPTION]` (opt-out mort = violation) et `[VOTRE_LIEN_CALENDLY]` (CTA mort). | CODE | refus d'envoi/export si un placeholder `[..]` subsiste ✅ corrigé |
| B2 | **Consentement de base acquise ≠ opt-in email pour CE responsable de traitement.** Base 2023 : couvre-t-elle un cold email d'un expéditeur différent 3 ans après ? **Plus gros risque légal, 100 % hors code.** | OPS/légal | vérifier la base légale (preuve opt-in nominative + finalité + responsable) avant tout envoi |
| B3 | **Rétention RGPD** : prospect > 3 ans (CNIL). Des contacts début-2023 sont à la limite à mi-2026. | OPS | purger / justifier les plus anciens |
| B4 | **STOP arrivé dans l'ESP mais non ingéré** ⇒ J+4/J+8 partent quand même = aggravant. L'annulation ne marche que si le STOP est ingéré **avant** le batch suivant. | CODE+OPS | ingestion auto (webhook/IMAP) avant montée en volume |
| B5 | **Corps non re-linté** si `.env`/réassurance change après génération. | CODE | re-lint à l'envoi |

Le **linter de claims** (1€, %, montants, « installation 48h ») est solide — c'est le
maillon le mieux tenu. Les trous sont autour : placeholders, consentement, timing STOP.

## 4. 🟠 Famille C — Funnel mort / vol à l'aveugle

| # | Cause racine | Tag | Parade |
|---|---|---|---|
| C1 | **Zéro personnalisation : « Bonjour, »** partout (`prenom` jamais peuplé ; la table a `nom`). Générique = signal spam + engagement bas. | CODE | splitter `nom`→prénom, ou retirer la variable |
| C2 | **RDV invisible** : pas de retour booking Calendly câblé ⇒ la métrique « RDV » (objectif final !) est creuse sauf saisie manuelle. | CODE+OPS | webhook Calendly → event `rdv` |
| C3 | **Sans ingestion, le funnel s'arrête à `sent`** ⇒ on ne sait pas si ça marche. | OPS | câbler bounces + réponses avant J0 |
| C4 | A/B objet impossible : 1 seul objet par position. | CODE | variantes (porte b) |

## 5. TEST POV (3 perspectives, 1 adversaire obligatoire)

- **POV destinataire** (contact 2023) : reçoit un mail d'un expéditeur non reconnu, sans
  son prénom, 3 ans après → **bouton spam**. > 0,3 % de plaintes = domaine plombé. (A5/B2/C1)
- **🥷 POV adversaire — inspecteur DGCCRF/CNIL** : demande (a) preuve d'opt-in nominative,
  (b) opt-out fonctionnel, (c) justification de rétention, (d) claims chiffrés. Le code
  protège (d) ; **(a)(b)(c) sont les angles morts** → ils arment les gates no-go. (B1/B2/B3)
- **POV filtre anti-spam** (Gmail Postmaster) : domaine neuf, 5 000 envois, liste 2023,
  engagement bas → **bulk folder** = campagne invisible. (A1/A4/A5)

## 6. 🚦 Gate Go/No-Go avant le 1ᵉʳ envoi réel

**Bloquants absolus (no-go si un seul manque) :**
- [ ] **B2** — base légale opt-in email vérifiée et archivée. *Seul vrai showstopper.*
- [ ] **B1** — `CALENDLY_URL` + `OPTOUT_URL` réels (`https://`) + opt-out testé cliquable.
- [ ] **A5** — SPF + DKIM + DMARC validés (test mail-tester.com).
- [ ] **A1** — warm-up réellement appliqué (départ à 30/j).

**Fortement recommandés avant la montée en volume :**
- [ ] **B4/C3** — ingestion bounce + STOP câblée avant le batch J+4.
- [ ] **A2/A3** — suppression appliquée sur le chemin d'envoi réellement utilisé.
- [ ] **A4** — coupe-circuit bounce-rate (env `BOUNCE_RATE_LIMIT`, défaut 0,05).
- [ ] test sur **micro-lot (20-30 contacts)** avant les 5 200.

## 7. 🔒 Synthèse verrouillée
- Le build est sain ; le danger est à la **couture code↔ops**.
- Landmines silencieux **corrigés en code** : A1 (warm-up auto), B1 (garde-fou
  placeholders), A3 (suppression à l'export), A4 (coupe-circuit bounce).
- **Seul showstopper non-code : B2** (base légale). Aucune ligne de Python ne couvre ça.
- Ordre : sécuriser B2 (métier) ‖ code A1/B1/A3/A4 → micro-lot → ingestion → volume.

## 8. Prompt maître — « 1ʳᵉ campagne réelle »
```
AVANT-ENVOI (gate, tout vert) :
  Légal  : opt-in email prouvé (B2) · rétention OK (B3)
  Liens  : CALENDLY_URL + OPTOUT_URL en https:// · opt-out testé (B1)
  Domaine: SPF+DKIM+DMARC verts (A5) · warm-up auto à 30/j (A1)
ENVOI : micro-lot 20-30 d'abord · via send_due uniquement (jamais ESP brut) ·
        suppression appliquée (A2/A3) · coupe-circuit bounce (A4)
APRÈS : ingérer bounce+STOP avant J+4 (B4) · funnel jusqu'au RDV (C2)
INTERDITS : 0 auto-envoi · 0 claim non sourcé · opt-out fonctionnel obligatoire
```
