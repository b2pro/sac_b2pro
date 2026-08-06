# Setup de Producao Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao SAC-B2PRO um caminho de deploy em producao numa VPS unica: compose de prod, imagem do frontend com nginx servindo a SPA e roteando `/api`, entrypoint de backend sem `--reload`, e um `docs/deploy.md` que cobre o que nao e verificavel localmente (Wasabi e proxy do host).

**Architecture:** O proxy reverso que ja existe na VPS termina TLS e aponta para `127.0.0.1:8080`, onde o container `web` (nginx) serve o build estatico do Vite e faz `proxy_pass` de `/api` para o container `backend` pela rede interna do compose. `backend` e `db` nao publicam porta. O compose de prod chama-se `sac-prod` para que os volumes nao colidam com os do compose de desenvolvimento. Segredos vivem num `.env.prod` que existe apenas na VPS.

**Tech Stack:** Docker Compose, nginx 1.27-alpine, Node 24 + pnpm 9.15.0 (build do Vite), uvicorn com multiplos workers, PostgreSQL 16, Wasabi S3, pytest para os testes de guarda de configuracao.

## Global Constraints

- **PROIBIDO usar emojis** em codigo, comentarios, commits, UI e documentacao.
- Sem CI: antes de cada commit que toque Python, rodar em `backend/`: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`.
- `pytest` completo estoura timeout curto: sempre rodar com timeout explicito de 600000 ms.
- Convencao de texto do repo: comentario em codigo e arquivo de configuracao em portugues **sem acento** (ver `settings.py`, `docker-compose.yml`); documentacao em `docs/` em portugues **com acento** (ver `docs/armazenamento-anexos.md`).
- Nada de segredo commitado. `.env.prod` nunca entra no git; so `.env.prod.example`. Atencao: o `.gitignore` da raiz tem `.env`, que casa apenas com o nome exato — `.env.prod` **nao** esta coberto hoje, e a Task 2 acrescenta a regra.
- `docker compose` de producao SEMPRE com `--env-file .env.prod -f docker-compose.prod.yml`. A interpolacao de `${POSTGRES_PASSWORD}` depende do `--env-file`; sem ele o compose falha com a mensagem do `:?`.
- Versoes exatas a usar: `postgres:16`, `nginx:1.27-alpine`, `node:24-alpine`, `pnpm@9.15.0`.
- Caminhos exatos que o nginx precisa conhecer: health em `/api/health`, stream SSE em `/api/notificacoes/stream`.

## Contexto que o implementador precisa saber

Fatos ja verificados no codigo, para nao serem redescobertos:

1. `frontend/src/lib/api.ts:105` chama `` fetch(`/api${path}`) `` — **relativo**. Nao existe variavel de ambiente de URL da API; quem serve a SPA precisa servir `/api` na mesma origem.
2. A sessao viaja em `Authorization: Bearer` com token no `localStorage` (`api.ts:109`). Nao ha cookie, logo nao ha requisito de `SameSite`.
3. `backend/src/sac/interface/rate_limit.py:35-39`: `client_ip` confia no **primeiro** item de `X-Forwarded-For` quando `trusted_proxy=True`. Portanto o proxy do host precisa **sobrescrever** o header (`proxy_set_header X-Forwarded-For $remote_addr;`), nunca acrescentar — se acrescentar, o cliente falsifica o IP e escapa do limitador de login.
4. Com `trusted_proxy=False` atras de proxy, todo login compartilha o IP do proxy e `login_rate_ip=30` (`settings.py:47`) passa a ser um teto global de 30 logins por minuto para a empresa inteira. Por isso `SAC_TRUSTED_PROXY=true` e obrigatorio nesta topologia.
5. `backend/src/sac/infrastructure/notify_listener.py:53-64`: um `LISTEN` por processo, e o Postgres entrega o `NOTIFY` a todos. Logo `uvicorn --workers N` **nao** quebra o SSE.
6. `backend/src/sac/infrastructure/settings.py:18` — `environment` tem default `"production"` e `ensure_boot_secrets` (linha 64) aborta o boot sem `SAC_JWT_SECRET` proprio de 32+ caracteres. `SAC_ENVIRONMENT=development` faz a aplicacao subir com o segredo publico do repositorio: e o erro que os testes de guarda deste plano existem para pegar.
7. `backend/src/sac/infrastructure/seed.py:11-13` — o seed e idempotente e nao faz nada sem `SAC_SEED_ADMIN_EMAIL`/`SAC_SEED_ADMIN_PASSWORD`. Em prod ele sai do boot e vira comando manual.
8. `SAC_CORS_ORIGINS` e `list[str]` no pydantic-settings: no `.env` precisa de JSON (`["https://sac.b2pro.com.br"]`), nao de valor solto.
9. O frontend usa **pnpm** (`frontend/pnpm-lock.yaml`, lockfileVersion 9.0). Nao existe `package-lock.json`; `npm ci` falharia.
10. `frontend/tsconfig.app.json` inclui apenas `src`, e `tsconfig.node.json` apenas `vite.config.ts`. `pnpm build` (`tsc -b && vite build`) nao toca `e2e/` nem `playwright.config.ts`, que podem ficar fora do contexto do Docker.
11. `backend/Dockerfile` ja instala com `uv sync --frozen --no-dev` (sem dependencias de desenvolvimento) e nao precisa mudar: o compose de prod so troca o `command`.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `backend/docker-entrypoint.prod.sh` (criar) | Rodar migrations e subir uvicorn de producao. Sem `--reload`, sem seed. |
| `backend/tests/unit/test_deploy_config.py` (criar) | Testes de guarda: impedir que o entrypoint/compose de prod voltem a ter caracteristica de desenvolvimento. |
| `docker-compose.prod.yml` (criar) | Topologia de producao: `db`, `backend`, `worker`, `web`. |
| `.env.prod.example` (criar) | Todas as chaves de producao, sem valores, com o porque de cada uma. |
| `.gitignore` (modificar) | Passar a ignorar `.env.prod`, hoje descoberto. |
| `CLAUDE.md` (modificar) | Listar `docs/deploy.md` entre os documentos de apoio. |
| `frontend/Dockerfile` (criar) | Build do Vite com pnpm e imagem final nginx com o `dist`. |
| `frontend/nginx.conf` (criar) | Servir a SPA, rotear `/api`, tratar o SSE, cache e headers de seguranca. |
| `frontend/.dockerignore` (criar) | Manter `node_modules`, `dist` e artefatos de teste fora do contexto de build. |
| `docs/deploy.md` (criar) | Procedimento de deploy, configuracao do Wasabi, bloco do proxy do host, smoke test, backup. |
| `docs/armazenamento-anexos.md` (modificar) | Corrigir a secao de objetos orfaos, hoje desatualizada. |

---

### Task 1: Entrypoint de producao do backend, com testes de guarda

**Files:**
- Create: `backend/docker-entrypoint.prod.sh`
- Create: `backend/tests/unit/test_deploy_config.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: o arquivo `backend/docker-entrypoint.prod.sh`, invocado na Task 2 como `command: ["sh", "docker-entrypoint.prod.sh"]`; e o modulo de teste `backend/tests/unit/test_deploy_config.py`, ao qual a Task 2 acrescenta funcoes. Constantes definidas neste modulo e reutilizadas na Task 2: `RAIZ`, `ENTRYPOINT_PROD`, `COMPOSE_PROD`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/tests/unit/test_deploy_config.py`:

```python
"""Guardas de configuracao de deploy.

Estes testes nao exercitam codigo da aplicacao: eles leem os arquivos de deploy
e travam as caracteristicas cuja perda seria silenciosa em producao. O modo de
falha que eles cobrem e concreto -- alguem copia o entrypoint ou o compose de
desenvolvimento por cima do de producao, tudo sobe normalmente, e a aplicacao
passa a assinar token com o segredo publico do repositorio ou a rodar com
`--reload` e um unico worker.
"""

