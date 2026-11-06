# Apply : API (backend)

Apply rédige un CV et une lettre de motivation adaptés à chaque offre d'emploi.
Ce dépôt contient l'API (FastAPI, PostgreSQL). Le site est dans `cvgen-frontend`.

Documents de référence :
- [Cahier des charges complet](docs/Apply-cahier-des-charges.pdf) : réalisations, accès, installation, interfaces
- [GUIDE.md](GUIDE.md) : utiliser Apply, en local et en ligne
- [DEPLOIEMENT.md](DEPLOIEMENT.md) : mettre le site en ligne (Neon, Brevo, Render)

## Prérequis

- Python 3.12 ou plus récent
- PostgreSQL 16 ou plus récent, démarré
- Une clé d'IA : [Gemini](https://aistudio.google.com/apikey) suffit pour commencer

## Installation

Créez la base de données :

```sql
CREATE DATABASE cvgen_db;
```

Préparez l'environnement Python :

```bash
python -m venv venv
```

```bash
venv/Scripts/python -m pip install -r requirements-dev.txt
```

Copiez `.env.example` en `.env`, puis renseignez au minimum `DATABASE_URL`, `SECRET_KEY`,
`GEMINI_API_KEY`, `FRONTEND_URL` et `CORS_ORIGINS`. Ce fichier ne part jamais sur GitHub.

Créez les tables :

```bash
venv/Scripts/alembic upgrade head
```

## Lancer l'API

```bash
venv/Scripts/python -m uvicorn app.main:app --reload --port 8001
```

- État de l'API : http://localhost:8001/health
- Documentation interactive, en local uniquement : http://localhost:8001/docs
- En local, les emails s'affichent dans le terminal au lieu de partir.

## Tests

```bash
venv/Scripts/python -m pytest -q
```

## Organisation

```
app/
  routers/     adresses de l'API
  services/    IA, PDF, emails, paiements, export et suppression de compte
  models/      tables de la base
  schemas/     formats des échanges
  templates/   modèles HTML des CV et de la lettre
  core/        configuration, base, sécurité, limites anti-abus
alembic/       évolutions de la base
tests/         tests automatiques
render.yaml    déploiement du site et de l'API sur Render
```
