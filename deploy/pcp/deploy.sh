#!/usr/bin/env bash
# Déploie une version de PCP sur le serveur. Appelé par GitHub Actions via SSH :
#
#   printf '%s' "$GITHUB_TOKEN" | ssh root@serveur "backend v1.2.0"
#
# La clé SSH de GitHub est restreinte à ce script dans /root/.ssh/authorized_keys
# (command="/opt/pcp/deploy.sh",restrict) : la commande demandée arrive dans
# SSH_ORIGINAL_COMMAND et le jeton ghcr.io (valable le temps du job) sur stdin.
#
# À la main sur le serveur : echo "$TOKEN" | /opt/pcp/deploy.sh frontend v1.2.0
set -euo pipefail
cd "$(dirname "$0")"

read -r component tag extra <<<"${SSH_ORIGINAL_COMMAND:-$*}" || true
if [[ -n ${extra:-} || ! ${tag:-} =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
  echo "Usage : deploy.sh <backend|frontend> <vX.Y.Z>" >&2
  exit 2
fi
case $component in
  backend)  var=BACKEND_TAG;  services=(prestart backend) ;;
  frontend) var=FRONTEND_TAG; services=(frontend) ;;
  *) echo "Composant inconnu : $component" >&2; exit 2 ;;
esac

touch versions.env
compose() { docker compose --env-file .env --env-file versions.env "$@"; }

token=$(cat)
printf '%s' "$token" | docker login ghcr.io -u github-actions --password-stdin >/dev/null
trap 'docker logout ghcr.io >/dev/null 2>&1 || true' EXIT

# La variable d'environnement est prioritaire sur versions.env
export "$var=$tag"
echo "==> $component $tag : téléchargement de l'image"
compose pull "${services[@]}"

echo "==> $component $tag : démarrage"
compose up -d --no-deps db
compose up -d "${services[@]}"

if [[ $component == backend ]]; then
  echo "==> Attente du healthcheck du backend"
  for _ in $(seq 1 30); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$(compose ps -q backend)")
    [[ $status == healthy ]] && break
    sleep 5
  done
  if [[ $status != healthy ]]; then
    echo "Le backend n'est pas healthy ($status). Logs :" >&2
    compose logs --tail 50 prestart backend >&2
    exit 1
  fi
fi

# On ne mémorise la version qu'une fois le démarrage réussi
grep -v "^$var=" versions.env > versions.env.tmp || true
echo "$var=$tag" >> versions.env.tmp
mv versions.env.tmp versions.env

docker image prune -f >/dev/null
echo "==> $component $tag déployé"