from pathlib import Path

# tests/unit/test_deploy_config.py -> tests/unit -> tests -> backend -> raiz
RAIZ = Path(__file__).resolve().parents[3]
ENTRYPOINT_PROD = RAIZ / "backend" / "docker-entrypoint.prod.sh"
COMPOSE_PROD = RAIZ / "docker-compose.prod.yml"


def test_entrypoint_de_prod_existe() -> None:
    assert ENTRYPOINT_PROD.is_file()


def test_entrypoint_de_prod_nao_usa_reload() -> None:
    """--reload derruba os workers (uvicorn recusa reload com --workers) e
    reinicia o processo a cada arquivo tocado."""
    assert "--reload" not in ENTRYPOINT_PROD.read_text(encoding="utf-8")


def test_entrypoint_de_prod_nao_roda_seed() -> None:
    """O super admin nasce por comando manual: deixar o seed no boot exige a
    senha do admin permanente no ambiente do servidor."""
    assert "sac.infrastructure.seed" not in ENTRYPOINT_PROD.read_text(encoding="utf-8")


def test_entrypoint_de_prod_roda_as_migrations() -> None:
    """Sem isto o container sobe e responde 500 em toda rota com tabela
    faltando depois de um deploy que trouxe migration nova."""
    conteudo = ENTRYPOINT_PROD.read_text(encoding="utf-8")
    assert "sac.infrastructure.migrate all" in conteudo
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
cd backend
uv run pytest tests/unit/test_deploy_config.py -v
```

Esperado: FAIL. `test_entrypoint_de_prod_existe` falha no `assert`, e os tres seguintes
falham com `FileNotFoundError` ao chamar `read_text` num arquivo que nao existe.

- [ ] **Step 3: Criar o entrypoint de producao**

Criar `backend/docker-entrypoint.prod.sh`:

```sh
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
```

Nota sobre as duas ultimas flags: elas fazem o uvicorn respeitar `X-Forwarded-Proto`
ao montar `request.url`, o que mantem correta qualquer URL absoluta gerada pela
aplicacao atras do TLS do proxy. `--forwarded-allow-ips '*'` e aceitavel aqui porque
o container nao publica porta: so o nginx da rede interna alcanca a porta 8000. Isso
nao afeta o limitador de login, que le o header por conta propria via
`client_ip`/`SAC_TRUSTED_PROXY`.

- [ ] **Step 4: Rodar os testes e confirmar que passam**

```bash
cd backend
uv run pytest tests/unit/test_deploy_config.py -v
```

Esperado: PASS, 4 passed.

- [ ] **Step 5: Rodar as verificacoes locais completas**

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Esperado: tudo verde. Rodar o `pytest` com timeout explicito de 600000 ms.
Se `ruff format --check` reclamar do arquivo novo de teste, rodar
`uv run ruff format tests/unit/test_deploy_config.py` e repetir.

- [ ] **Step 6: Commit**

```bash
git add backend/docker-entrypoint.prod.sh backend/tests/unit/test_deploy_config.py
git commit -m "Adiciona entrypoint de producao do backend sem reload nem seed"
```

---

### Task 2: Compose de producao e modelo de .env

**Files:**
- Create: `docker-compose.prod.yml`
- Create: `.env.prod.example`
- Modify: `.gitignore` (acrescentar `.env.prod`)
- Modify: `backend/tests/unit/test_deploy_config.py` (acrescentar funcoes ao final)

**Interfaces:**
- Consumes: `backend/docker-entrypoint.prod.sh` (Task 1), invocado como `command: ["sh", "docker-entrypoint.prod.sh"]`; a constante `COMPOSE_PROD` do modulo de teste da Task 1.
- Produces: o servico `web` com `build: ./frontend`, que a Task 3 preenche com o `Dockerfile`; os nomes de servico `db`, `backend`, `worker`, `web` e o nome de projeto `sac-prod`, usados nos comandos de `docs/deploy.md` (Task 4); o hostname interno `backend` na porta 8000, alvo do `proxy_pass` da Task 3.

- [ ] **Step 1: Escrever os testes que falham**

O modulo `backend/tests/unit/test_deploy_config.py` ja existe (Task 1) e ja traz os
helpers `_conteudo_prod()` e `_sem_comentarios(conteudo)`. **Reuse `_sem_comentarios`
nos testes novos, nao duplique a logica**: toda asserção de substring abaixo roda sobre
as linhas executaveis, porque um comentario do compose ou do `.env` pode legitimamente
citar o termo proibido para explicar que ele nao deve ser usado. Isso vale tanto para
YAML quanto para `.env`: os dois comentam com `#`.

