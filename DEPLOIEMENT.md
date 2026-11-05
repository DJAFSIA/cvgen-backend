# Mise en ligne d'Apply

Architecture : **Render** (site statique + API Docker) → **Neon** (PostgreSQL), emails par **Brevo**.
Chaque `git push` sur `main` redéploie automatiquement le site et l'API.

Adresses prévues, fixées dans `render.yaml` :
- site : https://apply.onrender.com
- API : https://apply-server.onrender.com

Comptez environ 30 minutes la première fois. Suivez les étapes dans l'ordre et gardez vos clés
de côté : elles se collent directement chez Render, jamais dans le code.

---

## 1. Base de données : Neon (gratuit)

1. Créez un compte sur https://neon.tech, puis **New Project** :
   nom `apply`, région **AWS Europe Central 1 (Frankfurt)** (la même que l'API), version de
   PostgreSQL proposée par défaut.
2. **Connect** : désactivez **Connection pooling**, puis copiez la chaîne de connexion
   (format `postgresql://...@ep-....neon.tech/neondb?sslmode=require`).
   C'est votre `DATABASE_URL`. Gardez-la secrète.

Les tables sont créées automatiquement au premier démarrage de l'API (migrations Alembic).

## 2. Emails : Brevo (gratuit, 300 emails/jour)

Obligatoire en production : sans emails, personne ne peut confirmer son compte.
L'offre gratuite de Render bloque les ports SMTP : l'API passe donc par l'API HTTPS de Brevo.

1. Créez un compte sur https://www.brevo.com.
2. **Senders, Domains & Dedicated IPs** → **Senders** : ajoutez et validez l'adresse d'expédition.
3. **SMTP & API** → onglet **API Keys** → **Generate a new API key**.
   Cette clé (`xkeysib-...`) est votre `BREVO_API_KEY`.
4. **Settings** → **Security** → **Authorized IPs** : si le blocage des adresses inconnues est actif,
   désactivez-le (Render n'a pas d'adresse IP unique et fixe).

Sans domaine à vous, Brevo remplace une adresse Gmail par une adresse `@brevosend.com` : les emails
partent, mais arrivent plus souvent dans les spams. Un domaine authentifié règle cela (étape 7).

## 3. API et site : Render

1. Créez un compte sur https://render.com avec votre compte GitHub. Quand GitHub demande à quels
   dépôts donner accès, cochez `cvgen-backend` **et** `cvgen-frontend`.
2. **New** → **Blueprint** → choisissez le dépôt `cvgen-backend`.
   Render lit `render.yaml` et prépare deux services : `apply-server` (API) et `apply` (site).
3. Renseignez les 4 valeurs demandées :
   - `DATABASE_URL` : la chaîne Neon (étape 1)
   - `GEMINI_API_KEY` : la clé de `.env`, ou une nouvelle sur https://aistudio.google.com/apikey
   - `MAIL_FROM` : `Apply <adresse-validee@exemple.com>` (l'adresse validée à l'étape 2)
   - `BREVO_API_KEY` : la clé de l'étape 2
4. **Apply**. Le premier déploiement de l'API prend 5 à 10 minutes (construction de l'image Docker).
5. Vérifiez :
   - https://apply-server.onrender.com/health répond `{"status":"ok","db":true}`
   - https://apply.onrender.com affiche le site, avec les tarifs (signe qu'il joint bien l'API)

Si Render affiche une autre adresse pour un service (nom déjà pris), corrigez `FRONTEND_URL`,
`CORS_ORIGINS` et `VITE_API_URL` dans `render.yaml`, puis poussez sur `main`.

Si le déploiement échoue avec « Configuration de production invalide », le journal liste
précisément les réglages à corriger : c'est voulu, l'API refuse de démarrer mal configurée.

### Ce que permet l'offre gratuite
- Le site statique est gratuit et reste toujours disponible.
- L'API s'endort après 15 minutes sans visite et met environ 1 minute à se réveiller.
- Elle dispose de 0,1 CPU et 512 Mo de mémoire. Render déconseille cette offre pour la production :
  pour le lancement public, passez l'API en **Starter** (environ 7 $/mois).

### Réglages optionnels, à ajouter plus tard
Sur le service → **Environment** :
- `apply-server` : `GROQ_API_KEY`, `OPENROUTER_API_KEY` (IA de secours si Gemini sature),
  `GOOGLE_CLIENT_ID`, `SUPPORT_EMAIL`, et les clés de paiement (étape 5)
- `apply` : `VITE_GOOGLE_CLIENT_ID` (connexion Google)

## 4. Vérifications avant d'annoncer le site

- [ ] `/health` répond `ok`
- [ ] Inscription : l'email de confirmation arrive (regardez aussi les spams), le lien fonctionne
- [ ] Mot de passe oublié : l'email arrive, le lien fonctionne une seule fois
- [ ] Import d'un CV PDF, analyse d'une offre, génération, téléchargement des 3 modèles en PDF
- [ ] Quota : la 4e génération d'un compte gratuit affiche « limite du mois »
- [ ] Le site s'affiche correctement sur téléphone

