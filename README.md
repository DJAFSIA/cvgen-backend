# CVGen Backend — Guide de démarrage

## Prérequis
- Python 3.10+
- PostgreSQL installé et démarré
- Un compte Anthropic (pour la clé API Claude)

---

## Installation

### 1. Créer et activer un environnement virtuel
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / Mac
source venv/bin/activate
```

### 2. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 3. Configurer les variables d'environnement
```bash
cp .env.example .env
```
Ouvrir `.env` et remplir les valeurs :
- `DATABASE_URL` : votre URL PostgreSQL
- `SECRET_KEY` : générer avec `openssl rand -hex 32`
- `ANTHROPIC_API_KEY` : votre clé sur https://console.anthropic.com

### 4. Créer la base de données PostgreSQL
```bash
psql -U postgres
CREATE DATABASE cvgen_db;
\q
```

### 5. Appliquer les migrations
```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

### 6. Lancer le serveur
```bash
uvicorn app.main:app --reload
```

---

## Documentation API

Une fois le serveur lancé, ouvrir dans le navigateur :

- **Swagger UI** : http://localhost:8000/docs
- **ReDoc** : http://localhost:8000/redoc

---

## Structure du projet

```
cvgen-backend/
├── app/
│   ├── main.py              # Point d'entrée FastAPI
│   ├── core/
│   │   ├── config.py        # Variables d'environnement
│   │   ├── database.py      # Connexion SQLAlchemy
│   │   └── security.py      # JWT et hachage
│   ├── models/              # Tables SQLAlchemy
│   ├── schemas/             # Validation Pydantic
│   ├── routers/             # Endpoints API
│   └── services/            # Logique métier (IA, PDF)
├── alembic/                 # Migrations base de données
├── .env.example             # Modèle de configuration
├── requirements.txt
└── README.md
```

---

## Endpoints principaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | /auth/inscription | Créer un compte |
| POST | /auth/login | Se connecter |
| GET | /profil/ | Récupérer son profil |
| PUT | /profil/ | Mettre à jour son profil |
| POST | /offre/ | Soumettre une offre (analyse IA) |
| GET | /offre/ | Lister ses offres |
| POST | /candidature/ | Créer une candidature |
| POST | /candidature/{id}/generer | Générer CV + lettre |
| GET | /candidature/{id}/export-pdf | Exporter en PDF |