Acrescentar as constantes junto das outras, no topo do arquivo (logo abaixo de
`COMPOSE_PROD`):

```python
ENV_EXEMPLO = RAIZ / ".env.prod.example"
GITIGNORE = RAIZ / ".gitignore"
```

E acrescentar ao final de `backend/tests/unit/test_deploy_config.py`:

```python
def _conteudo_compose() -> str:
    return _sem_comentarios(COMPOSE_PROD.read_text(encoding="utf-8"))


def test_compose_de_prod_existe() -> None:
    assert COMPOSE_PROD.is_file()


def test_compose_de_prod_nao_declara_ambiente_de_desenvolvimento() -> None:
    """SAC_ENVIRONMENT=development faz ensure_boot_secrets liberar o boot com o
    segredo publico do repositorio, e a aplicacao passa a assinar token
    forjavel -- quem tem o segredo emite um access token com `sa: true` e vira
    super_admin.

    O compose de prod nao define SAC_ENVIRONMENT (vem do .env.prod), entao este
    teste cobre apenas o caso de alguem inline-ar o valor errado aqui. O que
    esta no .env.prod da VPS nenhum teste alcanca -- por isso o teste seguinte
    trava o modelo, que e o arquivo de onde a copia sai.
    """
    conteudo = _conteudo_compose()
    assert "SAC_ENVIRONMENT: development" not in conteudo
    assert "SAC_ENVIRONMENT=development" not in conteudo


def test_env_de_exemplo_declara_producao() -> None:
    conteudo = _sem_comentarios(ENV_EXEMPLO.read_text(encoding="utf-8"))
    assert "SAC_ENVIRONMENT=production" in conteudo
    assert "SAC_ENVIRONMENT=development" not in conteudo


def test_env_de_exemplo_nao_traz_segredo_preenchido() -> None:
    """O modelo existe para ser copiado: valor real aqui vaza no git. Comparacao
    por linha, e nao por substring com \\n, porque o arquivo pode ter CRLF."""
    valores = {}
    for linha in ENV_EXEMPLO.read_text(encoding="utf-8").splitlines():
        limpa = linha.strip()
        if limpa and not limpa.startswith("#") and "=" in limpa:
            chave, _, valor = limpa.partition("=")
            valores[chave.strip()] = valor.strip()
    for chave in ("SAC_JWT_SECRET", "POSTGRES_PASSWORD", "SAC_S3_SECRET_KEY"):
        assert chave in valores, f"{chave} deveria estar no modelo"
        assert valores[chave] == "", f"{chave} deveria estar vazio no modelo"


def test_gitignore_cobre_o_env_de_producao() -> None:
    """A regra `.env` do .gitignore casa apenas com o nome exato: sem uma linha
    propria, `.env.prod` -- que tem o segredo JWT e a senha do banco -- entra
    num `git add .` sem aviso nenhum."""
    linhas = GITIGNORE.read_text(encoding="utf-8").splitlines()
    assert ".env.prod" in [linha.strip() for linha in linhas]


def test_compose_de_prod_nao_publica_porta_do_banco() -> None:
    """O Postgres nao pode ficar exposto na interface publica da VPS. Em prod o
    unico acesso e pela rede interna do compose."""
    assert "5432:5432" not in _conteudo_compose()


def test_compose_de_prod_usa_o_entrypoint_de_prod() -> None:
    conteudo = _conteudo_compose()
    assert "docker-entrypoint.prod.sh" in conteudo
    assert "docker-entrypoint.sh" not in conteudo.replace("docker-entrypoint.prod.sh", "")


def test_compose_de_prod_nao_monta_o_codigo_do_host() -> None:
    """Volume de codigo e recurso de desenvolvimento: em producao o container
    tem de rodar o que esta na imagem construida, nao o que esta no disco da
    VPS."""
    assert "./backend:/app" not in _conteudo_compose()
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
cd backend
uv run pytest tests/unit/test_deploy_config.py -v
```

