# Guide d'utilisation d'Apply

Apply prépare un CV et une lettre de motivation adaptés à chaque offre d'emploi.
Ce guide explique comment utiliser le service, puis comment le faire tourner en local et en ligne.

## 1. Utiliser Apply (identique en local et en ligne)

1. **Créer un compte** : remplissez le formulaire et cochez la case des conditions.
2. **Confirmer l'email** : ouvrez le lien reçu. Sans cela, l'import de CV et la génération restent bloqués.
3. **Mon profil** : importez votre CV (PDF de moins de 5 Mo, avec du texte sélectionnable, pas un scan),
   puis corrigez les informations si besoin.
4. **Nouvelle candidature** : collez le texte de l'offre ou son lien. Apply évalue la compatibilité et
   pose quelques questions : vos réponses rendent la lettre plus personnelle.
5. **Générer** : choisissez le modèle de CV (classique, moderne ou ATS) et la langue des documents.
6. **Télécharger** le CV et la lettre en PDF. Relisez-les avant de les envoyer.
7. **Historique** : retrouvez vos candidatures et vos documents.
8. **Abonnement** : suivez votre consommation du mois et passez au plan Pro.
9. **Mon compte** : corrigez vos informations, téléchargez vos données ou supprimez votre compte.

| Par mois | Gratuit | Pro |
|---|---|---|
| Candidatures générées | 3 | 50 |
| Offres analysées | 10 | 150 |
| CV importés | 3 | 20 |

Les compteurs repartent à zéro le 1er de chaque mois. Le plan Pro coûte 7,99 € par mois par carte, ou
3 000 FCFA pour 30 jours par Mobile Money. Sans clés de paiement, ces moyens restent indisponibles.

## 2. En local (sur votre ordinateur)

PostgreSQL doit être démarré. Ouvrez deux terminaux et laissez-les tourner.

Terminal 1, l'API :

```bash
cd C:/Users/USER/cvgen-backend; venv/Scripts/python -m uvicorn app.main:app --reload --port 8001
```

Terminal 2, le site :

```bash
cd C:/Users/USER/cvgen-frontend; npm run dev -- --port 5174
```

- **Site :** http://localhost:5174
- **Santé de l'API :** http://localhost:8001/health doit afficher `"status":"ok"` et `"db":true`
- **Arrêter :** Ctrl+C dans chaque terminal
- **Emails :** rien ne part vraiment. Le message et son lien s'affichent dans le terminal 1, entre des
  lignes `=== EMAIL`.
- **Tests automatiques :** `venv/Scripts/python -m pytest -q` dans le dossier du backend
- **Après une mise à jour de la base :** `venv/Scripts/alembic upgrade head` dans le dossier du backend
- **Réglages :** fichier `.env` de chaque dossier. Il ne part jamais sur GitHub.

Si les ports 5173 et 8000 sont occupés, c'est sans doute par un autre projet (VIFIC) : gardez 5174 et 8001.

### Problèmes fréquents en local

| Ce que vous voyez | Que faire |
|---|---|
| « Impossible de joindre le serveur » | Le terminal 1 est arrêté : relancez l'API |
| `/health` affiche `"db":false` | Démarrez PostgreSQL |
| Module introuvable côté site | Lancez `npm install` dans le dossier du site |
| « Le service d'IA est momentanément indisponible » | Quota ou surcharge de Gemini : réessayez plus tard |
| Import ou génération refusés | Confirmez d'abord l'email avec le lien du terminal 1 |

## 3. En ligne

La mise en ligne se fait une seule fois, en suivant [DEPLOIEMENT.md](DEPLOIEMENT.md) : Neon pour la base,
Brevo pour les emails, Render pour le site et l'API.

- **Site :** https://apply.onrender.com
- **Santé de l'API :** https://apply-server.onrender.com/health

Ces adresses sont celles prévues dans `render.yaml`. Render les confirme au déploiement.

### Ce qui change par rapport au local

| | En local | En ligne |
|---|---|---|
| Emails | Dans le terminal 1 | Vrais emails par Brevo (300 par jour) |
| Base de données | PostgreSQL sur votre PC | Neon |
| Réglages et clés | Fichiers `.env` | Render, onglet **Environment** de chaque service |
| Journaux | Terminal 1 | Render, onglet **Logs** de `apply-server` |
| Mise à jour | Immédiate après enregistrement | Automatique après un `git push` sur `main` |
| Disponibilité | Tant que les terminaux tournent | Permanente, mais voir ci-dessous |

Sur l'offre gratuite, l'API s'endort après 15 minutes sans visite et met environ 1 minute à se réveiller.
Pour le lancement public, passez-la en Starter (environ 7 $ par mois).

### Au quotidien

- **Publier une modification :** un `git push` sur `main` redéploie le service concerné (5 à 10 minutes
  pour l'API, moins pour le site).
- **Ajouter ou changer une clé :** Render → le service → **Environment**. Render redéploie ensuite.
- **Suivre les emails envoyés :** tableau de bord Brevo, journaux des emails transactionnels.
- **Ne changez pas `SECRET_KEY` sans raison :** cela déconnecte tous les utilisateurs.

### Problèmes fréquents en ligne

| Ce que vous voyez | Que faire |
|---|---|
| Site lent ou tarifs absents au premier chargement | L'API se réveille : attendez environ 1 minute |
| Tarifs toujours absents | Comparez les adresses réelles avec `FRONTEND_URL`, `CORS_ORIGINS` et `VITE_API_URL` dans `render.yaml` |
| Déploiement échoué, « Configuration de production invalide » | Le journal liste les réglages à corriger |
| Email non reçu | Regardez les spams, puis cherchez `Brevo a refuse l'envoi` dans **Logs** |
| `/health` affiche `"db":false` | Vérifiez `DATABASE_URL` dans **Environment** |

Avant d'annoncer le site au public, faites la liste de la section « Avant d'ouvrir au public » de
[DEPLOIEMENT.md](DEPLOIEMENT.md).
