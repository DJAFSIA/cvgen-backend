# Mise en ligne de CVGen

Architecture : **Vercel** (site) → **Render** (API Docker) → **Neon** (PostgreSQL).
Chaque `git push` sur `main` redéploie automatiquement le site et l'API.

Comptez environ 45 minutes la première fois. Suivez les étapes dans l'ordre : chaque service a
besoin d'une adresse fournie par le précédent.

---

## 1. Base de données : Neon (gratuit)

1. Créez un compte sur https://neon.tech, puis **New Project** :
   nom `cvgen`, PostgreSQL 16, région **AWS Europe Central (Frankfurt)** (la même que l'API).
2. Dans **Connection Details**, copiez la chaîne de connexion (format
   `postgresql://...@ep-....neon.tech/neondb?sslmode=require`).
   C'est votre `DATABASE_URL`. Gardez-la secrète.

Les tables sont créées automatiquement au premier démarrage de l'API (migrations Alembic).

## 2. Emails : Brevo (gratuit, 300 emails/jour)

Obligatoire en production : sans emails, personne ne peut confirmer son compte.

1. Créez un compte sur https://www.brevo.com.
2. **Senders, Domains & Dedicated IPs** → ajoutez et validez l'adresse d'expédition
   (ex. votre adresse Gmail au début, une adresse `@votre-domaine` plus tard).
3. **SMTP & API** → onglet SMTP → **Generate a new SMTP key**. Notez :
   - `SMTP_HOST` = `smtp-relay.brevo.com`
   - `SMTP_PORT` = `587`
   - `SMTP_USER` = l'identifiant affiché (souvent `xxxx@smtp-brevo.com`)
   - `SMTP_PASSWORD` = la clé SMTP générée
   - `MAIL_FROM` = `CVGen <adresse-validee@exemple.com>`

## 3. API : Render

1. Créez un compte sur https://render.com avec votre compte GitHub.
2. **New** → **Blueprint** → choisissez le dépôt `cvgen-backend`.
   Render lit `render.yaml` et prépare le service `cvgen-api`.
3. Renseignez les valeurs demandées :
   - `DATABASE_URL` : la chaîne Neon (étape 1)
   - `FRONTEND_URL` et `CORS_ORIGINS` : mettez provisoirement `https://cvgen.vercel.app`
     (vous corrigerez à l'étape 5 avec l'adresse réelle)
   - `GEMINI_API_KEY` (et/ou `GROQ_API_KEY`, `OPENROUTER_API_KEY`)
   - `MAIL_FROM`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` (étape 2)
   - Paiements : laissez vides pour l'instant (les moyens de paiement seront simplement masqués)
4. **Apply**. Le premier déploiement prend 5 à 10 minutes (construction de l'image Docker).
5. Vérifiez : `https://cvgen-api.onrender.com/health` doit répondre `{"status":"ok","db":true}`.
   (L'adresse exacte est affichée en haut de la page du service.)

Si le déploiement échoue avec « Configuration de production invalide », le journal liste
précisément les réglages à corriger : c'est voulu, l'API refuse de démarrer mal configurée.

Offre gratuite : l'API s'endort après 15 minutes sans visite et met ~1 minute à se réveiller.
Pour le lancement public, passez le service en **Starter** (~7 $/mois).

## 4. Site : Vercel

1. Sur https://vercel.com → **Add New** → **Project** → importez le dépôt `cvgen-frontend`.
2. Framework détecté : **Vite** (rien à changer).
3. **Environment Variables** :
   - `VITE_API_URL` = l'adresse Render de l'étape 3 (ex. `https://cvgen-api.onrender.com`, sans `/` final)
   - `VITE_GOOGLE_CLIENT_ID` = optionnel (connexion Google)
4. **Deploy**. Notez l'adresse obtenue (ex. `https://cvgen-xxxx.vercel.app`).

## 5. Relier le site et l'API

Sur Render → service `cvgen-api` → **Environment** :
- `FRONTEND_URL` = l'adresse Vercel exacte (liens des emails, retours de paiement)
- `CORS_ORIGINS` = la même adresse (autorise le site à appeler l'API)

Enregistrez : Render redéploie l'API.

## 6. Vérifications avant d'annoncer le site

- [ ] `/health` répond `ok`
- [ ] Inscription : l'email de confirmation arrive (regardez aussi les spams), le lien fonctionne
- [ ] Mot de passe oublié : l'email arrive, le lien fonctionne une seule fois
- [ ] Import d'un CV PDF, analyse d'une offre, génération, téléchargement des 3 modèles en PDF
- [ ] Quota : la 4e génération d'un compte gratuit affiche « limite du mois »
- [ ] Le site s'affiche correctement sur téléphone

## 7. Activer les paiements (quand vous êtes prêt)

### Stripe (cartes)
1. Tableau de bord Stripe → **Developers → API keys** → `STRIPE_SECRET_KEY` (commencez par la clé de test).
2. **Developers → Webhooks → Add endpoint** :
   - URL : `https://<votre-api>/billing/stripe/webhook`
   - Événements : `checkout.session.completed`, `invoice.paid`, `customer.subscription.updated`,
     `customer.subscription.deleted`, `charge.refunded`, `charge.dispute.created`
   - Copiez le **Signing secret** (`whsec_...`) dans `STRIPE_WEBHOOK_SECRET`.
3. **Settings → Billing → Customer portal** : activez le portail (résiliation, factures, carte).
4. Passage en réel : vérification de l'entreprise par Stripe, puis remplacez les clés de test par les clés live
   (et recréez le webhook en mode live).

### Flutterwave (MTN Mobile Money, Orange Money)
1. **Settings → API keys** → `FLUTTERWAVE_SECRET_KEY`.
2. **Settings → Webhooks** : URL `https://<votre-api>/billing/momo/webhook`, choisissez un
   **Secret hash** et recopiez-le dans `FLUTTERWAVE_WEBHOOK_HASH`.
3. Vérifiez que le Mobile Money est activé pour XAF/XOF sur votre compte.
4. Passage en réel : validation KYC de l'entreprise par Flutterwave.

## 8. Nom de domaine (plus tard)

1. Achetez le domaine (ex. chez Hostinger, OVH, Namecheap…).
2. Vercel → projet → **Settings → Domains** : ajoutez `votre-domaine.com` (suivez les DNS indiqués).
3. Render → service → **Settings → Custom Domains** : ajoutez `api.votre-domaine.com`.
4. Mettez à jour `FRONTEND_URL`, `CORS_ORIGINS` (Render), `VITE_API_URL` (Vercel, puis redéployez),
   et les URL des webhooks Stripe / Flutterwave.

---

### Limites connues de cette première version
- Les limites de débit (anti-abus) sont en mémoire : gardez **1 seule instance** de l'API
  (`WEB_CONCURRENCY=1`, réglage par défaut). Au-delà, il faudra un Redis partagé.
- Pas encore de sauvegarde exportée hors de Neon (Neon conserve un historique de restauration
  limité sur l'offre gratuite).
