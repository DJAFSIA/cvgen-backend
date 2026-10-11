#!/bin/sh
# Demarrage en production : migrations de la base, puis serveur.
set -e

alembic upgrade head

# --proxy-headers : l'adresse IP reelle du client (limites de debit) vient de l'hebergeur.
# WEB_CONCURRENCY=1 par defaut : les limites de debit sont en memoire, propres a chaque processus.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips "*" \
    --workers "${WEB_CONCURRENCY:-1}"