Esperado: os 4 testes da Task 1 passam; os 8 novos falham (`test_compose_de_prod_existe`
no `assert`, os que leem `docker-compose.prod.yml` e `.env.prod.example` com
`FileNotFoundError`, e `test_gitignore_cobre_o_env_de_producao` no `assert` porque a
regra `.env` do `.gitignore` nao cobre `.env.prod`).

- [ ] **Step 3: Criar o compose de producao**

Criar `docker-compose.prod.yml` na raiz:

```yaml
# Compose de PRODUCAO. Suba sempre com o --env-file, porque a interpolacao de
# ${POSTGRES_PASSWORD} depende dele:
#
#   docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
#
# Variavel de env_file NAO serve para interpolacao no proprio compose -- por isso
# a senha do Postgres vem do --env-file e o SAC_DATABASE_URL e montado aqui, num
# lugar so, em vez de duas copias que dessincronizam no primeiro rodizio de senha.
#
# O nome do projeto e sac-prod para que os volumes nao colidam com os do compose
# de desenvolvimento se os dois rodarem na mesma maquina.
name: sac-prod

services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: sac
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD no .env.prod}
      POSTGRES_DB: sac
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sac -d sac"]
      interval: 5s
      timeout: 3s
      retries: 30

  backend:
    build: ./backend
    command: ["sh", "docker-entrypoint.prod.sh"]
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env.prod
    environment:
      # Vence o que vier do env_file (environment tem precedencia). Nao defina
      # SAC_DATABASE_URL no .env.prod: seria ignorado em silencio.
      SAC_DATABASE_URL: postgresql+asyncpg://sac:${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD no .env.prod}@db:5432/sac
    healthcheck:
      # So fica saudavel depois que as migrations rodaram e o uvicorn subiu. O
      # worker e o web dependem desta condicao.
      test: ["CMD", "python3", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/api/health', timeout=2)"]
      interval: 10s
      timeout: 3s
      retries: 30
      start_period: 30s

  worker:
    build: ./backend
    command: ["uv", "run", "--frozen", "--no-dev", "python", "-m", "sac.worker"]
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
      backend:
        condition: service_healthy
    env_file:
      - .env.prod
    environment:
      SAC_DATABASE_URL: postgresql+asyncpg://sac:${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD no .env.prod}@db:5432/sac

  web:
    build: ./frontend
    restart: unless-stopped
    depends_on:
      # service_started, e nao service_healthy, de proposito: o nginx precisa
      # que o nome `backend` RESOLVA no carregamento da config -- com nome
      # literal em proxy_pass e sem diretiva resolver, ele se recusa a iniciar
      # com "host not found in upstream" --, e para isso basta o container
      # existir. Esperar por saude faria um backend doente derrubar tambem a
      # pagina, em vez de a SPA subir e mostrar o erro vindo da API.
      backend:
        condition: service_started
    ports:
      # Apenas no loopback: quem expoe o servico na internet e o proxy reverso
      # do host, que termina TLS e aponta para ca. Publicar em 0.0.0.0 daria
      # acesso HTTP sem TLS direto no IP da VPS.
      - "${SAC_WEB_BIND:-127.0.0.1:8080}:80"

volumes:
  pgdata:
```

- [ ] **Step 4: Criar o modelo de .env**

Criar `.env.prod.example` na raiz:

