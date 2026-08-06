# Deploy em produção

Procedimento para colocar o SAC-B2PRO no ar numa VPS: topologia, configuração do
Wasabi, proxy reverso do host, primeiro deploy, deploys seguintes, smoke test e
backup. Todo comando de produção usa o compose de produção com o arquivo de
ambiente explícito:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml <comando>
```

O `--env-file` não é enfeite: a interpolação de `${POSTGRES_PASSWORD}` dentro de
`docker-compose.prod.yml` depende dele. Sem ele o compose sobe com a senha vazia
ou com o valor default do shell, e a conexão do backend com o banco falha.

## Topologia

```
internet -> proxy reverso do host (TLS, dominio)
              -> 127.0.0.1:8080  web (nginx: SPA + proxy /api)
                                   -> backend:8000 (uvicorn, sem porta publicada)
                                        -> db:5432 (sem porta publicada)
                                   worker (previews, expiracao de pendentes, orfaos)
```

Quem termina TLS é o **proxy reverso do host** (fora do compose, instalado direto na
VPS) — é ele que guarda o certificado do domínio e fala HTTPS com a internet. Todo o
resto do stack (`web`, `backend`, `db`, `worker`) vive dentro do compose de produção
(projeto `sac-prod`) e fala HTTP em texto puro entre si, isolado na rede interna do
Docker. Só o serviço `web` publica porta no host, e só no loopback:
`127.0.0.1:8080` (`SAC_WEB_BIND`, default no `.env.prod.example`). `backend` e `db`
não publicam porta nenhuma — o único jeito de alcançá-los de fora do host é através
do `web`.

Dentro do container `web`, o nginx serve os arquivos estáticos da SPA e faz proxy de
`/api/` (e do stream de notificações) para `backend:8000`. O `worker` não atende
requisição nenhuma: roda em loop, gerando previews de anexos, expirando anexos
pendentes sem confirmação e reconciliando objetos órfãos no bucket.

## Pré-requisitos da VPS

- Docker Engine com o plugin `compose` (`docker compose`, não o binário antigo
  `docker-compose`).
- `git`.
- Um proxy reverso já instalado no host (nginx ou Traefik) com certificado válido
  para o domínio. Este documento assume nginx; a lógica se aplica igual a Traefik.

## Configuração do Wasabi

1. Criar bucket **privado**, sem acesso público de leitura ou escrita, e anotar a
   região.
2. Criar um sub-user com chave de acesso própria (não usar a credencial raiz da
   conta).
3. Aplicar a policy abaixo, que é exatamente o que o código usa — `GetObject` cobre
   também o `HEAD` da confirmação de anexo, e `ListBucket`/`DeleteObject` existem
   para a varredura de órfãos do worker:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketCors",
        "s3:PutBucketCors",
        "s3:GetLifecycleConfiguration",
        "s3:PutLifecycleConfiguration"
      ],
      "Resource": "arn:aws:s3:::SEU-BUCKET"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::SEU-BUCKET/*"
    }
  ]
}
```

4. Aplicar o CORS do bucket. Passo obrigatório e **não verificável localmente**: o
   MinIO de desenvolvimento libera CORS por padrão e nem implementa `PutBucketCors`,
   então nenhum teste local detecta a falta da política, e sem ela todo upload pelo
   navegador falha com um erro opaco (`xhr.onerror`, sem status). Rodar de dentro do
   container, para reaproveitar o `.env.prod`:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend \
  uv run --frozen --no-dev python -m sac.infrastructure.provision_bucket \
  --origem https://sac.b2pro.com.br

docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend \
  uv run --frozen --no-dev python -m sac.infrastructure.provision_bucket --conferir
