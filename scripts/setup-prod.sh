#!/usr/bin/env bash
#
# Primeiro deploy E deploys seguintes do SAC em producao. Rodar da raiz do repo:
#
#   ./scripts/setup-prod.sh
#
# Idempotente pela regra mais simples possivel: SE O .env.prod JA EXISTE, ESTE
# SCRIPT NAO REESCREVE NENHUM VALOR QUE JA ESTEJA PREENCHIDO. Ele so completa as
# chaves que faltam.
#
# Por que essa regra e obrigatoria e nao um capricho: a imagem do Postgres usa
# POSTGRES_PASSWORD apenas uma vez, no initdb, quando o diretorio de dados esta
# vazio. Num volume que ja existe ela e ignorada. Se este script regerasse a
# senha num segundo deploy, o banco continuaria com a senha antiga enquanto o
# SAC_DATABASE_URL (montado a partir do .env.prod) passaria a usar a nova: o
# backend pararia de autenticar, o container ficaria unhealthy e a aplicacao
# sairia do ar -- com a senha antiga ja sobrescrita no arquivo. Rotacao de senha
# do banco e procedimento manual, documentado em docs/deploy.md.
#
# O que este script NAO faz, porque nao pode: criar o bucket e a credencial no
# console do Wasabi, apontar o DNS, instalar o server block do nginx e emitir o
# certificado. Ele imprime esses passos no final.

set -euo pipefail

ENV_FILE=".env.prod"
EXEMPLO=".env.prod.example"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)
ESPERA_MAX_SEGUNDOS=300

vermelho() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
aviso() { printf '\033[33m%s\033[0m\n' "$*"; }
passo() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

abortar() {
  vermelho "ERRO: $*"
  exit 1
}

# ---------------------------------------------------------------- pre-requisitos

passo "Conferindo pre-requisitos"

[ -f "docker-compose.prod.yml" ] || abortar "rode da raiz do repositorio (nao achei docker-compose.prod.yml)"
[ -f "$EXEMPLO" ] || abortar "nao achei $EXEMPLO"

command -v docker >/dev/null 2>&1 || abortar "docker nao esta instalado"
docker compose version >/dev/null 2>&1 || abortar "o plugin 'docker compose' (v2) nao esta disponivel"
docker info >/dev/null 2>&1 || abortar "o daemon do docker nao responde (permissao no grupo docker?)"
verde "docker e docker compose ok"

# ------------------------------------------------------------------- utilidades

# Le o valor de uma chave do .env.prod. Devolve vazio se a chave nao existe ou
# esta sem valor.
ler_valor() {
  [ -f "$ENV_FILE" ] || return 0
  local linha
  linha=$(grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 || true)
  printf '%s' "${linha#*=}"
}

# Grava a chave, substituindo a linha existente ou acrescentando ao final.
# Reescreve por linha em vez de usar sed porque o valor pode conter barras e
# outros caracteres que sed interpretaria como sintaxe. O `cat >` no final
# preserva o modo 600 do arquivo original.
gravar_valor() {
  local chave=$1 valor=$2 tmp achou=0
  tmp=$(mktemp)
  if [ -f "$ENV_FILE" ]; then
    while IFS= read -r linha || [ -n "$linha" ]; do
      if [ "${linha%%=*}" = "$chave" ] && [ "$linha" != "${linha#"$chave"=}" ]; then
        printf '%s=%s\n' "$chave" "$valor" >>"$tmp"
        achou=1
      else
        printf '%s\n' "$linha" >>"$tmp"
      fi
    done <"$ENV_FILE"
  fi
  [ "$achou" -eq 1 ] || printf '%s=%s\n' "$chave" "$valor" >>"$tmp"
  cat "$tmp" >"$ENV_FILE"
  rm -f "$tmp"
  # Redundante com o `cat >` (que preserva o modo do arquivo destino), e
  # deliberado: o arquivo guarda o segredo JWT e a senha do banco, e a permissao
  # e barata demais para depender de semantica de redirecionamento.
  chmod 600 "$ENV_FILE"
}

