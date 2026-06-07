# Phronesis — Backend

API REST du projet Phronesis, une plateforme de financement automobile destinée au marché ouest-africain.

## Ce que fait le projet

Phronesis couvre l'ensemble du cycle de vie d'un crédit auto :

- **Demandes de financement** — soumission d'une demande avec prix du véhicule, apport, durée et montant du prêt
- **Scoring IA** — évaluation automatique du dossier (emploi, ratio d'endettement, Mobile Money, historique BCEAO) avec valeurs SHAP explicatives
- **KYC et documents** — upload de pièces justificatives avec OCR automatique (stockage S3)
- **Comité de crédit** — validation ou rejet par un analyste avec commentaire horodaté
- **Contrats** — génération du contrat PDF, plan de remboursement mensuel, mode de paiement
- **Paiements** — suivi des échéances avec intégration Mobile Money (MoMo)
- **Recouvrement** — actions automatisées sur les paiements en retard (SMS, appel, mise en demeure)
- **Suivi GPS** — positions en temps réel des véhicules financés, commandes de coupure à distance
- **Audit** — log complet de toutes les actions utilisateurs et système

## Stack technique

| Composant | Technologie |
|---|---|
| API | FastAPI + Python 3.10+ |
| Base de données | PostgreSQL 18 |
| ORM / Migrations | SQLModel + Alembic |
| Auth | JWT (OAuth2) + Argon2 |
| Emails | Jinja2 + SMTP |
| Monitoring | Sentry |
| Proxy | Traefik |
| Conteneurs | Docker Compose |

## Lancer le projet en local

### Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et démarré
- [Git](https://git-scm.com/)

### Étapes

**1. Cloner le dépôt**

```bash
git clone <url-du-repo>
cd BackPcP
```

**2. Configurer l'environnement**

Le fichier `.env` est déjà présent avec des valeurs par défaut pour le développement local. Modifier au minimum :

```dotenv
SECRET_KEY=           # générer avec : python -c "import secrets; print(secrets.token_urlsafe(32))"
POSTGRES_PASSWORD=    # mot de passe de la base de données
FIRST_SUPERUSER=      # email du compte admin
FIRST_SUPERUSER_PASSWORD=  # mot de passe du compte admin
```

**3. Démarrer le stack**

```bash
docker compose watch
```

Cette commande démarre la base de données, applique les migrations, crée le superuser initial et lance l'API avec hot-reload.

**4. Accéder aux services**

| Service | URL |
|---|---|
| API (Swagger UI) | http://localhost:8000/docs |
| API (ReDoc) | http://localhost:8000/redoc |
| Adminer (base de données) | http://localhost:8080 |
| Mailcatcher (emails) | http://localhost:1080 |

### Connexion à la base de données

Avec pgAdmin ou tout autre client PostgreSQL :

| Champ | Valeur |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `app` |
| Username | valeur de `POSTGRES_USER` dans `.env` |
| Password | valeur de `POSTGRES_PASSWORD` dans `.env` |
