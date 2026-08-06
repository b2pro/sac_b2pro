# Deploy em produção

Procedimento para colocar o SAC-B2PRO no ar numa VPS: topologia, configuração do
Wasabi, proxy reverso do host, primeiro deploy, deploys seguintes, smoke test e
backup. Todo comando de produção usa o compose de produção com o arquivo de
ambiente explícito:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml <comando>
```

O `--env-file` não é enfeite: a interpolação de `${POSTGRES_PASSWORD}` dentro de
`docker-compose.prod.yml` depende dele. Sem ele o compose **aborta** ao subir —
`${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD no .env.prod}` recusa interpolar
para vazio e mostra essa mensagem, em vez de subir com senha vazia ou com algum
valor do shell.

## Topologia

```
internet -> proxy reverso do host (TLS, dominio)
              -> 127.0.0.1:52010  web (nginx: SPA + proxy /api)
                                   -> backend:8000 (uvicorn, sem porta publicada)
                                        -> db:5432 (sem porta publicada)
                                   worker (previews, expiracao de pendentes, orfaos)
```

Quem termina TLS é o **proxy reverso do host** (fora do compose, instalado direto na
VPS) — é ele que guarda o certificado do domínio e fala HTTPS com a internet. Todo o
resto do stack (`web`, `backend`, `db`, `worker`) vive dentro do compose de produção
(projeto `sac-prod`) e fala HTTP em texto puro entre si, isolado na rede interna do
Docker. Só o serviço `web` publica porta no host, e só no loopback:
`127.0.0.1:52010` por padrão. O host é fixo em `127.0.0.1` no
`docker-compose.prod.yml` — só a porta é configurável, por `SAC_WEB_PORT` no
`.env.prod.example` — de propósito: quem expõe na internet é o proxy reverso do
host, nunca o Docker direto. `backend` e `db` não publicam porta nenhuma — o único
jeito de alcançá-los de fora do host é através do `web`.

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
  --origem https://solucionix.com.br

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

**`SAC_RECONCILE_ORPHANS_HOURS` merece atenção antes de preencher.** É a margem de
idade da varredura de objetos órfãos que o `worker` roda no bucket (padrão 24h, piso
de 1h) — e essa varredura **apaga** objetos, quase imediatamente no boot do worker
(`proxima_reconciliacao = 0.0` em `backend/src/sac/infrastructure/worker.py`). Apontar
um segundo stack (staging, ambiente de teste) com banco vazio ou desatualizado para o
bucket de **produção** apaga todo objeto com mais de 24h que não tenha linha
correspondente no banco daquele stack — inclusive anexos em uso. Ver
`docs/armazenamento-anexos.md`, item 3 do checklist.

## Proxy reverso do host

O server block está versionado em **`ops/nginx/sac.conf`** — é a fonte de verdade, e
não uma cópia deste documento. Instalar:

```bash
sudo cp ops/nginx/sac.conf /etc/nginx/sites-available/sac.conf
sudo ln -s /etc/nginx/sites-available/sac.conf /etc/nginx/sites-enabled/sac.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d solucionix.com.br
```

O arquivo escuta **apenas na porta 80** de propósito. O certbot acrescenta o bloco
`443`, as diretivas `ssl_certificate` e o redirect `80 -> 443`, e recarrega o nginx.
Entregar um bloco `443` apontando para certificados que ainda não existem faria o
`nginx -t` falhar e o nginx se recusar a recarregar — o que derrubaria também os
outros sites que esta máquina serve.

**Pré-requisito do certbot:** o domínio já precisa resolver e chegar na VPS
(`dig +short solucionix.com.br`), senão o desafio HTTP-01 do Let's Encrypt falha. Se o
domínio estiver atrás da Cloudflare com proxy ligado, o `dig` devolve IPs anycast dela
(`104.21.x.x`, `172.67.x.x`) e não o IP da VPS — isso é normal e o HTTP-01 ainda
funciona, porque a Cloudflare repassa o desafio para a origem.

**Depois que o certbot roda, o arquivo instalado deixa de ser igual ao do repo.** O
certbot edita `/etc/nginx/sites-available/sac.conf` no lugar, acrescentando o bloco
`443`, as diretivas `ssl_certificate` e o redirect. A partir daí, **nunca** copie
`ops/nginx/sac.conf` por cima do arquivo instalado: o `cp` apagaria o bloco `443` e o
HTTPS pararia — o nginx passaria a atender o domínio pelo `default_server`, que numa
máquina com vários sites é o site de outro. Para aplicar mudança do repo depois do
certbot, edite o arquivo instalado à mão, ou copie e rode o certbot de novo.

### Atrás da Cloudflare: IP real do visitante

Com o proxy da Cloudflare ligado, `$remote_addr` no nginx do host é o IP de uma borda
da Cloudflare, não do visitante. Como o `X-Forwarded-For` é montado a partir dele e o
limitador de login lê o primeiro item, o limite de tentativas passaria a ser contado
**por borda da Cloudflare** em vez de por visitante: um teto quase global, que deixa de
limitar o atacante individual. Nada dá erro; só protege menos.

O `ops/nginx/sac.conf` já traz o `include` do snippet (com curinga, para que a ausência
dele não derrube o nginx). Gerar o snippet na VPS, sempre a partir da fonte da
Cloudflare, porque as faixas mudam:

```bash
sudo mkdir -p /etc/nginx/snippets
{ curl -s https://www.cloudflare.com/ips-v4; echo; \
  curl -s https://www.cloudflare.com/ips-v6; echo; } \
  | grep -v '^$' \
  | sed 's|^|set_real_ip_from |; s|$|;|' \
  | sudo tee /etc/nginx/snippets/cloudflare-realip.conf > /dev/null
echo 'real_ip_header CF-Connecting-IP;' \
  | sudo tee -a /etc/nginx/snippets/cloudflare-realip.conf > /dev/null
wc -l /etc/nginx/snippets/cloudflare-realip.conf   # 23 linhas em 2026-08
sudo nginx -t && sudo systemctl reload nginx
```

**Os dois `echo` não são enfeite.** A lista `ips-v4` da Cloudflare não termina com
newline, então sem eles a última faixa IPv4 cola na primeira IPv6 e o nginx recusa a
configuração inteira:

```
[emerg] host not found in set_real_ip_from "131.0.72.0/222400:cb00::/32"
```

O `grep -v '^$'` remove as linhas vazias que os `echo` introduzem. Como o `nginx -t`
roda antes do `reload`, esse erro para o processo sem derrubar nada — mas só se você
respeitar o `&&`.

Depois de instalar o server block, o `include` já está no `ops/nginx/sac.conf`. Se o
certbot já editou o arquivo instalado, acrescente a linha nele sem sobrescrever o
arquivo:

```bash
sudo cp /etc/nginx/sites-available/sac.conf /etc/nginx/sites-available/sac.conf.bak
sudo sed -i '/set \$sac_upstream/a\    include /etc/nginx/snippets/cloudflare-realip*.conf;' \
  /etc/nginx/sites-available/sac.conf
sudo nginx -t
```

**Verificar que funcionou:** abra o site e confira o `access.log` — o IP das linhas novas
tem de ser o do visitante, não `104.21.x.x` nem `172.67.x.x`.

Se o domínio sair de trás da Cloudflare, **apague o snippet**: confiar em
`CF-Connecting-IP` sem a Cloudflare na frente permite que qualquer cliente mande esse
header e forje o próprio IP — o oposto do que o snippet existe para fazer.

Se mudar `SAC_WEB_PORT` no `.env.prod`, mude também o `proxy_pass` em
`ops/nginx/sac.conf` — são os dois lados da mesma porta, e nada valida que eles
concordam.

**Ponto de maior consequência deste documento**: a linha `proxy_set_header
X-Forwarded-For $remote_addr;` de `ops/nginx/sac.conf` **sobrescreve** o header, ela
não o acrescenta (o que `$proxy_add_x_forwarded_for` faria). Se você escrever o server
block à mão em vez de usar o arquivo versionado, é esta linha que não pode sair errada.
Isso importa porque o limitador de tentativas de
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

**Nunca rode `docker compose up -d` sem `-f docker-compose.prod.yml` dentro de
`/opt/sac`.** O clone traz o repositório inteiro, e sem o `-f` o comando sobe o
compose de **desenvolvimento**: Postgres em `5432:5432` com senha `sac`, backend
em `8000:8000`, MinIO nas portas dele, tudo em `0.0.0.0`, e
`SAC_ENVIRONMENT: development` — que libera o boot com o segredo JWT público do
repositório, e quem tem esse segredo emite token com `sa: true` e vira
super_admin. Some isso ao fato de que a publicação de porta do Docker entra por
`DOCKER-USER`/`PREROUTING` — um firewall do host (`ufw`, por exemplo) **não**
bloqueia essas portas — e é a pior exposição possível, a partir de um comando de
uma linha.

### Caminho recomendado: o script

```bash
git clone <repo> /opt/sac && cd /opt/sac
./scripts/setup-prod.sh
```

O script cobre o primeiro deploy **e** os seguintes. Ele confere os pré-requisitos,
cria o `.env.prod` com permissão 600, **gera** o `SAC_JWT_SECRET` e o
`POSTGRES_PASSWORD` (você não precisa inventar nem guardar nenhum dos dois), pergunta
apenas o que ele não pode saber (bucket e chaves do Wasabi, domínio), sobe o stack,
espera o backend ficar saudável e cria o super admin se ainda não houver nenhum.

**Rodar de novo é seguro, e é o comando de deploy contínuo.** Se o `.env.prod` já
existe, o script não reescreve nenhum valor já preenchido — só completa chaves
vazias. Isso não é conveniência, é necessidade: a imagem do Postgres usa
`POSTGRES_PASSWORD` apenas no `initdb`, quando o diretório de dados está vazio; num
volume que já existe ela é ignorada. Se um segundo deploy regerasse a senha, o banco
continuaria com a antiga enquanto o `SAC_DATABASE_URL` passaria a usar a nova — o
backend pararia de autenticar, o container ficaria `unhealthy` e a aplicação sairia do
ar, com a senha antiga já sobrescrita no arquivo. Rotação de senha do banco é
procedimento manual (ver "Rotação de segredos" abaixo).

### Operação do dia a dia

Depois do primeiro deploy, quatro scripts na raiz cobrem a rotina. Todos exigem o
`.env.prod` e todos apontam para o compose de produção — nenhum deles pode subir o
compose de desenvolvimento por acidente (há teste de guarda para isso em
`backend/tests/unit/test_deploy_config.py`).

| Comando | O que faz |
|---|---|
| `./build.sh` | constrói as imagens. Aceita nome de serviço (`./build.sh web`) e `--no-cache`. Nada é trocado aqui, só construído |
| `./up.sh` | sobe a stack. Aceita nomes de serviço |
| `./up.sh migrate` | sobe e, depois do backend ficar saudável, força as migrations |
| `./down.sh` | para os containers. Os dados persistem, e `./up.sh` traz tudo de volta |
| `./down.sh --volumes` | **apaga o banco.** Pede confirmação digitada e recusa sem terminal |
| `./migrate.sh [public\|tenants\|all]` | aplica migrations no container que já está no ar |

O deploy normal é `git pull`, `./build.sh`, `./up.sh`.

**Sobre a flag `migrate`:** o entrypoint de produção já roda `migrate all` a cada boot
do backend, então um `./build.sh` seguido de `./up.sh` aplica as migrations sozinho — a
imagem muda, o compose recria o container, o entrypoint migra. A flag existe para o caso
em que o backend **não** é recriado: `up -d` só recria serviço cuja imagem ou
configuração mudou, então um `./up.sh` sem `./build.sh` antes sobe a imagem antiga e não
aplica migration nenhuma. A flag força, sem depender dessa decisão do compose.

### Caminho manual

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
antigo. Não há janela em que a SPA (arquivos estáticos) fique fora do ar por causa
do build do frontend.

`docker compose up -d --build` recria só os serviços cuja imagem ou configuração
mudou — o caso mais comum é mudar só o `backend`. Isso causa uma janela breve e
esperada de indisponibilidade da **API** (não da SPA), do tamanho do próprio
restart do container (migrations + boot do uvicorn + `start_period` do
healthcheck); ela existia mesmo antes desta topologia. O que **não** deve mais
acontecer é a janela ficar permanente: o `resolver` do `frontend/nginx.conf`
resolve `backend` a cada request (TTL `valid=10s`), então tão logo o novo
container suba com IP diferente na rede da bridge, as próximas chamadas de API já
alcançam ele. Sem essa diretiva (como era antes desta correção), o nginx guardava
o IP do container antigo pela vida inteira do processo e a API ficava
respondendo 502 até alguém recriar o `web` manualmente — para sempre, não só
durante o deploy.

Rodar `./scripts/setup-prod.sh` de novo faz exatamente esses dois comandos, mais a
espera pelo healthcheck. Ele não regenera segredo nenhum.

## Rotação de segredos

Nenhuma das duas rotações abaixo pode ser feita apenas editando o `.env.prod`, e é por
isso que o script de setup nunca mexe em valor já preenchido.

**Senha do Postgres.** A imagem do Postgres só aplica `POSTGRES_PASSWORD` no `initdb`,
com o diretório de dados vazio. Num volume existente ela é ignorada, então a troca
tem de acontecer **dentro** do banco, e o `.env.prod` só depois:

```bash
# 1. trocar no banco
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  psql -U sac -d sac -c "ALTER USER sac WITH PASSWORD 'NOVA-SENHA';"

# 2. atualizar POSTGRES_PASSWORD no .env.prod (a mão)

# 3. recriar backend e worker, que montam o DSN a partir dela
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d \
  --force-recreate backend worker
```

Use uma senha **hexadecimal ou alfanumérica**: ela entra dentro de uma URL
(`postgresql+asyncpg://sac:SENHA@db:5432/sac`), e caracteres como `/`, `@`, `+` ou `#`
quebram o DSN de um jeito confuso de diagnosticar.

**Segredo JWT.** Trocar `SAC_JWT_SECRET` no `.env.prod` e recriar `backend` invalida
**todas** as sessões em aberto na hora — todo mundo é deslogado e precisa entrar de
novo. Não há dano além disso, mas não faça em horário de uso.

## Smoke test pós-deploy

Depois de qualquer deploy, confirmar cada afirmação abaixo (a Task 5 deste plano roda
esta mesma lista, primeiro localmente com um `.env.prod` de teste antes do primeiro
deploy real):

```bash
# 1. a SPA e servida
curl -s -o /dev/null -w 'raiz: %{http_code}\n' http://127.0.0.1:52010/
# 2. fallback da SPA numa rota do react-router
curl -s -o /dev/null -w 'deep link: %{http_code}\n' http://127.0.0.1:52010/tickets
# 3. a API responde ATRAVES do nginx
curl -s -w '\nhealth: %{http_code}\n' http://127.0.0.1:52010/api/health
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

Nenhum item acima toca storage: com `SAC_S3_BUCKET` vazio o stack sobe healthy do
mesmo jeito, porque nada valida a configuração de S3 no boot. Por isso, acrescentar
um último item manual: rodar

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend \
  uv run --frozen --no-dev python -m sac.infrastructure.provision_bucket --conferir
```

e depois fazer upload real de um anexo pela interface, aguardando o preview
aparecer. É o único jeito de exercitar CORS do bucket, presigned PUT e o job de
preview de ponta a ponta — nada nos itens 1-8 passa por ali.

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