# Hexadecimal de proposito: o valor da senha do banco entra dentro de uma URL
# (postgresql+asyncpg://sac:SENHA@db:5432/sac). Um base64 com '/' ou '+' quebraria
# o DSN de um jeito confuso de diagnosticar.
gerar_segredo() {
  local bytes=$1
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$bytes"
  else
    head -c "$bytes" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# Pergunta so se a chave estiver vazia. -s para nao ecoar segredo na tela.
perguntar_se_vazio() {
  local chave=$1 rotulo=$2 silencioso=${3:-nao} atual resposta
  atual=$(ler_valor "$chave")
  if [ -n "$atual" ]; then
    printf '  %-28s ja preenchido, mantido\n' "$chave"
    return 0
  fi
  [ -t 0 ] || abortar "$chave esta vazio e nao ha terminal para perguntar. Preencha $ENV_FILE a mao."
  while [ -z "${resposta:-}" ]; do
    if [ "$silencioso" = "sim" ]; then
      read -rsp "  $rotulo: " resposta
      printf '\n'
    else
      read -rp "  $rotulo: " resposta
    fi
  done
  gravar_valor "$chave" "$resposta"
  unset resposta
}

# ------------------------------------------------------------------- .env.prod

primeira_vez=0
if [ -f "$ENV_FILE" ]; then
  passo "$ENV_FILE ja existe -- completando so o que falta"
  aviso "Nenhum valor ja preenchido sera alterado (ver comentario no topo deste script)."
else
  passo "Criando $ENV_FILE a partir de $EXEMPLO"
  cp "$EXEMPLO" "$ENV_FILE"
  primeira_vez=1
fi

chmod 600 "$ENV_FILE"

# Gerados: voce nao precisa inventar nem guardar nenhum dos dois.
if [ -z "$(ler_valor SAC_JWT_SECRET)" ]; then
  gravar_valor SAC_JWT_SECRET "$(gerar_segredo 32)"
  verde "  SAC_JWT_SECRET gerado (64 caracteres)"
else
  printf '  %-28s ja preenchido, mantido\n' "SAC_JWT_SECRET"
fi

if [ -z "$(ler_valor POSTGRES_PASSWORD)" ]; then
  gravar_valor POSTGRES_PASSWORD "$(gerar_segredo 24)"
  verde "  POSTGRES_PASSWORD gerado (48 caracteres)"
else
  printf '  %-28s ja preenchido, mantido\n' "POSTGRES_PASSWORD"
fi

passo "Valores que so voce sabe"

# A regiao vem pre-preenchida no modelo, entao "perguntar so se vazio" nunca
# perguntaria -- e uma regiao errada nao da erro obvio: a assinatura da URL cobre
# o header Host, e o Wasabi recusa com mensagem de credencial/endpoint invalido.
# Por isso ela e confirmada na PRIMEIRA execucao, e nunca depois.
if [ "$primeira_vez" -eq 1 ] && [ -t 0 ]; then
  regiao_atual=$(ler_valor SAC_S3_REGION)
  read -rp "  regiao do bucket no Wasabi [${regiao_atual}]: " regiao
  regiao=${regiao:-$regiao_atual}
  if [ "$regiao" != "$regiao_atual" ]; then
    gravar_valor SAC_S3_REGION "$regiao"
    gravar_valor SAC_S3_ENDPOINT_URL "https://s3.${regiao}.wasabisys.com"
    gravar_valor SAC_S3_PUBLIC_ENDPOINT_URL "https://s3.${regiao}.wasabisys.com"
    verde "  regiao e endpoints ajustados para $regiao"
  else
    printf '  %-28s %s\n' "SAC_S3_REGION" "$regiao_atual (mantido)"
  fi
fi

perguntar_se_vazio SAC_S3_BUCKET "nome do bucket no Wasabi"
perguntar_se_vazio SAC_S3_ACCESS_KEY "access key do Wasabi"
perguntar_se_vazio SAC_S3_SECRET_KEY "secret key do Wasabi (nao aparece na tela)" sim

# A origem entra em dois lugares: no CORS da aplicacao e, mais tarde, na politica
# de CORS do bucket. Tem de ser a origem exata, sem barra final.
if [ -z "$(ler_valor SAC_CORS_ORIGINS)" ]; then
  [ -t 0 ] || abortar "SAC_CORS_ORIGINS esta vazio e nao ha terminal para perguntar."
  read -rp "  dominio do frontend (ex.: https://solucionix.com.br): " dominio
  dominio=${dominio%/}
  case "$dominio" in
    https://*|http://*) ;;
    *) abortar "a origem precisa comecar com https:// ou http://" ;;
  esac
  gravar_valor SAC_CORS_ORIGINS "[\"$dominio\"]"
  verde "  SAC_CORS_ORIGINS definido como [\"$dominio\"]"
else
  printf '  %-28s ja preenchido, mantido\n' "SAC_CORS_ORIGINS"
fi

# Confere o que o boot exige, antes de gastar um build.
for obrigatoria in SAC_ENVIRONMENT SAC_JWT_SECRET POSTGRES_PASSWORD SAC_S3_ENDPOINT_URL \
  SAC_S3_PUBLIC_ENDPOINT_URL SAC_S3_REGION SAC_S3_BUCKET SAC_S3_ACCESS_KEY SAC_S3_SECRET_KEY; do
  [ -n "$(ler_valor "$obrigatoria")" ] || abortar "$obrigatoria continua vazio em $ENV_FILE"