```bash
# Modelo do ambiente de PRODUCAO.
#
# Na VPS: copie para .env.prod, preencha, e restrinja o acesso:
#   cp .env.prod.example .env.prod && chmod 600 .env.prod
#
# .env.prod NUNCA entra no git. Suba sempre com:
#   docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build

# Qualquer valor diferente de "development". Nao use "development" aqui: o boot
# passaria a aceitar o segredo publico do repositorio.
SAC_ENVIRONMENT=production

# Minimo 32 caracteres. Gere com:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
# Trocar este valor invalida todas as sessoes em aberto.
SAC_JWT_SECRET=

# Senha do Postgres do compose. O SAC_DATABASE_URL e montado a partir dela pelo
# docker-compose.prod.yml -- nao defina SAC_DATABASE_URL aqui, seria ignorado.
POSTGRES_PASSWORD=

# Obrigatorio nesta topologia. Com false, todo login chega com o IP do proxy e o
# limite de 30 logins/minuto por IP vira um teto global da empresa. Exige que o
# proxy do host SOBRESCREVA X-Forwarded-For; ver docs/deploy.md.
SAC_TRUSTED_PROXY=true

# JSON, porque o campo e uma lista. Origem exata do frontend, sem barra final.
SAC_CORS_ORIGINS=["https://sac.b2pro.com.br"]

# Wasabi. O endpoint tem de ser o da regiao real do bucket, e o PUBLIC precisa
# ser o endereco que o NAVEGADOR alcanca: a assinatura cobre o header Host,
# entao trocar o host depois de assinar invalida a URL.
SAC_S3_ENDPOINT_URL=https://s3.us-east-1.wasabisys.com
SAC_S3_PUBLIC_ENDPOINT_URL=https://s3.us-east-1.wasabisys.com
SAC_S3_REGION=us-east-1
SAC_S3_BUCKET=
SAC_S3_ACCESS_KEY=
SAC_S3_SECRET_KEY=

# Onde o nginx do container escuta no host. O proxy reverso do host aponta para
# este endereco. Mantenha no loopback.
SAC_WEB_BIND=127.0.0.1:8080

# Processos do uvicorn. 2 e um ponto de partida razoavel para uma VPS pequena.
SAC_UVICORN_WORKERS=2
```

- [ ] **Step 5: Ignorar o .env.prod no git**

Fato ja verificado: `.gitignore` da raiz tem `.env`, que casa **apenas** com o nome
exato, e `git check-ignore -v .env.prod` sai com codigo 1 — ou seja, hoje o arquivo
com o segredo JWT e a senha do banco entraria num `git add .` sem aviso.

Acrescentar ao `.gitignore` da raiz, na linha imediatamente abaixo de `.env`:

```
.env.prod
```

- [ ] **Step 6: Rodar os testes e confirmar que passam**

```bash
cd backend
uv run pytest tests/unit/test_deploy_config.py -v
```

Esperado: PASS, 12 passed.

- [ ] **Step 7: Validar o compose de verdade**

```bash
cp .env.prod.example .env.prod
```

Preencher no `.env.prod` recem-criado o `SAC_JWT_SECRET` e o `POSTGRES_PASSWORD` com
valores de teste — o `config` resolve a interpolacao e o `:?` falha com valor vazio.
Depois:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml config
git check-ignore -v .env.prod
```

Esperado: o YAML resolvido sai na tela, com `SAC_DATABASE_URL` ja contendo a senha e
sem nenhum erro de variavel; e o `check-ignore` imprime uma linha apontando
`.gitignore:<n>:.env.prod`. Se o `check-ignore` nao imprimir nada, o Step 5 nao foi
aplicado — pare e aplique, porque o commit do Step 9 vazaria o arquivo.

O `config` nao constroi imagem, entao o `build: ./frontend` ainda sem `Dockerfile`
nao e problema neste passo. O `.env.prod` criado aqui fica no disco para as tasks
seguintes e e apagado na Task 5.

- [ ] **Step 8: Rodar as verificacoes locais completas**

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Esperado: tudo verde. `pytest` com timeout explicito de 600000 ms.

- [ ] **Step 9: Commit**

```bash
git add docker-compose.prod.yml .env.prod.example .gitignore backend/tests/unit/test_deploy_config.py
git status --short   # confirmar que .env.prod NAO aparece como untracked
git commit -m "Adiciona compose de producao e modelo de ambiente"
```

No `git status --short`, o `.env.prod` nao deve aparecer nem como `??`. Se aparecer, o
Step 5 nao pegou — nao commite.

---

### Task 3: Imagem do frontend com nginx servindo a SPA e roteando /api

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Create: `frontend/.dockerignore`

**Interfaces:**
- Consumes: o servico `web` com `build: ./frontend` e o hostname interno `backend:8000` (Task 2).
- Produces: uma imagem que serve a SPA na porta 80 do container, atende `/api/` por proxy para `backend:8000`, e trata `/api/notificacoes/stream` sem buffer. Nada em tasks posteriores depende de nome de arquivo interno desta imagem.

- [ ] **Step 1: Criar o .dockerignore**

Criar `frontend/.dockerignore`:

```
node_modules
dist
dist-ssr
test-results
playwright-report
e2e
playwright.config.ts
Dockerfile
.dockerignore
*.log
```

`e2e/` e `playwright.config.ts` ficam fora porque `tsc -b` nao os alcanca:
`tsconfig.app.json` inclui apenas `src` e `tsconfig.node.json` apenas
`vite.config.ts`.

`nginx.conf` **nao** entra nesta lista, de proposito: o `.dockerignore` filtra o
contexto enviado ao daemon, e o estagio final faz `COPY nginx.conf`. Ignorar o arquivo
o tiraria do contexto e o `COPY` falharia com "file not found".

- [ ] **Step 2: Criar o Dockerfile**

Criar `frontend/Dockerfile`:

```dockerfile
# Estagio de build: precisa das devDependencies (vite, typescript), por isso
# instala tudo. O projeto usa pnpm -- nao existe package-lock.json, e `npm ci`
# falharia.
FROM node:24-alpine AS build
WORKDIR /app
RUN npm install -g pnpm@9.15.0
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# Imagem final: so nginx e os arquivos estaticos. Nada de Node em producao.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

- [ ] **Step 3: Criar a configuracao do nginx**

