#!/usr/bin/env bash
# Sobe a stack de producao.
#
# Uso:
#   ./up.sh                     # sobe tudo
#   ./up.sh backend worker      # sobe so esses servicos
#   ./up.sh migrate             # sobe tudo e forca as migrations no fim
#   ./up.sh backend migrate     # sobe so o backend e forca as migrations
#
# A palavra `migrate`, em qualquer posicao, e tratada como flag e nao como nome
# de servico: ela dispara ./migrate.sh depois que os servicos sobem.
#
# Por que a flag existe, se o entrypoint de producao ja roda `migrate all` a cada
# boot do backend: o `up -d` so recria servico cuja imagem ou configuracao mudou.
# Um `./up.sh` sem `./build.sh` antes sobe a imagem antiga, o container do backend
# nao e recriado, e nenhuma migration nova e aplicada. A flag forca, sem depender
# dessa decisao do compose.
#
# Nao constroi imagem: para isso, ./build.sh antes.

set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env.prod ]; then
  echo "ERRO: .env.prod nao encontrado. Rode ./scripts/setup-prod.sh." >&2
  exit 1
fi

DC=(docker compose --env-file .env.prod -f docker-compose.prod.yml)

rodar_migrate=0
servicos=()
for arg in "$@"; do
  if [ "$arg" = "migrate" ]; then
    rodar_migrate=1
  else
    servicos+=("$arg")
  fi
done

"${DC[@]}" up -d ${servicos[@]+"${servicos[@]}"}

echo ""
echo "==> Estado dos servicos"
"${DC[@]}" ps

if [ "$rodar_migrate" -eq 1 ]; then
  echo ""
  echo "==> Flag 'migrate' recebida"
  # O migrate roda por `exec` no backend, que precisa estar respondendo. O
  # healthcheck do backend so fica verde depois das migrations do boot e do
  # uvicorn no ar, entao esperar por ele evita um `exec` contra container que
  # ainda esta subindo.
  cid=$("${DC[@]}" ps -q backend || true)
  if [ -z "$cid" ]; then
    echo "ERRO: backend nao esta no ar; nao ha onde aplicar as migrations." >&2
    exit 1
  fi
  decorrido=0
  while [ "$(docker inspect --format '{{.State.Health.Status}}' "$cid" 2>/dev/null)" != "healthy" ]; do
    if [ "$decorrido" -ge 180 ]; then
      echo "ERRO: backend nao ficou saudavel em ${decorrido}s. Veja:" >&2
      echo "  ./down.sh && ./up.sh   ou   docker compose --env-file .env.prod -f docker-compose.prod.yml logs backend" >&2
      exit 1
    fi
    sleep 3
    decorrido=$((decorrido + 3))
  done
  ./migrate.sh
fi
