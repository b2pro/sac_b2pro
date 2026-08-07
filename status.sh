#!/usr/bin/env bash
# Mostra o estado da stack, tudo numa tela.
#
# Uso:
#   ./status.sh                 # a stack de producao (.env.prod + docker-compose.prod.yml)
#   ./status.sh --dev           # a stack de desenvolvimento (docker-compose.yml)
#
# Sai com 0 se esta tudo certo e 1 se algo esta errado, para servir de checagem
# em cron ou alerta, nao so de leitura humana.
#
# O `docker compose ps` sozinho nao responde as perguntas que importam depois de
# um deploy: um container pode estar "Up" e reiniciando em loop, o backend pode
# estar de pe sem ter aplicado migration, e o nginx pode estar servindo a SPA com
# a API retornando 502. Aqui cada uma dessas vira uma linha com veredito.
#
# Somente leitura: nao sobe, nao derruba, nao aplica migration.

# Sem `-e` de proposito: a graca do script e continuar checando depois que uma
# verificacao falha. O acumulador `problemas` e quem decide o codigo de saida.
set -uo pipefail

cd "$(dirname "$0")"

modo="prod"
for arg in "$@"; do
  case "$arg" in
    --dev) modo="dev" ;;
    -h | --help)
      sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "ERRO: argumento desconhecido: $arg (use --dev ou --help)" >&2
      exit 1
      ;;
  esac
done

if [ "$modo" = "prod" ]; then
  if [ ! -f .env.prod ]; then
    echo "ERRO: .env.prod nao encontrado. Rode ./scripts/setup-prod.sh." >&2
    echo "      Para olhar a stack de desenvolvimento: ./status.sh --dev" >&2
    exit 1
  fi
  DC=(docker compose --env-file .env.prod -f docker-compose.prod.yml)
  servicos=(db backend worker web)
else
  DC=(docker compose -f docker-compose.yml)
  servicos=(db minio backend worker)
fi

problemas=0

ok() { printf '  [ ok ]  %s\n' "$1"; }
falha() {
  printf '  [FALHA] %s\n' "$1"
  problemas=$((problemas + 1))
}
nota() { printf '  [ -- ]  %s\n' "$1"; }
titulo() { printf '\n== %s\n' "$1"; }

# --- containers ---------------------------------------------------------------
titulo "Containers ($modo)"

for servico in "${servicos[@]}"; do
  cid=$("${DC[@]}" ps -q "$servico" 2>/dev/null)
  if [ -z "$cid" ]; then
    falha "$servico: nao esta no ar"
    continue
  fi

  estado=$(docker inspect --format '{{.State.Status}}' "$cid" 2>/dev/null)
  saude=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}sem healthcheck{{end}}' "$cid" 2>/dev/null)
  reinicios=$(docker inspect --format '{{.RestartCount}}' "$cid" 2>/dev/null)
  desde=$(docker inspect --format '{{.State.StartedAt}}' "$cid" 2>/dev/null | cut -c1-19)

  descricao="$servico: $estado, $saude, no ar desde $desde"
  # Reinicio nao zera o "Up": um container em loop de crash aparece saudavel no
  # `ps` e so o contador denuncia.
  if [ "${reinicios:-0}" -gt 0 ]; then
    descricao="$descricao, ${reinicios} reinicio(s)"
  fi

  if [ "$estado" != "running" ]; then
    falha "$descricao"
  elif [ "$saude" = "unhealthy" ]; then
    falha "$descricao"
  elif [ "${reinicios:-0}" -gt 0 ]; then
    falha "$descricao"
  else
    ok "$descricao"
  fi
done

# --- respostas HTTP -----------------------------------------------------------
titulo "HTTP"

codigo() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$1" 2>/dev/null; }

# Endereco onde da para bater com curl, ou vazio se o servico nao publica a porta.
#
# Duas armadilhas do `docker compose port`, ambas com codigo de saida 0: quando a
# porta NAO esta publicada ele imprime `invalid IP:0`, e quando esta aberta em
# todas as interfaces ele devolve 0.0.0.0 (ou [::]), que serve para escutar e nao
# para conectar. As duas passam por um teste de string vazia.
endereco() {
  local bruto
  bruto=$("${DC[@]}" port "$1" "$2" 2>/dev/null)
  case "$bruto" in
    "" | *invalid* | *:0) return 0 ;;
  esac
  printf '%s' "$bruto" | sed -e 's/^0\.0\.0\.0:/127.0.0.1:/' -e 's/^\[::\]:/127.0.0.1:/'
}

web_addr=$(endereco web 80)
if [ -n "$web_addr" ]; then
  base="http://$web_addr"
  # A SPA e a API atravessam o mesmo nginx: se o deep link cair e a raiz nao, o
  # que quebrou foi o fallback do react-router, nao o servidor.
  for caminho in "/:SPA na raiz" "/tickets:deep link do react-router" "/api/health:API atraves do nginx"; do
    url="${caminho%%:*}"
    rotulo="${caminho#*:}"
    resposta=$(codigo "$base$url")
    if [ "$resposta" = "200" ]; then
      ok "$rotulo: $resposta"
    else
      falha "$rotulo: $resposta ($base$url)"
    fi
  done