Criar `frontend/nginx.conf`:

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # Anexo nao passa por aqui: o upload vai direto para o Wasabi por URL
    # assinada. O corpo que chega na API e pequeno (JSON).
    client_max_body_size 2m;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/css application/javascript application/json image/svg+xml;

    # SSE de notificacoes. location exato ganha do prefixo /api/, e este bloco
    # existe porque com proxy_buffering ligado o nginx segura os eventos e as
    # notificacoes simplesmente param de chegar, sem erro em lugar nenhum.
    # Connection "" impede que o header hop-by-hop do cliente feche o upstream.
    location = /api/notificacoes/stream {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1h;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        # $proxy_add_x_forwarded_for acrescenta o IP do salto anterior ao que
        # chegou. Correto AQUI porque o proxy do host sobrescreve o header com o
        # IP real do cliente, que assim continua sendo o primeiro item -- e o
        # primeiro item e o que client_ip le. Ver docs/deploy.md.
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # Bundles do Vite tem hash no nome, entao podem ser imutaveis.
    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        # add_header em location DESCARTA os add_header do server. Repetir os
        # headers de seguranca aqui e no bloco do index.html nao e redundancia:
        # sem isto eles desaparecem exatamente nas respostas que importam.
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        try_files $uri =404;
    }

    # O HTML nunca pode ficar em cache: e ele que aponta para o bundle novo
    # depois de um deploy.
    location = /index.html {
        add_header Cache-Control "no-store" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    }

    # Fallback da SPA: as rotas do react-router nao existem como arquivo.
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 4: Construir a imagem**

```bash
docker build -t sac-web-test ./frontend
```

Esperado: build conclui. Se falhar no `pnpm build` com erro de tipo, o problema e do
codigo do frontend e nao deste plano: rodar `pnpm build` local em `frontend/` para ver
o mesmo erro.

- [ ] **Step 5: Testar a imagem isolada, sem backend**

O `--add-host` nao e opcional aqui: com nome literal em `proxy_pass` e sem diretiva
`resolver`, o nginx resolve o upstream **ao carregar a config** e se recusa a iniciar
com "host not found in upstream". Fora da rede do compose o nome `backend` nao existe,
entao o container morreria no boot em vez de responder qualquer coisa. Apontar o nome
para o loopback do proprio container satisfaz a resolucao e deixa a conexao ser
recusada, que e o que este teste quer observar.

```bash
docker run --rm -d --name sac-web-test --add-host backend:127.0.0.1 -p 8099:80 sac-web-test
docker ps --filter name=sac-web-test --format '{{.Status}}'
curl -s -o /dev/null -w 'raiz: %{http_code}\n' http://localhost:8099/
curl -s -o /dev/null -w 'deep link: %{http_code}\n' http://localhost:8099/tickets
curl -s -o /dev/null -w 'api: %{http_code}\n' http://localhost:8099/api/health
curl -s -D - -o /dev/null http://localhost:8099/ | grep -i -E 'x-frame-options|cache-control'
docker rm -f sac-web-test
```

Esperado:
- `docker ps` mostra `Up ...` — se o container nao estiver de pe, ler
  `docker logs sac-web-test`: erro de sintaxe no `nginx.conf` aparece ali.
- `/` responde `200` (a SPA).
- `/tickets` responde `200` — prova o fallback da SPA; sem o `try_files` daria `404`.
- `/api/health` responde `502` — o bloco `/api/` pegou a rota e tentou o upstream, que
  recusou a conexao. `502` e o resultado correto aqui; `404` significaria que o bloco
  `/api/` nao esta pegando a rota e o `try_files` respondeu no lugar dele.
- O `grep` mostra `X-Frame-Options: DENY`.

- [ ] **Step 6: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf frontend/.dockerignore
git commit -m "Adiciona imagem do frontend com nginx servindo a SPA e a API"
```

---

### Task 4: Documento de deploy

**Files:**
- Create: `docs/deploy.md`
- Modify: `docs/armazenamento-anexos.md` (secao "Objetos orfaos", linhas 69-81, e o item 3 do checklist na linha 89)
- Modify: `CLAUDE.md` (lista de documentos de apoio)

**Interfaces:**
- Consumes: os nomes de servico e o nome de projeto do compose (Task 2), o endereco `127.0.0.1:8080` do servico `web` (Task 2) e o comportamento de `X-Forwarded-For` do nginx do container (Task 3).
- Produces: nada consumido por task posterior. A Task 5 executa o smoke test que este documento descreve.

- [ ] **Step 1: Escrever docs/deploy.md**

Criar `docs/deploy.md` com estas secoes, no conteudo indicado:

**Secao "Topologia"** — o diagrama e a explicacao de quem termina TLS:

```
internet -> proxy reverso do host (TLS, dominio)
              -> 127.0.0.1:8080  web (nginx: SPA + proxy /api)
                                   -> backend:8000 (uvicorn, sem porta publicada)
                                        -> db:5432 (sem porta publicada)
                                   worker (previews, expiracao de pendentes, orfaos)
