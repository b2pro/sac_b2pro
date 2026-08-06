#!/usr/bin/env bash
# Derruba a stack de producao.
#
# Uso:
#   ./down.sh                   # para os containers; os dados persistem
#   ./down.sh --volumes         # APAGA o volume do Postgres: perde o banco
#
# Sem `--volumes`, isto e reversivel: `./up.sh` traz tudo de volta com os dados
# intactos. O site fica fora do ar enquanto os containers estiverem parados.
#
# Com `--volumes`, nao e reversivel. O volume sac-prod_pgdata guarda o banco
# inteiro -- tickets, anexos, usuarios -- e nao existe backup automatico neste
# projeto (o pg_dump e manual, ver docs/deploy.md). Os anexos no Wasabi
# sobreviveriam ao volume, mas ficariam orfaos: sem as linhas do banco, a
# varredura de reconciliacao do worker os apagaria na proxima passada. Por isso a
# flag pede confirmacao digitada em vez de obedecer direto: ela esta a um
# caractere de distancia de um `down` comum.

set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env.prod ]; then
  echo "ERRO: .env.prod nao encontrado." >&2
  exit 1
fi

destrutivo=0
for arg in "$@"; do
  case "$arg" in
    -v | --volumes) destrutivo=1 ;;
  esac
done

if [ "$destrutivo" -eq 1 ]; then
  echo "AVISO: isto apaga o volume sac-prod_pgdata -- o banco de producao inteiro."
  echo "       Nao ha backup automatico. Se voce quer um, rode o pg_dump de"
  echo "       docs/deploy.md ANTES de continuar."
  if [ ! -t 0 ]; then
    echo "ERRO: sem terminal para confirmar; recusando apagar o volume." >&2
    exit 1
  fi
  read -rp "Digite 'apagar' para confirmar: " resposta
  if [ "$resposta" != "apagar" ]; then
    echo "Cancelado. Nada foi apagado."
    exit 1
  fi
fi

docker compose --env-file .env.prod -f docker-compose.prod.yml down "$@"