else
  api_addr=$(endereco backend 8000)
  if [ -n "$api_addr" ]; then
    resposta=$(codigo "http://$api_addr/api/health")
    if [ "$resposta" = "200" ]; then
      ok "API direto na porta publicada: $resposta"
    else
      falha "API direto na porta publicada: $resposta (http://$api_addr/api/health)"
    fi
    nota "sem servico web nesta stack: o Vite roda fora do compose"
  else
    falha "nem web nem backend com porta publicada: nao ha o que checar"
  fi
fi

# --- exposicao ----------------------------------------------------------------
# So faz sentido em producao: em dev o backend e publicado de proposito, para o
# Vite e os testes de integracao alcancarem ele.
if [ "$modo" = "prod" ]; then
  titulo "Exposicao"
  # Aqui a pergunta nao e "onde conecto", e "existe alguma publicacao?" -- e para
  # essa o `docker compose port` nao serve nem com a limpeza acima: ele responde
  # sobre uma porta que voce escolheu perguntar. Quem sabe o que esta publicado,
  # em qualquer porta, e o proprio container.
  for servico in backend db; do
    cid=$("${DC[@]}" ps -q "$servico" 2>/dev/null)
    if [ -z "$cid" ]; then
      nota "$servico fora do ar: nada publicado, e a falha ja foi contada acima"
      continue
    fi
    publicado=$(docker inspect --format \
      '{{range $porta, $binds := .NetworkSettings.Ports}}{{range $binds}}{{$porta}} em {{.HostIp}}:{{.HostPort}} {{end}}{{end}}' \
      "$cid" 2>/dev/null)
    if [ -z "$publicado" ]; then
      ok "$servico nao esta publicado no host"
    else
      falha "$servico publicado em $publicado: deveria ficar so na rede interna"
    fi
  done
fi

# --- migrations ---------------------------------------------------------------
titulo "Migrations"

psql_q() { "${DC[@]}" exec -T db psql -U sac -d sac -Atc "$1" 2>/dev/null; }

schemas=$(psql_q "select table_schema from information_schema.tables where table_name = 'alembic_version' order by 1")
if [ -z "$schemas" ]; then
  falha "nenhuma tabela alembic_version encontrada: as migrations nao rodaram"
else
  consulta=""
  while IFS= read -r schema; do
    [ -z "$schema" ] && continue
    [ -n "$consulta" ] && consulta="$consulta union all "
    consulta="$consulta select '$schema' as schema, version_num from \"$schema\".alembic_version"
  done <<<"$schemas"

  revisoes=$(psql_q "$consulta order by 1")
  publica=$(printf '%s\n' "$revisoes" | grep '^public|' | cut -d'|' -f2)
  tenants=$(printf '%s\n' "$revisoes" | grep -v '^public|')

  if [ -n "$publica" ]; then
    ok "schema public na revisao $publica"
  else
    falha "schema public sem revisao aplicada"
  fi

  if [ -z "$tenants" ]; then
    nota "nenhum schema de tenant ainda"
  else
    quantos=$(printf '%s\n' "$tenants" | wc -l | tr -d ' ')
    distintas=$(printf '%s\n' "$tenants" | cut -d'|' -f2 | sort -u)
    if [ "$(printf '%s\n' "$distintas" | wc -l | tr -d ' ')" -eq 1 ]; then
      ok "$quantos schema(s) de tenant, todos na revisao $distintas"
    else
      # Tenant fora da revisao dos outros e o sintoma de migration que falhou no
      # meio do caminho: o app funciona ate alguem abrir a tela que usa a coluna
      # nova.
      falha "$quantos schema(s) de tenant em revisoes diferentes:"
      printf '%s\n' "$tenants" | sed 's/^/            /'
    fi
  fi
fi

# --- worker -------------------------------------------------------------------
titulo "Worker"

cid_worker=$("${DC[@]}" ps -q worker 2>/dev/null)
if [ -z "$cid_worker" ]; then
  falha "worker fora do ar: previews de anexo e reconciliacao param"
else
  # O worker nao tem healthcheck: e um loop, nao um servidor. A ultima linha de
  # log e o que existe para dizer se ele ainda esta girando.
  ultima=$("${DC[@]}" logs --tail 1 worker 2>/dev/null | tail -1)
  if [ -n "$ultima" ]; then
    ok "ultima linha de log: $ultima"
  else
    nota "sem linhas de log ainda"
  fi
fi

# --- veredito -----------------------------------------------------------------
printf '\n'
if [ "$problemas" -eq 0 ]; then
  echo "Tudo certo."
  exit 0
fi
echo "$problemas verificacao(oes) com problema."
exit 1
