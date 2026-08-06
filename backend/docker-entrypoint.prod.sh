#!/bin/sh
# Entrypoint de PRODUCAO. Diferencas deliberadas em relacao ao
# docker-entrypoint.sh (desenvolvimento):
#
#   - sem a flag de reload automatico: em producao o reload reinicia o
#     processo a cada arquivo tocado e e incompativel com --workers;
#   - sem seed: o super admin e criado uma vez, por comando manual, para nao
#     exigir SAC_SEED_ADMIN_PASSWORD permanente no ambiente do servidor
#     (ver docs/deploy.md);
#   - com --workers: mais de um processo e seguro aqui porque o listener de
#     notificacoes faz um LISTEN por processo e o Postgres entrega o NOTIFY a
#     todos (ver notify_listener.py).
#
# As migrations rodam antes do exec, uma vez por container, com o servidor
# ainda fora do ar -- e nao dentro do processo que atende requisicao.
set -e

uv run --frozen --no-dev python -m sac.infrastructure.migrate all

exec uv run --frozen --no-dev uvicorn sac.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${SAC_UVICORN_WORKERS:-2}" \
  --proxy-headers \
  --forwarded-allow-ips '*'
