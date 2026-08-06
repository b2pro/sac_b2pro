# SAC-B2PRO

Plataforma de SAC para automatizar o controle de trocas, defeitos e garantias hoje feito em planilhas (marcas KODI e STALEKS), com backend limpo e testado e front que evolui o layout do sistema legado.

## Stack

- **Backend**: Python 3.12+, FastAPI, Uvicorn, SQLAlchemy (async), Alembic, PostgreSQL. Clean Architecture (domain / application / infrastructure / interface). Multi-tenant por schema, autenticação por email + senha + slug do tenant (JWT).
- **Frontend**: React + TypeScript + Vite.

## Pré-requisitos

- Docker (para o PostgreSQL, o MinIO e os containers de backend/worker do `docker-compose.yml`)
- [uv](https://docs.astral.sh/uv/) (gerenciador de ambiente/pacotes do backend)
- Node.js 20+
- pnpm

## Quickstart

### Um comando (recomendado para dev)

```powershell
./dev.ps1
```

O script builda e sobe Postgres, MinIO (mais o job `minio-init`, que cria o bucket), o
backend e o `worker` em containers (migrations e seed rodam automaticamente no backend;
hot-reload ativo via volume montado em backend e worker) e depois inicia o frontend com
`pnpm dev` no terminal atual. Super admin de dev: `admin@b2pro.com` / `admin-dev-12345`
(deixe o slug vazio no login). Para parar os containers depois: `docker compose down`. As
credenciais podem ser sobrescritas pelas variáveis de ambiente `SAC_SEED_ADMIN_EMAIL` e
`SAC_SEED_ADMIN_PASSWORD` antes de rodar o script.

O `worker` roda `python -m sac.worker`: drena a fila de geração de previews (imagem do
anexo de ticket e foto de produto) e depende do `backend` estar saudável, já que é o
backend quem roda as migrations. O MinIO expõe a API S3 em `http://localhost:9000` e o
console em `http://localhost:9001` (usuário `sacminio`, senha `sacminio123`, bucket
`sac-dev`, criado automaticamente pelo `minio-init`).

### Passo a passo manual

Suba a infraestrutura (Postgres e MinIO, com o bucket já criado):

```bash
docker compose up -d db minio minio-init
```

Backend:

```bash
cd backend
cp .env.example .env   # preencher SAC_SEED_ADMIN_EMAIL e SAC_SEED_ADMIN_PASSWORD
uv run python -m sac.infrastructure.migrate all
uv run python -m sac.infrastructure.seed
uv run uvicorn sac.main:app --reload
```

Worker de previews (em outro terminal, para os anexos ganharem thumbnail):

```bash
cd backend
uv run python -m sac.worker
```

Frontend (em outro terminal):

```bash
cd frontend
pnpm install
pnpm dev
```

O backend sobe em `http://localhost:8000` (docs em `/docs`) e o frontend em `http://localhost:5173`.

## Verificações locais

Não há CI: as verificações abaixo devem passar localmente antes de cada commit.

Backend (em `backend/`):

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest
```

Frontend (em `frontend/`):

```bash
pnpm lint
pnpm build
```

Os testes de integração do backend (`uv run pytest`, em `tests/integration/`) batem em
Postgres e MinIO de verdade — exigem `docker compose up -d db minio minio-init` de pé
antes de rodar.

### Passeio end-to-end (Playwright)

Cobre os fluxos de ticket na UI real: login, fila repaginada (busca livre com debounce,
chips de atalho com contagem e cards de duas linhas, incluindo o card inteiro como link
navegável), criação completa com cliente inline, máquina de estados até finalizado,
declínio com motivo, ticket parcial completado pelo detalhe, comentários com resposta,
ciclo de não lido, os escopos de atendente e visualizador, e os anexos de ticket (upload
pelo dropzone com espera do preview assíncrono gerado pelo worker, recusa de tipo/tamanho
inválido e remoção) incluindo a foto de produto (exclusão sempre atrás de confirmação e
progresso de upload isolado por produto).

```bash
cd frontend
pnpm exec playwright install chromium   # apenas na primeira vez
pnpm e2e
```

Exige o Postgres, o MinIO, o backend e o `worker` de pé (`docker compose up -d db minio
minio-init backend worker`); o Vite sobe sozinho. Sem o `worker` rodando, o teste que
espera o preview do anexo estourar o timeout e falhar — é esperado, prova que a espera é
real. Os testes usam o tenant `e2e` com quatro usuários (`e2e-admin@`,
`e2e-supervisor@`, `e2e-atendente@` e `e2e-viewer@b2pro.com`, senha
`senha-e2e-12345`) — recrie-os pelo painel da plataforma se o banco de dev for
descartado. O login do backend limita 5 tentativas por minuto por IP e tenant, por
isso a suíte autentica cada usuário uma única vez e reaproveita a sessão.

## Fases entregues

- **Fase 0 — Fundação**: monorepo, Clean Architecture, Alembic multi-schema, autenticação (login com slug + JWT), sistema de módulos por tenant, painel mínimo da plataforma.
- **Fase 1 — Cadastros**: marcas, clientes, produtos, defeitos, soluções e canais, com CRUDs no front e design system inicial.
- **Fase 2A — Tickets (core)**: núcleo do fluxo de trocas/defeitos/garantia.
  - **Domínio**: máquina de estados explícita com um use case por transição (9 transições — enviar para análise, aprovar, declinar, aguardar cliente, retomar, produto recebido, finalizar, cancelar, reabrir), cada uma com permissão, guards e marcos próprios.
  - **Numeração**: sequence nativa por schema de tenant, sem race condition entre criações concorrentes.
  - **Itens**: `TicketItem` (produto + defeito + quantidade) como fonte única de verdade — nenhum dado de produto/defeito duplicado no ticket.
  - **SLA**: `sla_policies` por tenant (semeada com urgente/alta/média/baixa e alerta antes do vencimento), prazo calculado na criação e recalculado na troca de prioridade.
  - **Colaboração**: comentários internos com reply (bloqueados em ticket encerrado), timeline de auditoria (transições, itens, reversos, garantia, edições) e lido/não lido por usuário.
  - **Logística**: códigos reversos (registrar/excluir, com retorno automático de status) e pedido de garantia (código + rastreio).
  - **API**: rotas sob `/api/tickets` (CRUD, itens, transições, reversos, garantia, comentários, marcar não lido).
  - **Frontend**: lista com filtros e debounce, indicador de não lido e paginação; detalhe em duas colunas (2/3 dados + chat + timeline, 1/3 ação primária contextual por estado com trilha de status); criação com lookup de cliente por documento/CEP e itens repetíveis.
  - Anexos (Wasabi S3) ficam para a Fase 2B — o detalhe já reserva o espaço com um card placeholder desabilitado.
- **Fase 2B — Anexos, previews e membros**: anexos de ticket com upload direto por presigned URL (imagem, PDF e vídeo até 50 MB, 10 por ticket), compressão de imagem e captura da thumb de vídeo no navegador, previews WebP (thumb 400px e média 1200px) gerados por worker assíncrono com fila em tabela (`preview_jobs`) e retry com backoff, soft delete preservando o objeto no storage para auditoria, foto de catálogo do produto (mesmo pipeline de upload e preview) e endpoint de membros do tenant com seletor de supervisor no ticket. A galeria de mídias (visualização agrupada de todos os anexos do tenant) fica para a Fase 3.
  - **Antes do primeiro deploy em produção** aplique o checklist de bucket de `docs/armazenamento-anexos.md`. O CORS sai por script — `cd backend && python -m sac.infrastructure.provision_bucket --origem https://sac.b2pro.com.br` — porque sem a política o upload direto pelo navegador falha no Wasabi com um erro opaco. Objetos órfãos já têm solução implementada (varredura periódica do worker, configurável por `SAC_RECONCILE_ORPHANS_HOURS`; **não** existe regra de ciclo de vida que resolva isso com o layout de chaves atual). Resta o bucket privado. O MinIO de desenvolvimento é permissivo justamente onde o Wasabi não é, então nenhuma verificação local cobre esses pontos.
- **Fase 3 — Visibilidade**: dashboard como rota inicial, com KPI cards clicaveis que pre-filtram a lista, grafico de distribuicao por status (Recharts), rankings top 5 e tempo medio de resolucao, tudo com filtro por marca; relatorios com card de filtros de 9 campos, chips de filtros ativos, KPIs do recorte, rankings, tabela paginada com linhas navegaveis e export CSV com exatamente os mesmos filtros da tela (a tela exige um filtro antes de consultar); galeria de midias do tenant com filtros, scroll infinito e lightbox compartilhado com o detalhe do ticket. Layout implementado a partir dos mockups aprovados em `docs/frontendmockups/`. O importador das planilhas KODI/STALEKS saiu do escopo por decisao de produto (2026-07-30).
- **Fase 3B — Fila de tickets repaginada**: a lista de tickets trocou a tabela e o card de filtros por um layout de fila: filtros no header (busca livre com debounce sobre numero/cliente/produto/pedido, selects compactos de Status/Marca/Atendente, ordenacao) e chips de atalho com contagem (Todos, Abertos, Aguardando analise, Atrasados, Nao lidos, Meus tickets — o chip ativo (ou nenhum) e derivado da URL) acima de cards de duas linhas (numero, cliente, status, prioridade e SLA na primeira; produto, itens, atendente e datas na segunda), mantendo a ordenacao da Fase 2A. Backend: `GET /api/tickets` ganhou os filtros `atendente_id`, `q` (busca livre por numero/cliente/produto/pedido) e `unread`; `GET /api/tickets/contadores` devolve todos os contadores da fila numa unica varredura, com escopo por papel (atendente ve so os proprios). A busca livre depende dos indices GIN de trigram criados nas migrations `public/0003_pg_trgm` (extensao `pg_trgm`) e `tenant/0008_indices_busca` (indices em `customers.name`, `products.name` e `tickets.order_code`) — decisao de usar trigram em vez de Seq Scan documentada, com a massa de teste reproduzivel, em `docs/medicao-indices-tenant.md`. Design e mockup em `docs/superpowers/specs/2026-07-30-sac-b2pro-fase-3b-fila-tickets-design.md` e `docs/frontendmockups/Tickets.dc.html`.

## Documentação

- `docs/PRD.md` — fonte de verdade de requisitos, domínio e fases do produto.
- `docs/superpowers/specs/2026-07-27-sac-b2pro-fase-0-design.md` — design técnico da Fase 0.
- `docs/superpowers/plans/2026-07-27-fase-0-fundacao.md` — plano de implementação da Fase 0.
- `docs/superpowers/specs/2026-07-28-sac-b2pro-fase-1-design.md` — design técnico da Fase 1 (cadastros).
- `docs/superpowers/plans/2026-07-28-fase-1-cadastros.md` — plano de implementação da Fase 1.
- `docs/superpowers/specs/2026-07-28-sac-b2pro-fase-2a-tickets-design.md` — design técnico da Fase 2A (tickets).
- `docs/superpowers/plans/2026-07-28-fase-2a-tickets.md` — plano de implementação da Fase 2A.
- `docs/superpowers/specs/2026-07-28-sac-b2pro-fase-2b-anexos-design.md` — design técnico da Fase 2B (anexos, previews e membros).
- `docs/superpowers/plans/2026-07-28-fase-2b-anexos.md` — plano de implementação da Fase 2B.
- `docs/superpowers/specs/2026-07-30-sac-b2pro-fase-3-visibilidade-design.md` — design técnico da Fase 3 (visibilidade: dashboard, relatórios e galeria de mídias).
- `docs/superpowers/plans/2026-07-30-fase-3-visibilidade.md` — plano de implementação da Fase 3.
- `docs/frontendmockups/Componentes.md` — inventário dos componentes de UI compartilhados usados nos mockups aprovados da Fase 3.
- `docs/prompt-design-fase-3.md` — prompt de design usado para gerar os mockups da Fase 3.
- `docs/superpowers/specs/2026-07-30-sac-b2pro-fase-3b-fila-tickets-design.md` — design tecnico da Fase 3B (fila de tickets repaginada: filtros no header, chips com contagem e busca livre).
- `docs/superpowers/plans/2026-07-30-fase-3b-fila-tickets.md` — plano de implementacao da Fase 3B.
- `docs/frontendmockups/Tickets.dc.html` — mockup aprovado da fila repaginada.
- `docs/medicao-indices-tenant.md` — medicao em escala (massa reproduzivel) que justificou os indices trigram (GIN) da busca livre de tickets.
- `docs/armazenamento-anexos.md` — desenho do armazenamento de anexos (Wasabi/S3, presigned URLs, previews) e o **checklist de bucket antes do primeiro deploy em produção** (CORS por script, bucket privado, objetos órfãos).
- `docs/deploy.md` — procedimento de deploy em produção numa VPS: topologia, proxy reverso do host, primeiro deploy, deploys seguintes, smoke test e backup.
- `docs/identidade-visual.md` — identidade visual do frontend.
- `CLAUDE.md` — decisões de arquitetura e regras obrigatórias do projeto.
