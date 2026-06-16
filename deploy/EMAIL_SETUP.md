# deploy/EMAIL_SETUP.md — brancher l'envoi réel (GRATUIT, via Infomaniak)

Tu as un domaine + une boîte mail chez **Infomaniak** → tu as **déjà** un serveur SMTP.
On envoie directement via `contact@renoadomicile.fr` : **pas d'ESP, pas de coût en plus**,
et Infomaniak gère **SPF/DKIM/DMARC** pour toi. Valeurs ci-dessous **littérales**
(domaine `renoadomicile.fr`). À faire une fois **B2 (opt-in archivé)** validé.

> Pas besoin de Brevo. Un ESP (Brevo payant, Scaleway TEM…) ne devient utile que si un
> jour tu dépasses les limites d'envoi d'une boîte mail (cf. §5) — il suffira alors de
> changer les `SMTP_*`, le reste de l'outil ne bouge pas.

---

## 1. Vérifier que la boîte fonctionne
Depuis ton mail perso, envoie un message à `contact@renoadomicile.fr` et vérifie sa
réception dans le **webmail Infomaniak**. Réponds-toi pour tester l'envoi.
**Passage :** tu reçois et tu envoies depuis `contact@renoadomicile.fr`.

## 2. Activer la signature & vérifier la délivrabilité (SPF/DKIM/DMARC)
Infomaniak les pose automatiquement quand le **DNS du domaine est géré chez eux** :
- **Manager Infomaniak → Mail → (ton domaine) → Signature DKIM** : vérifie qu'elle est **activée**.
- **Domaine → Zone DNS** : confirme la présence de **SPF**, **DKIM**, **DMARC**
  (Infomaniak propose un bouton « configuration automatique » si un enregistrement manque).
- Test final : envoie un mail à l'adresse fournie par **https://www.mail-tester.com**.

**Passage A5 :** mail-tester **≥ 9/10**, SPF/DKIM/DMARC = `pass`.

## 3. Récupérer les réglages SMTP/IMAP Infomaniak
- **SMTP** : `mail.infomaniak.com`, port **587** (STARTTLS) — login = l'adresse complète,
  mot de passe = celui de la boîte.
- **IMAP** : `mail.infomaniak.com`, port **993** — mêmes identifiants.

## 4. Remplir `.env` (copie de `.env.example`)
```dotenv
# Envoi (boîte Infomaniak du domaine)
SMTP_HOST=mail.infomaniak.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_USER=contact@renoadomicile.fr
SMTP_PASSWORD=<mot-de-passe-boîte>
SENDER_EMAIL=contact@renoadomicile.fr
SENDER_NAME=Réno à domicile
UNSUBSCRIBE_MAILTO=unsubscribe@renoadomicile.fr

# Réception des retours (la MÊME boîte Infomaniak)
IMAP_HOST=mail.infomaniak.com
IMAP_PORT=993
IMAP_USER=contact@renoadomicile.fr
IMAP_PASSWORD=<mot-de-passe-boîte>

# Liens
CALENDLY_URL=https://calendly.com/paul-gerard-renoboostia/rdv-expert-cvc-30-min
CALENDLY_TOKEN=<personal-access-token-calendly>   # Calendly → Integrations → API & webhooks
OPTOUT_URL=https://renoadomicile.fr/desinscription # page https réelle, testée cliquable (voir note)

# Réassurance (affichée dans les mails)
REASSURANCE_RGE=<n° ou mention RGE>
REASSURANCE_DECENNALE=<assureur / n° décennale>
REASSURANCE_NB_CHANTIERS=<ex. 1 200>
```

> **OPTOUT_URL** : il faut une **page https réelle** de désinscription. Si tu n'as pas
> encore de site, options rapides : page « Site Creator » Infomaniak, une page publique
> (Notion/Carrd), ou GitHub Pages. À défaut, le header `List-Unsubscribe` (mailto
> `unsubscribe@renoadomicile.fr`) reste posé par l'outil, mais une URL cliquable dans le
> corps est fortement recommandée (conformité + délivrabilité).

## 5. ⚠️ Limites d'envoi d'une boîte mail
Une boîte Infomaniak a un **plafond d'envoi anti-spam** (quelques centaines/jour). C'est
**compatible avec le warm-up** (30 → 50 → 100/j). Surveille `out/daily.log`. Si tu vises
durablement de gros volumes, bascule vers un ESP (changer seulement les `SMTP_*`).

## 6. Gate puis micro-lot
```bash
python -m src.preflight --db out/state.sqlite check     # exit 0 = GO
python -m src.daily --db out/state.sqlite run --confirm --smtp --limit 25   # 1er micro-lot
```
Puis suivre **LAUNCH.md §3→4** (observer 48-72 h, puis montée en volume / cron).

## 🔒 Sécurité
- `SMTP_PASSWORD` / `IMAP_PASSWORD` / `CALENDLY_TOKEN` = secrets → uniquement dans `.env`
  (jamais committé ; couvert par `.gitignore`).
- `SENDER_EMAIL` doit être l'adresse du domaine signé DKIM, sinon spam.