```

**Secao "Pre-requisitos da VPS"** — Docker Engine com o plugin `compose`, git, e um
proxy reverso ja instalado (nginx ou Traefik) com certificado valido para o dominio.

**Secao "Configuracao do Wasabi"** — na ordem:

1. Criar bucket **privado**, sem acesso publico de leitura ou escrita, e anotar a regiao.
2. Criar um sub-user com chave de acesso propria (nao usar a credencial raiz da conta).
3. Aplicar a policy abaixo, que e exatamente o que o codigo usa — `GetObject` cobre
   tambem o `HEAD` da confirmacao de anexo, e `ListBucket`/`DeleteObject` existem para
   a varredura de orfaos do worker:

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

4. Aplicar o CORS do bucket. Passo obrigatorio e **nao verificavel localmente**: o
   MinIO de desenvolvimento libera CORS por padrao e nem implementa `PutBucketCors`,
   entao nenhum teste local detecta a falta da politica, e sem ela todo upload pelo
   navegador falha com um erro opaco (`xhr.onerror`, sem status). Rodar de dentro do
   container, para reaproveitar o `.env.prod`:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend \
  uv run --frozen --no-dev python -m sac.infrastructure.provision_bucket \
  --origem https://sac.b2pro.com.br

docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend \
  uv run --frozen --no-dev python -m sac.infrastructure.provision_bucket --conferir
```

Apontar para `docs/armazenamento-anexos.md` para o detalhe da politica.

**Secao "Arquivo .env.prod"** — copiar de `.env.prod.example`, `chmod 600`, e gerar o
segredo com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Deixar
explicito que trocar `SAC_JWT_SECRET` invalida todas as sessoes em aberto.

**Secao "Proxy reverso do host"** — com este bloco de nginx e o aviso que o acompanha:

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

Acrescentar a nota sobre a versao do nginx: `http2 on;` como diretiva separada exige
nginx 1.25.1 ou mais novo. Em nginx anterior a config nem carrega, e a forma correta e
`listen 443 ssl http2;` sem a linha `http2 on;`. Conferir com `nginx -v` na VPS.

Acrescentar a nota: se por algum motivo nao for possivel garantir essa sobrescrita,
deixar `SAC_TRUSTED_PROXY=false` — o limitador passa a contar por IP do proxy (teto
global de 30 logins/minuto, ruim) mas deixa de ser falsificavel. Nunca as duas coisas:
`true` com header acrescentado e o pior dos casos.

**Secao "Primeiro deploy"**:

```bash
git clone <repo> /opt/sac && cd /opt/sac
cp .env.prod.example .env.prod && chmod 600 .env.prod
# preencher .env.prod
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

Em seguida criar o super admin, uma unica vez (senha entra so neste comando, nao no
`.env.prod`; use um shell que nao guarda historico ou limpe depois):

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm \
  -e SAC_SEED_ADMIN_EMAIL=admin@b2pro.com.br \
  -e SAC_SEED_ADMIN_PASSWORD='<senha forte>' \
  backend uv run --frozen --no-dev python -m sac.infrastructure.seed
```

Esperado: `super admin criado: admin@b2pro.com.br`. Rodar de novo responde
`super admin ja existe`, sem efeito — o comando e idempotente. Use um TLD real no
email: enderecos `.local`/`.test` sao recusados pela validacao de email do login.

**Secao "Deploys seguintes"**:

```bash
cd /opt/sac && git pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

As migrations rodam no boot do `backend`, antes do uvicorn subir. Registrar que
durante o `--build` do frontend o servico fica no ar com a imagem antiga, e a troca
acontece quando o container novo sobe.

**Secao "Smoke test pos-deploy"** — a lista da Task 5 deste plano, com os comandos e
o que cada um prova.

**Secao "Backup"**:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  pg_dump -U sac -d sac --format=custom > sac-$(date +%F).dump
```

