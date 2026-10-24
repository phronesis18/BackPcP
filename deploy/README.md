# Déploiement en production

Serveur : Hetzner `178.104.209.151` · Domaine : `phronesiscapital-partners.com`

```
Internet ──► Traefik (80/443, HTTPS Let's Encrypt)
               ├─ phronesiscapital-partners.com, www.  ──► pcp-frontend (FrontPcp)
               ├─ api.phronesiscapital-partners.com    ──► pcp-backend  (BackPcP) ──► pcp-db
               └─ tout le reste en HTTP (accès par IP) ──► atlas-frontend
```

## Mettre une version en production

1. Créer et pousser un tag :
   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```
   Le workflow **Release** construit l'image Docker et la publie sur ghcr.io (2 à 5 min).
2. Sur GitHub : **Actions → Deploy → Run workflow**, saisir `v1.2.0`, valider.

Le frontend et le backend se déploient séparément, chacun depuis son dépôt.

**Revenir en arrière** : relancer **Deploy** avec le tag précédent. Attention, les migrations
de base de données ne sont pas annulées.

## Sur le serveur

| Chemin | Contenu |
|---|---|
| `/opt/traefik/compose.yml` | Reverse proxy partagé (copie de `deploy/traefik/compose.yml`) |
| `/opt/traefik/.env` | `ACME_EMAIL=...` |
| `/opt/pcp/compose.yml` | Stack PCP (copie de `deploy/pcp/compose.yml`) |
| `/opt/pcp/deploy.sh` | Script lancé par GitHub Actions (copie de `deploy/pcp/deploy.sh`) |
| `/opt/pcp/.env` | Secrets de production (modèle : `deploy/pcp/.env.example`) |
| `/opt/pcp/versions.env` | Versions déployées, mis à jour par `deploy.sh` |

Commandes utiles :
```bash
cd /opt/pcp
cat versions.env                                                   # versions en ligne
docker compose --env-file .env --env-file versions.env ps          # état
docker compose --env-file .env --env-file versions.env logs -f backend
```

Une modification de `deploy/pcp/compose.yml` ou de `deploy.sh` n'est **pas** déployée
automatiquement : il faut recopier le fichier sur le serveur.

## Configuration GitHub (dans chacun des deux dépôts)

**Settings → Secrets and variables → Actions** :

| Type | Nom | Valeur |
|---|---|---|
| Variable | `DEPLOY_HOST` | `178.104.209.151` |
| Secret | `DEPLOY_SSH_KEY` | Clé privée `pcp_deploy` |
| Secret | `DEPLOY_KNOWN_HOSTS` | Sortie de `ssh-keyscan 178.104.209.151` |

La clé `pcp_deploy` est déclarée dans `/root/.ssh/authorized_keys` du serveur avec
`command="/opt/pcp/deploy.sh",restrict` : elle ne peut rien faire d'autre que lancer un déploiement.