```

Ver `docs/armazenamento-anexos.md` para o detalhe da política de CORS e da
reconciliação de objetos órfãos.

## Arquivo `.env.prod`

Copiar do modelo e restringir o acesso ao arquivo:

```bash
cp .env.prod.example .env.prod && chmod 600 .env.prod
```

Gerar o segredo do JWT com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`SAC_JWT_SECRET` precisa de no mínimo 32 caracteres — abaixo disso, ou vazio, ou igual
ao segredo de desenvolvimento do repositório, o boot do backend recusa subir
(`ensure_boot_secrets`, em `backend/src/sac/infrastructure/settings.py`). **Trocar
`SAC_JWT_SECRET` invalida todas as sessões em aberto**: todo usuário logado precisa
autenticar de novo. Trocar o segredo é uma operação deliberada (rotação por suspeita
de vazamento, por exemplo), nunca algo para fazer sem avisar quem está usando o
sistema.

## Proxy reverso do host

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name sac.b2pro.com.br;

    ssl_certificate     /etc/letsencrypt/live/sac.b2pro.com.br/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sac.b2pro.com.br/privkey.pem;

    add_header Strict-Transport-Security "max-age=31536000" always;

    # O SSE precisa dos dois lados sem buffer: se este salto bufferizar, as
    # notificacoes param de chegar mesmo com o container configurado certo.
    location = /api/notificacoes/stream {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 1h;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        # SOBRESCREVE o header, nao acrescenta. O limitador de login le o
        # PRIMEIRO item de X-Forwarded-For (rate_limit.py:38): com
        # $proxy_add_x_forwarded_for aqui, um cliente que manda
        # "X-Forwarded-For: 1.2.3.4" viraria o primeiro item e falsificaria o
        # proprio IP, escapando do limite de tentativas de login.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Ponto de maior consequência deste documento**: o `proxy_set_header X-Forwarded-For
$remote_addr;` acima **sobrescreve** o header, ele não o acrescenta (o que
`$proxy_add_x_forwarded_for` faria). Isso importa porque o limitador de tentativas de
login (`client_ip` em `backend/src/sac/interface/rate_limit.py`) lê apenas o
**primeiro** item de `X-Forwarded-For` quando `SAC_TRUSTED_PROXY=true`:

```python
forwarded = request.headers.get("x-forwarded-for")
if forwarded:
    return forwarded.split(",")[0].strip()
```

Se o proxy do host usasse `$proxy_add_x_forwarded_for` em vez de sobrescrever, ele
**concatenaria** ao que o cliente já mandou. Um atacante que envie a requisição com o
header `X-Forwarded-For: 1.2.3.4` chegaria ao nginx do host com
`X-Forwarded-For: 1.2.3.4`, o nginx acrescentaria o IP real dele
(`X-Forwarded-For: 1.2.3.4, <ip real>`), e o limitador leria o primeiro item —
`1.2.3.4`, forjado pelo próprio atacante. Cada tentativa de login com um valor
forjado diferente cai num contador novo e nunca esgota o limite de tentativas: a
proteção de força bruta deixa de existir na prática, mesmo com o código do backend
correto e `SAC_TRUSTED_PROXY=true`. **Sobrescrever, nunca acrescentar**, é a regra que
faz esse limite valer alguma coisa.

Se por algum motivo não for possível garantir essa sobrescrita no proxy do host,
deixar `SAC_TRUSTED_PROXY=false` no `.env.prod` — o limitador passa a contar pelo IP
da conexão TCP direta (o do proxy, não o do cliente), o que degrada o limite a um teto
global de 30 logins/minuto para toda a aplicação com um único worker (pior para uso
legítimo, mas deixa de ser falsificável). **Nunca as duas coisas ao mesmo tempo**:
`SAC_TRUSTED_PROXY=true` com o header sendo acrescentado em vez de sobrescrito é o
pior dos casos — parece protegido e não protege nada.

**O teto real depende de `SAC_UVICORN_WORKERS`.** `SlidingWindowRateLimiter` guarda
os contadores num dict em memória do processo
(`backend/src/sac/interface/rate_limit.py`) — o deploy é de instância única, sem
Redis nem outro store compartilhado. Com `--workers 2` (default) existem dois
processos uvicorn, cada um com o próprio contador: o teto efetivo é o configurado
multiplicado pelo número de workers, não o valor cru. Com o default de produção
isso é 10 tentativas/minuto por IP+tenant e 60/minuto por IP (em vez de 5 e 30).
Ver "Residuais conhecidos".

Nota sobre versão do nginx: `http2 on;` como diretiva separada (como no bloco acima)
exige nginx 1.25.1 ou mais novo. Em versões anteriores essa diretiva não existe e a
configuração nem carrega; a forma correta nesse caso é `listen 443 ssl http2;`, sem a
linha `http2 on;`. Conferir a versão instalada na VPS com `nginx -v` antes de aplicar
este bloco.

## Primeiro deploy

```bash
git clone <repo> /opt/sac && cd /opt/sac
cp .env.prod.example .env.prod && chmod 600 .env.prod
# preencher .env.prod
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

