#!/bin/sh
# Entrypoint de PRODUCAO. Diferencas deliberadas em relacao ao
# docker-entrypoint.sh (desenvolvimento):
#
#   - sem --reload: em producao o reload reinicia o processo a cada arquivo
#     tocado e e incompativel com --workers;
#   - sem seed: o super admin e criado uma vez, por comando manual, para nao
#     exigir SAC_SEED_ADMIN_PASSWORD permanente no ambiente do servidor
#     (ver docs/deploy.md);
#   - com --workers: mais de um processo e seguro aqui porque o listener de
#     notificacoes faz um LISTEN por processo e o Postgres entrega o NOTIFY a
#     todos (ver notify_listener.py). Efeito colateral: o limitador de login
#     (rate_limit.py) guarda os contadores em memoria do processo, entao o
#     teto configurado em SAC_LOGIN_RATE_IP_TENANT e SAC_LOGIN_RATE_IP vale
#     por worker -- o teto efetivo e o configurado multiplicado por
#     SAC_UVICORN_WORKERS (ver docs/deploy.md);
#   - sem --proxy-headers e sem --forwarded-allow-ips: este backend nao gera
#     URL absoluta (nada usa request.url, scheme, url_for nem
#     RedirectResponse) e o unico consumidor de IP de cliente e o limitador
#     de login, que le X-Forwarded-For por conta propria conforme
#     SAC_TRUSTED_PROXY (client_ip, em rate_limit.py) -- essas flags so
#     reescreveriam request.client sem nenhum efeito util, e no modo
#     "confia em todos" (--forwarded-allow-ips '*') o uvicorn usa o item MAIS
#     A ESQUERDA do header, que e o que o proprio cliente manda: com
#     SAC_TRUSTED_PROXY=false isso tornaria o limitador falsificavel de novo,
#     por outro caminho.
#
# As migrations rodam antes do exec, uma vez por container, com o servidor
# ainda fora do ar -- e nao dentro do processo que atende requisicao.
set -e

uv run --frozen --no-dev python -m sac.infrastructure.migrate all

exec uv run --frozen --no-dev uvicorn sac.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${SAC_UVICORN_WORKERS:-2}"