Pas d'email reçu ? Cherchez `Brevo a refuse l'envoi` dans **Logs** de `apply-server` : le message
de Brevo dit quoi corriger (clé invalide, adresse IP non autorisée, expéditeur non validé).

## 5. Activer les paiements (quand vous êtes prêt)

Les moyens de paiement sans clé restent masqués sur le site. Ajoutez les clés dans **Environment**
de `apply-server`.

### Stripe (cartes)
Stripe n'ouvre de compte qu'aux entreprises de certains pays (https://stripe.com/global), dont très
peu en Afrique. Vérifiez que le vôtre y figure avant de commencer.

1. Tableau de bord Stripe → **Developers → API keys** → `STRIPE_SECRET_KEY` (commencez par la clé de test).
2. **Developers → Webhooks → Add endpoint** :
   - URL : `https://apply-server.onrender.com/billing/stripe/webhook`
   - Événements : `checkout.session.completed`, `invoice.paid`, `customer.subscription.updated`,
     `customer.subscription.deleted`, `charge.refunded`, `charge.dispute.created`
   - Copiez le **Signing secret** (`whsec_...`) dans `STRIPE_WEBHOOK_SECRET`.
3. **Settings → Billing → Customer portal** : activez le portail (résiliation, factures, carte).
4. Passage en réel : vérification de l'entreprise par Stripe, puis remplacez les clés de test par les clés live
   (et recréez le webhook en mode live).

### Flutterwave (MTN Mobile Money, Orange Money)
1. **Settings → API keys** → `FLUTTERWAVE_SECRET_KEY`.
2. **Settings → Webhooks** : URL `https://apply-server.onrender.com/billing/momo/webhook`, choisissez un
   **Secret hash** et recopiez-le dans `FLUTTERWAVE_WEBHOOK_HASH`.
3. Vérifiez que le Mobile Money est activé pour XAF/XOF sur votre compte.
4. Passage en réel : validation KYC de l'entreprise par Flutterwave.

## 6. Avant d'ouvrir au public

Ces points ne bloquent pas un test privé, mais **doivent être faits avant d'accueillir de vrais
utilisateurs** (et Stripe les vérifie pour activer les paiements réels) :

- [ ] **Pages légales** : complétez l'identité de l'éditeur dans
      `cvgen-frontend/src/legal/config.js` (raison sociale, adresse, immatriculation, email,
      directeur de la publication, coordonnées des hébergeurs). Tant qu'un champ reste à compléter,
      un bandeau jaune s'affiche en haut des pages légales.
- [ ] **Relecture juridique** : les textes sont des modèles adaptés au fonctionnement réel d'Apply,
      pas un avis juridique. Faites-les relire par un juriste, en particulier pour le droit de la
      consommation des pays visés.
- [ ] **Fournisseurs d'IA** : la politique de confidentialité indique que les CV ne servent pas à
      entraîner les modèles des fournisseurs. C'est faux avec certaines offres gratuites
      (notamment l'offre gratuite de Gemini). Passez sur des offres payantes, ou retirez ces
      fournisseurs de `LLM_PROVIDERS`, avant l'ouverture.
- [ ] **`SUPPORT_EMAIL`** (Render) : adresse qui reçoit les réponses aux emails et les demandes
      liées aux données personnelles. Mettez la même dans `src/legal/config.js`.
- [ ] **API toujours éveillée** : passez `apply-server` en Starter.
- [ ] **Remboursements Mobile Money** : ils se font à la main depuis Flutterwave. Après un
      remboursement, retirez aussi le plan Pro du compte (les remboursements par carte, eux,
      retirent le Pro automatiquement).

## 7. Nom de domaine (plus tard)

1. Achetez le domaine (ex. chez Hostinger, OVH, Namecheap…).
2. Render → `apply` → **Settings → Custom Domains** : ajoutez `votre-domaine.com` (suivez les DNS indiqués).
3. Render → `apply-server` → **Settings → Custom Domains** : ajoutez `api.votre-domaine.com`.
4. Dans `render.yaml`, mettez à jour `FRONTEND_URL`, `CORS_ORIGINS` et `VITE_API_URL`, puis poussez sur `main`.
5. Modifiez les URL des webhooks Stripe / Flutterwave.
6. Brevo → **Senders, Domains & Dedicated IPs** → **Domains** : authentifiez le domaine, puis mettez
   une adresse de ce domaine dans `MAIL_FROM` (les emails arriveront bien mieux en boîte de réception).

---

### Droits des utilisateurs (RGPD)
Chaque utilisateur peut, depuis la page **Compte** : corriger son nom et la langue de ses emails,
**télécharger toutes ses données** (fichier JSON) et **supprimer définitivement son compte**
(abonnement par carte arrêté, données effacées, paiements conservés sans lien avec la personne
pour la comptabilité).

### Limites connues de cette première version
- Les limites de débit (anti-abus) sont en mémoire : gardez **1 seule instance** de l'API
  (`WEB_CONCURRENCY=1`, réglage par défaut). Au-delà, il faudra un Redis partagé.
- Pas encore de sauvegarde exportée hors de Neon (Neon conserve un historique de restauration
  limité sur l'offre gratuite).