Em seguida criar o super admin, uma única vez (a senha entra só neste comando, não
fica em `.env.prod`; use um shell que não guarda histórico, ou limpe o histórico
depois):

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm \
  -e SAC_SEED_ADMIN_EMAIL=admin@b2pro.com.br \
  -e SAC_SEED_ADMIN_PASSWORD='<senha forte>' \
  backend uv run --frozen --no-dev python -m sac.infrastructure.seed
```

Esperado: `super admin criado: admin@b2pro.com.br`. Rodar de novo responde
`super admin ja existe: admin@b2pro.com.br`, sem efeito — o comando é idempotente.
Use um TLD real no email: endereços `.local`/`.test` são recusados pela validação de
email do login.

## Deploys seguintes

```bash
cd /opt/sac && git pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

As migrations rodam no boot do `backend` (`uv run ... python -m
sac.infrastructure.migrate all`, dentro de `backend/docker-entrypoint.prod.sh`),
antes do uvicorn subir — nunca dentro do processo que atende requisição. Durante o
`--build` do `web` (frontend), o serviço continua no ar servindo a imagem antiga; a
troca só acontece no momento em que o container novo termina de subir e substitui o
antigo. Não há janela em que o site fique fora do ar por causa do build do frontend.

## Smoke test pós-deploy

Depois de qualquer deploy, confirmar cada afirmação abaixo (a Task 5 deste plano roda
esta mesma lista, primeiro localmente com um `.env.prod` de teste antes do primeiro
deploy real):

```bash
# 1. a SPA e servida
curl -s -o /dev/null -w 'raiz: %{http_code}\n' http://127.0.0.1:8080/
# 2. fallback da SPA numa rota do react-router
curl -s -o /dev/null -w 'deep link: %{http_code}\n' http://127.0.0.1:8080/tickets
# 3. a API responde ATRAVES do nginx
curl -s -w '\nhealth: %{http_code}\n' http://127.0.0.1:8080/api/health
# 4. o backend nao esta exposto direto
curl -s -o /dev/null -w 'backend direto: %{http_code}\n' --max-time 3 http://127.0.0.1:8000/api/health
# 5. o banco nao esta exposto
docker compose --env-file .env.prod -f docker-compose.prod.yml port db 5432
# 6. as migrations rodaram
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  psql -U sac -d sac -c "\dt public.*"
# 7. o worker esta vivo e no loop
docker compose --env-file .env.prod -f docker-compose.prod.yml logs worker | tail -5
# 8. o uvicorn subiu com mais de um worker e sem reload
docker compose --env-file .env.prod -f docker-compose.prod.yml logs backend | grep -i -E 'started server|reload|worker'
```

Esperado, em ordem: `200`; `200`; `200` com corpo JSON de health; falha de conexão
(código `000` — nada escutando na 8000 do host); saída vazia ou erro do `port` (porta
não publicada); a listagem com as tabelas globais (`users`, `tenants`,
`user_tenants`); a linha do loop do worker; e, nas linhas do uvicorn, nenhuma menção a
reload, com mais de um processo iniciado.

Depois disso, criar o super admin pelo comando da seção "Primeiro deploy" e confirmar
a resposta esperada (`super admin criado: ...`, depois `super admin ja existe: ...`
numa segunda chamada).

## Backup

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  pg_dump -U sac -d sac --format=custom > sac-$(date +%F).dump
```

Restauração:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  pg_restore -U sac -d sac --clean --if-exists < sac-AAAA-MM-DD.dump
```

**Não existe backup automático.** Agendar este comando no cron da VPS e enviar o
arquivo resultante para fora da máquina é responsabilidade de quem opera. Um dump
guardado no mesmo disco do banco não protege contra perda do disco — se o disco da
VPS falhar ou o volume for apagado por engano, o dump se perde junto.

## Residuais conhecidos

- **Sem CSP.** Com o token de sessão em `localStorage`, um XSS consegue ler a sessão;
  uma Content-Security-Policy é a mitigação certa, mas montar uma às cegas quebra a
  aplicação (scripts inline, origens de fonte/imagem, etc.). Fica como tarefa própria,
  com verificação no navegador depois de cada ajuste.
- **Sem backup automatizado** — ver seção "Backup" acima.
- **Limitador de login não é compartilhado entre workers.** `SlidingWindowRateLimiter`
  guarda os contadores num dict em memória do processo — com `SAC_UVICORN_WORKERS=2`
  existem dois contadores independentes, e o teto real é o dobro do configurado (ver
  seção "Proxy reverso do host" acima). Um store compartilhado (Redis, por exemplo)
  é a solução real e não existe hoje; o limite continua existindo, só não é exato.
