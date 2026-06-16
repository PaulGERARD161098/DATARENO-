# deploy/BREVO_SETUP.md — brancher l'envoi réel via Brevo (EU)

Runbook concret de l'étape **A5 (DNS) + `.env`** du lancement, pour l'ESP **Brevo**.
Remplace partout `<DOMAINE>` par ton **domaine d'envoi dédié** (jamais ton domaine
principal). À faire une fois **B2 (opt-in archivé)** validé.

> Ordre : 1) authentifier le domaine → 2) poser les DNS → 3) clé SMTP → 4) boîte de
> réception (réponses) → 5) `.env` → 6) gate preflight → 7) micro-lot (LAUNCH.md §3).

---

## 1. Authentifier le domaine dans Brevo
Brevo → **Senders, Domains & Dedicated IPs → Domains → Add a domain** → saisir `<DOMAINE>`.
Brevo affiche alors **les enregistrements exacts à copier** (DKIM + code de vérification).

## 2. Poser les DNS (chez ton registrar)
| Type  | Hôte                         | Valeur                                                        |
|-------|------------------------------|--------------------------------------------------------------|
| TXT   | `@`                          | `v=spf1 include:spf.brevo.com ~all`                          |
| TXT/CNAME | `brevo._domainkey` *(exact donné par Brevo)* | la valeur **DKIM** affichée par Brevo (copier verbatim) |
| TXT   | *(code de vérif Brevo)*      | `brevo-code:...` (copier verbatim depuis Brevo)             |
| TXT   | `_dmarc`                     | `v=DMARC1; p=none; rua=mailto:dmarc@<DOMAINE>` *(voir note)* |

> **DMARC** : démarre en `p=none` (observation, ne casse rien). Une fois SPF+DKIM en
> `pass` confirmés (mail-tester), passe à `p=quarantine`. Ne mets `adkim=s; aspf=s`
> (strict) qu'après vérif d'alignement.

**Critère de passage A5 :** dans Brevo le domaine est **Authenticated** ; un envoi test
sur **https://www.mail-tester.com** donne **≥ 9/10**, SPF/DKIM/DMARC = `pass`.

## 3. Récupérer la clé SMTP
Brevo → **SMTP & API → SMTP**. Tu obtiens :
- serveur `smtp-relay.brevo.com`, port `587` (STARTTLS),
- **login** = ton email de compte Brevo,
- **mot de passe** = la **clé SMTP (Master password)** affichée ici (≠ ton mot de passe Brevo).

## 4. Boîte de réception des réponses (IMAP)
Brevo **envoie** mais ne fournit pas de boîte. Les **réponses + bounces** reviennent sur
la mailbox de `SENDER_EMAIL`. Il te faut donc une **vraie boîte mail sur `<DOMAINE>`**
(chez ton registrar, Gandi, OVH, Google Workspace…) avec accès **IMAP** → c'est elle que
`src.inbox` relèvera. Note ses `IMAP_HOST` / `IMAP_PORT` (993) / login / mot de passe.

## 5. Remplir `.env` (copie de `.env.example`)
```dotenv
# Envoi (Brevo)
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_USER=<ton-email-compte-brevo>
SMTP_PASSWORD=<clé-SMTP-brevo>
SENDER_EMAIL=contact@<DOMAINE>          # doit appartenir au domaine authentifié
SENDER_NAME=<Prénom Nom ou Marque>
UNSUBSCRIBE_MAILTO=unsubscribe@<DOMAINE>

# Réception des retours (ta boîte sur le domaine)
IMAP_HOST=<imap.ton-hébergeur>
IMAP_PORT=993
IMAP_USER=contact@<DOMAINE>
IMAP_PASSWORD=<mot-de-passe-boîte>

# Liens
CALENDLY_URL=https://calendly.com/<toi>/<event>
CALENDLY_TOKEN=<personal-access-token-calendly>   # Calendly → Integrations → API & webhooks
OPTOUT_URL=https://<DOMAINE>/desinscription        # page https réelle, testée cliquable

# Réassurance (affichée dans les mails)
REASSURANCE_RGE=<n° ou mention RGE>
REASSURANCE_DECENNALE=<assureur / n° décennale>
REASSURANCE_NB_CHANTIERS=<ex. 1 200>
```

## 6. Gate Go/No-Go
```bash
python -m src.preflight --db out/state.sqlite check     # exit 0 = GO
```

## 7. Micro-lot test (puis montée en volume)
Suivre **LAUNCH.md §3→4** : `python -m src.daily --db out/state.sqlite run --confirm --smtp --limit 25`,
observer 48-72 h (inbox vs spam, bounces, opt-out cliquable, 1 RDV test capté), puis cron.

> ⚠️ **Plafond Brevo** : le plan gratuit limite l'envoi quotidien (≈ 300/j) — suffisant
> pour le warm-up (30→50→100/j). Vérifie ton plan avant de viser 100/j en continu.

## 🔒 Sécurité
- `SMTP_PASSWORD` / `IMAP_PASSWORD` / `CALENDLY_TOKEN` = secrets → uniquement dans `.env`
  (jamais committé ; `.gitignore` le couvre). En PaaS : variables Render (`sync:false`).
- `SENDER_EMAIL` doit être sur le domaine authentifié, sinon DKIM/DMARC échouent (spam).