done

if [ "$(ler_valor SAC_ENVIRONMENT)" = "development" ]; then
  abortar "SAC_ENVIRONMENT=development em $ENV_FILE: o boot passaria a aceitar o segredo publico do repositorio"
fi
verde "$ENV_FILE completo"

# ------------------------------------------------------------------ build e up

passo "Construindo e subindo o stack"
"${COMPOSE[@]}" up -d --build

passo "Esperando o backend ficar saudavel (limite de ${ESPERA_MAX_SEGUNDOS}s)"
# O healthcheck do backend so fica verde depois que as migrations rodaram e o
# uvicorn subiu, entao esperar por ele e esperar pelo banco migrado.
cid=$("${COMPOSE[@]}" ps -q backend)
[ -n "$cid" ] || abortar "container do backend nao subiu"
decorrido=0
while :; do
  estado=$(docker inspect --format '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo desconhecido)
  [ "$estado" = "healthy" ] && break
  if [ "$estado" = "unhealthy" ] || [ "$decorrido" -ge "$ESPERA_MAX_SEGUNDOS" ]; then
    vermelho "backend ficou '$estado' apos ${decorrido}s. Ultimas linhas do log:"
    "${COMPOSE[@]}" logs --tail 40 backend >&2 || true
    abortar "backend nao ficou saudavel"
  fi
  sleep 3
  decorrido=$((decorrido + 3))
done
verde "backend saudavel (migrations aplicadas)"

# ----------------------------------------------------------------- super admin

passo "Super admin"
# Detecta em vez de usar marcador: se ja existe super admin, nao pergunta nada.
# As credenciais do seed NAO ficam no .env.prod de proposito -- elas entram
# apenas neste comando, uma vez.
ja_existe=$("${COMPOSE[@]}" exec -T db psql -U sac -d sac -tAc \
  "SELECT count(*) FROM public.users WHERE is_super_admin" 2>/dev/null | tr -d '[:space:]' || echo erro)

if [ "$ja_existe" = "erro" ]; then
  aviso "nao consegui consultar o banco; pulando o seed. Crie o admin a mao (ver docs/deploy.md)."
elif [ "$ja_existe" != "0" ]; then
  verde "super admin ja existe ($ja_existe), nada a fazer"
elif [ ! -t 0 ]; then
  aviso "sem super admin e sem terminal para perguntar. Crie a mao (ver docs/deploy.md)."
else
  read -rp "  email do super admin (use um TLD real, .local e recusado): " admin_email
  read -rsp "  senha do super admin (nao aparece na tela): " admin_senha
  printf '\n'
  "${COMPOSE[@]}" run --rm \
    -e SAC_SEED_ADMIN_EMAIL="$admin_email" \
    -e SAC_SEED_ADMIN_PASSWORD="$admin_senha" \
    backend uv run --frozen --no-dev python -m sac.infrastructure.seed
  unset admin_senha
fi

# --------------------------------------------------------------------- resumo

porta=$(ler_valor SAC_WEB_PORT)
porta=${porta:-52010}

passo "Estado dos servicos"
"${COMPOSE[@]}" ps

verde ""
verde "Stack no ar em http://127.0.0.1:${porta} (loopback -- ainda nao publico)."
cat <<FIM

O que falta, e que este script nao pode fazer:

  1. CORS do bucket no Wasabi. Sem isto todo upload pelo navegador falha com um
     erro opaco (xhr.onerror, sem status), e nenhum teste local detecta:

       ${COMPOSE[*]} run --rm backend \\
         uv run --frozen --no-dev python -m sac.infrastructure.provision_bucket \\
         --origem $(ler_valor SAC_CORS_ORIGINS | tr -d '[]"')

       ${COMPOSE[*]} run --rm backend \\
         uv run --frozen --no-dev python -m sac.infrastructure.provision_bucket --conferir

  2. Server block do nginx do host e certificado:

       sudo cp ops/nginx/sac.conf /etc/nginx/sites-available/sac.conf
       sudo ln -s /etc/nginx/sites-available/sac.conf /etc/nginx/sites-enabled/sac.conf
       sudo nginx -t && sudo systemctl reload nginx
       sudo certbot --nginx -d <seu dominio>

     Confira em ops/nginx/sac.conf que a porta do proxy_pass e ${porta}, e que o
     X-Forwarded-For usa \$remote_addr (sobrescreve, nao acrescenta).

  3. Smoke test, incluindo um upload de anexo por um navegador de verdade -- e o
     unico jeito de exercitar o preflight de CORS. Ver docs/deploy.md.

FIM