Restauracao:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  pg_restore -U sac -d sac --clean --if-exists < sac-AAAA-MM-DD.dump
```

Deixar explicito que **nao existe backup automatico**: agendar esse comando no cron da
VPS e enviar o arquivo para fora da maquina e responsabilidade de quem opera. Um dump
guardado no mesmo disco do banco nao protege contra perda do disco.

**Secao "Residuais conhecidos"** — dois itens, com o motivo:
- Sem CSP. Com token de sessao no `localStorage`, XSS le a sessao; uma CSP e a mitigacao
  certa, mas montar uma as cegas quebra a aplicacao e ela precisa de tarefa propria com
  verificacao no navegador.
- Sem backup automatizado (acima).

- [ ] **Step 2: Corrigir a secao desatualizada de docs/armazenamento-anexos.md**

O documento afirma que a mitigacao de objetos orfaos esta "pendente de decisao" e
lista duas saidas possiveis, mas a varredura no worker (a opcao 2) foi implementada:
existe `ReconcileOrphansUseCase`, `reconcile_orphans_all` em
`backend/src/sac/infrastructure/worker.py:204` e o ajuste `reconcile_orphans_hours`
em `settings.py:42`. Reescrever as linhas 69-81 e o item 3 do checklist (linha 89)
para dizer o que e verdade hoje:

- a varredura periodica do worker apaga objeto sem linha correspondente no banco;
- a margem de idade e `SAC_RECONCILE_ORPHANS_HOURS` (default 24 h), com piso 1, e
  objeto mais novo que a margem nunca e apagado, porque pode ser upload em voo;
- continua **nao** existindo regra de ciclo de vida no bucket, e aplicar `Expiration`
  nos prefixos reais apagaria anexos em uso: essa parte do documento permanece valida;
- o prefixo de staging (opcao 1) segue como alternativa nao implementada, nao mais
  como decisao pendente.

- [ ] **Step 3: Conferir os fatos do documento contra o codigo**

Reler `docs/deploy.md` inteiro com o codigo aberto e confirmar, um por um: o caminho
do health (`/api/health`), o caminho do stream (`/api/notificacoes/stream`), o nome
de cada variavel `SAC_*` contra `backend/src/sac/infrastructure/settings.py`, e o
nome do modulo de cada comando (`sac.infrastructure.seed`,
`sac.infrastructure.migrate`, `sac.infrastructure.provision_bucket`). Um nome errado
aqui vira um comando que falha no meio do primeiro deploy.

- [ ] **Step 4: Listar o documento novo no CLAUDE.md**

O `CLAUDE.md` enumera os documentos de apoio ("Apoio: `docs/planilhas.md` ...").
Acrescentar `docs/deploy.md` a essa lista, com a descricao "procedimento de deploy em
producao, configuracao do Wasabi e do proxy reverso". Documento novo que nao aparece
nessa lista deixa de ser encontrado por quem entra no projeto depois.

- [ ] **Step 5: Commit**

```bash
git add docs/deploy.md docs/armazenamento-anexos.md CLAUDE.md
git commit -m "Documenta o deploy em producao e atualiza a secao de objetos orfaos"
```

---

### Task 5: Smoke test local do stack de producao

**Files:**
- Nenhum arquivo novo. Esta task valida o conjunto e corrige o que aparecer.

**Interfaces:**
- Consumes: todos os arquivos das tasks 1 a 4.
- Produces: a confirmacao de que o stack de producao sobe de ponta a ponta, ou correcoes nos arquivos anteriores.

- [ ] **Step 1: Preparar um .env.prod de teste**

A Task 2 (Step 7) ja criou um `.env.prod` na raiz com `SAC_JWT_SECRET` e
`POSTGRES_PASSWORD` de teste. Se ele nao existir mais:

```bash
cp .env.prod.example .env.prod
```

Garantir que esta preenchido: `SAC_JWT_SECRET` com
`python -c "import secrets; print(secrets.token_urlsafe(48))"`,
`POSTGRES_PASSWORD` com qualquer valor, `SAC_S3_BUCKET`/`SAC_S3_ACCESS_KEY`/
`SAC_S3_SECRET_KEY` com valores de fachada. Sem tenant cadastrado o worker nao faz
chamada nenhuma ao S3, entao credencial invalida nao impede o smoke test — e por isso
o caminho do Wasabi so e verificavel no deploy real.

- [ ] **Step 2: Subir o stack**

Antes, derrubar o compose de desenvolvimento se ele estiver rodando:

```bash
docker compose ps            # se listar servico de pe, derrubar (sem -v)
docker compose down
```

Isso importa por dois motivos: o dev ocupa a porta 8000 do host, e o Step 3 usa
justamente a ausencia de resposta na 8000 como prova de que o backend de producao nao
esta exposto. Use `down` sem `-v` para nao apagar o banco de desenvolvimento.

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

Esperado: `db` e `backend` em `healthy`, `worker` e `web` em `running`. Se o `backend`
ficar `unhealthy`, ver `logs backend` — a causa mais provavel e `SAC_JWT_SECRET`
vazio ou curto, e a mensagem de `ensure_boot_secrets` diz qual dos dois.

- [ ] **Step 3: Verificar cada afirmacao do design**

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

Esperado, em ordem: `200`; `200`; `200` com corpo JSON de health; falha de conexao
(codigo `000` — nada escutando na 8000 do host); saida vazia ou erro do `port` (porta
nao publicada); a listagem com as tabelas globais (`users`, `tenants`, `user_tenants`);
a linha do loop do worker; e nas linhas do uvicorn nenhuma mencao a reload, com mais
de um processo iniciado.

- [ ] **Step 4: Criar o super admin pelo caminho documentado**

Rodar o comando de seed da secao "Primeiro deploy" de `docs/deploy.md`, com email de
TLD real e senha de teste. Esperado: `super admin criado: ...`. Rodar de novo e
esperar `super admin ja existe: ...`. Isso valida o comando exatamente como esta
escrito no documento — que e o ponto do passo.

- [ ] **Step 5: Corrigir o que falhou**

Qualquer divergencia entre o esperado e o observado se conserta nos arquivos das tasks
1 a 4, com um commit por correcao e mensagem que diga o que o smoke test pegou. Se
nada falhou, nao ha commit neste passo.

- [ ] **Step 6: Derrubar o stack e limpar**

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml down -v
rm .env.prod
docker rmi sac-web-test
```

O `-v` apaga o volume `sac-prod_pgdata` do teste. O nome do projeto `sac-prod` e o que
garante que isso nao toca o banco de desenvolvimento; conferir com `docker volume ls`
antes, se houver duvida.

- [ ] **Step 7: Verificacao final e relatorio**

```bash
cd backend
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd .. && git status --short
```

Esperado: verificacoes verdes e `git status` limpo (sem `.env.prod` residual).
