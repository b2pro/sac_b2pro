#!/usr/bin/env bash
# Aplica as migrations dentro do container backend que ja esta no ar,
# reaproveitando as variaveis do .env.prod -- a mesma config que o app usa em
# runtime.
#
# Uso:
#   ./migrate.sh                # schema public + todos os schemas de tenant (default)
#   ./migrate.sh public         # so o schema public (users, tenants, user_tenants)
#   ./migrate.sh tenants        # so os schemas de tenant (t_<slug>)
#
# Quando isto e necessario, se o entrypoint de producao ja roda `migrate all` a
# cada boot do backend: quando o container do backend NAO e recriado. O
# `docker compose up -d` so recria servico cuja imagem ou configuracao mudou,
# entao um `./up.sh` sem `./build.sh` antes sobe a imagem antiga e nao aplica
# migration nova nenhuma. Rodar isto forca, sem depender de o compose ter
# decidido recriar o container.
#
# `tenants` percorre os schemas que existem no banco no momento da execucao. Um
# tenant criado depois nasce ja migrado, pelo provisionador.

set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env.prod ]; then
  echo "ERRO: .env.prod nao encontrado. Rode ./scripts/setup-prod.sh." >&2
  exit 1
fi

DC=(docker compose --env-file .env.prod -f docker-compose.prod.yml)

alvo="${1:-all}"
case "$alvo" in
  public | tenants | all) ;;
  *)
    echo "ERRO: alvo invalido '$alvo'. Use: public | tenants | all." >&2
    exit 1
    ;;
esac

# `exec` exige o container no ar. Sem esta checagem o erro do docker e obscuro.
if [ -z "$("${DC[@]}" ps -q backend 2>/dev/null)" ]; then
  echo "ERRO: o servico backend nao esta no ar. Rode ./up.sh primeiro." >&2
  exit 1
fi

echo "==> Aplicando migrations: $alvo"
# -T desliga a alocacao de TTY, para funcionar dentro de script.
"${DC[@]}" exec -T backend uv run --frozen --no-dev python -m sac.infrastructure.migrate "$alvo"
echo "==> Migrations concluidas."
