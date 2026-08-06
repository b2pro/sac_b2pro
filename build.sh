#!/usr/bin/env bash
# Constroi as imagens de producao.
#
# Uso:
#   ./build.sh                  # todas as imagens (backend, worker, web)
#   ./build.sh web              # so um servico
#   ./build.sh --no-cache       # rebuild sem cache
#
# O build do `web` roda o Vite (tsc + bundle) dentro do container e e o mais
# demorado. Enquanto ele roda, a stack no ar continua servindo a imagem antiga:
# nada e trocado aqui, so construido. Quem troca e o ./up.sh.

set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env.prod ]; then
  echo "ERRO: .env.prod nao encontrado. Rode ./scripts/setup-prod.sh." >&2
  exit 1
fi

docker compose --env-file .env.prod -f docker-compose.prod.yml build "$@"
