# Residuais da Fase 3 — plano de execucao

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar os itens que a revisao da Fase 3 classificou como deferiveis — nenhum bloqueava o merge, mas todos sao trabalho real e ja identificado.

**Origem:** achados do review final da branch `fase-3-visibilidade` (mergeada em 2026-07-31, commits `73e7bd0..57d5e1a`) e das revisoes por task. Cada item abaixo tem arquivo e motivo; nada aqui e especulacao.

**Estado do codigo:** Fase 3 entregue na `main`. Nenhum destes itens depende dos outros — podem ser feitos em qualquer ordem e em commits separados.

## Global Constraints

- PROIBIDO usar emojis em codigo, comentarios, commits, UI e documentacao.
- Clean Architecture no backend; TDD (teste antes da implementacao).
- Antes de CADA commit de backend (em `backend/`): `ruff check .`, `ruff format --check .`, `mypy` (**sem path** — `mypy .` da erro falso em `migrations/tenant/env.py`), `pytest`.
- Antes de CADA commit de frontend (em `frontend/`): `pnpm build` e `pnpm lint`. Gerenciador e **pnpm**.
- Nunca rodar verificacoes em background — ficam orfas; sempre foreground.
- Copy de UI em portugues sem acentos; nunca hex solto no front (existe tema escuro).
- Ambiente: `docker compose up -d` na raiz. E2E exige `E2E_PORT` (a 5173 e disputada por outro projeto) e o container `copilot-postgres` precisa estar parado (briga pela 5432).

## Ordem recomendada

Os itens 1 e 2 sao os de maior retorno (performance real e o unico com migration). O 8 e o unico que mexe em acessibilidade e conflita com o contrato de componentes — leia a nota antes. Os demais sao independentes.

---

### Task 1: Indices no schema do tenant

**Files:** `backend/src/sac/infrastructure/models_tenant.py`; nova migration em `backend/migrations/tenant/versions/`; teste em `backend/tests/integration/test_tenant_schema.py`

Hoje o schema de tenant nao tem **nenhum** indice alem de PK/unique/FK, e o Postgres nao indexa FK automaticamente. As queries da Fase 3 filtram e ordenam por colunas sem indice.

Colunas que as queries novas usam (conferir contra `repositories_reporting.py` antes de decidir a lista final):
- `tickets`: `status`, `brand_id`, `opened_at`, `due_at`, `approved_at`, `declined_at`, `closed_at`, `attendant_user_id`, `deleted_at`
- `ticket_items`: `ticket_id` (usado em todo `EXISTS` e nos rankings)
- `ticket_attachments`: `created_at`, `ticket_id`, `status`

- [ ] **Step 1:** medir antes — rodar `EXPLAIN ANALYZE` das queries do dashboard e do relatorio no tenant `e2e` (687 tickets) e anotar os planos no report. Sem medida antes, nao ha como saber se o indice ajudou.
- [ ] **Step 2:** declarar os indices nos models (`Index(...)` em `__table_args__`), escolhendo compostos onde o filtro e sempre conjunto (ex.: `(deleted_at, status)`) em vez de um indice por coluna.
- [ ] **Step 3:** gerar a migration de tenant com Alembic e conferir que ela roda em todos os schemas (o projeto tem duas arvores de migracao; ver `docs` e `infrastructure/migrate.py`).
- [ ] **Step 4:** medir depois, comparar os planos, e registrar no report o que mudou.
- [ ] **Step 5:** verificacoes e commit.

### Task 2: Dashboard em menos idas ao banco

**Files:** `backend/src/sac/infrastructure/repositories_reporting.py`; teste ja existente `backend/tests/integration/test_repositories_reporting.py`

`SqlReportingRepository.dashboard()` faz sete `SELECT count(*)` sequenciais (um por KPI), mais a distribuicao por status, tres rankings, a media e a lista de recentes — treze idas ao banco por request. As sete contagens colapsam em **uma** query com `count(*) FILTER (WHERE ...)` por KPI sobre uma unica varredura.

- [ ] **Step 1:** os testes de dashboard existentes ja cobrem os sete KPIs e os filtros dos cards — rode-os primeiro e confirme verdes, eles sao a rede de seguranca desta refatoracao.
- [ ] **Step 2:** trocar as sete contagens por um `select` unico com `func.count().filter(...)` por KPI, preservando exatamente as chaves e os dicts de filtro que os testes ja asseguram.
- [ ] **Step 3:** rodar os testes de novo — devem passar sem alteracao nenhuma. Se algum precisar mudar, a refatoracao mudou comportamento e esta errada.
- [ ] **Step 4:** verificacoes e commit.

### Task 3: Code splitting do grafico

**Files:** `frontend/src/pages/dashboard/DashboardPage.tsx`

O build avisa que um chunk passou de 500kB, porque o Recharts entrou nesta fase e vai no bundle principal — inclusive para Relatorios e Midias, que nao desenham grafico nenhum.

- [ ] **Step 1:** envolver `StatusDistributionChart` em `React.lazy` + `Suspense` dentro do card do grafico, com um fallback do mesmo tamanho do grafico (reusar o `Skeleton` compartilhado) para nao dar salto de layout.
- [ ] **Step 2:** `pnpm build` e comparar o tamanho dos chunks antes e depois; anotar no report.
- [ ] **Step 3:** conferir na tela que o grafico aparece normalmente e que o fallback nao pisca de forma incomoda.
- [ ] **Step 4:** commit.

### Task 4: Validar periodo invertido com 422

**Files:** `backend/src/sac/interface/routers/reporting.py`; teste em `backend/tests/integration/test_reporting_api.py`

A spec (secao 4) diz que `de > ate` responde 422. Hoje `_report_filters` nao faz validacao entre campos — FastAPI nao infere isso — e a consulta simplesmente devolve vazio, que o usuario le como "nao ha dados" em vez de "o periodo esta invertido".

- [ ] **Step 1:** teste esperando 422 para `?de=2026-08-01&ate=2026-07-01` em `/api/relatorios` **e** em `/api/relatorios/export` (a dependency e compartilhada, entao um so lugar para corrigir, mas os dois precisam de cobertura).
- [ ] **Step 2:** validar dentro de `_report_filters`, levantando o erro no padrao que o projeto ja usa para 422 (ver `interface/errors.py` e como `ValidationError` do dominio e traduzido).
- [ ] **Step 3:** rodar, verificacoes e commit.

### Task 5: Resolver o nome do produto pelo id

**Files:** `frontend/src/pages/relatorios/RelatoriosPage.tsx`, `frontend/src/pages/tickets/TicketsListPage.tsx`; talvez `frontend/src/lib/cadastros.ts`

`product_id` vive na URL, mas o texto do autocomplete vive em estado local. Ao abrir um link compartilhado o filtro esta ativo e **invisivel**: em Relatorios o chip cai no rotulo generico "Produto selecionado", e na lista de tickets nao aparece nada. Quem recebe o link ve resultados filtrados sem saber por que.

- [ ] **Step 1:** conferir se existe endpoint de produto por id; se nao existir, a alternativa mais barata e buscar pela listagem de produtos filtrando pelo id (ver `lib/cadastros.ts`) — decidir e registrar a escolha no report.
- [ ] **Step 2:** ao montar a tela com `product_id` na URL e sem rotulo em estado, resolver o nome e preencher o campo do autocomplete e o chip.
- [ ] **Step 3:** conferir os dois casos na tela: link com `product_id` valido (mostra o nome) e com id inexistente (nao quebra; degrada para o rotulo generico).
- [ ] **Step 4:** commit.

### Task 6: Ordem de insercao dos itens do ticket

**Files:** `backend/src/sac/infrastructure/models_tenant.py`; migration de tenant; `backend/src/sac/infrastructure/repositories_tickets.py`, `repositories_reporting.py`

`ticket_items.created_at` usa `server_default=func.now()`, que em Postgres e `transaction_timestamp()` — todos os itens inseridos na mesma transacao empatam. "Primeiro produto do ticket" e hoje estabilizado apenas por evitar um JOIN (feito em `report()` e `export_rows()`), o que reduz mas nao elimina a indeterminacao. `SqlTicketRepository.list()` ainda tem o padrao original.

- [ ] **Step 1:** teste que insere dois itens no mesmo flush e exige um "primeiro produto" estavel em varias execucoes (o teste precisa falhar de forma confiavel antes da correcao — se nao falhar, documente isso no report em vez de fingir um red).
- [ ] **Step 2:** adicionar uma coluna de ordinal por ticket (ou um `Identity`/sequence) em `ticket_items`, com migration que preenche as linhas existentes de forma deterministica.
- [ ] **Step 3:** ordenar por ela nos tres lugares e remover os contornos que existiam so por causa do empate.
- [ ] **Step 4:** verificacoes e commit.

### Task 7: Polimento de fidelidade ao mockup

**Files:** `frontend/src/components/reporting/KpiCard.tsx`, `StatusDistributionChart.tsx`, `FiltersCard.tsx`, `frontend/src/components/media/MediaTile.tsx`, `frontend/src/pages/dashboard/DashboardPage.tsx`, `frontend/src/pages/midias/MidiasPage.tsx`, `frontend/src/lib/format.ts`

Itens pequenos e independentes; podem ir num commit so.

- [ ] **`KpiCard` sem tooltip:** o mockup mostra um `title` por card ("Ver todos os tickets", "Tickets com SLA vencido"...). Adicionar uma prop opcional e passar do Dashboard.
- [ ] **Teto do eixo do grafico:** `StatusDistributionChart.tsx:49` usa `domain={[0, "dataMax"]}`, entao a barra maior encosta na borda. `Componentes.md` pede teto arredondado acima do maximo.
- [ ] **`MediaTile` sem `onError`:** se a URL assinada expirar enquanto o usuario rola, o tile mostra icone de imagem quebrada em vez do placeholder por tipo que ja existe. Tratar `onError` caindo no placeholder.
- [ ] **Copy do empty state do dashboard:** diz "Nenhum ticket registrado neste tenant" mesmo quando o tenant tem tickets e apenas a marca filtrada nao tem. Diferenciar as duas frases.
- [ ] **Filtro de marca do dashboard fora da URL:** e o unico filtro das telas novas em estado de componente, entao nao e compartilhavel e se perde ao voltar. Mover para a URL com o mesmo padrao `setParam` das outras telas.
- [ ] **Midias manda limpar filtros sem ter como:** o empty state diz "limpe os filtros", mas a tela nao tem botao Limpar nem chips. Ou adicionar a afordancia, ou reescrever a frase.
- [ ] **`FiltersCard` com grid fixo:** hardcoda `minmax(190px,1fr)`; Midias foi especificada com 170px. Aceitar um `minWidth` opcional.
- [ ] **`formatDuration` com horas negativas:** `d`/`h` herdam o sinal, entao `-1` viraria "-1h" em vez de "-1d 23h". Hoje inalcancavel (`slaRemaining` sempre passa `Math.abs`), mas o helper e publico e compartilhado.
- [ ] Verificacoes e commit.

### Task 8: Acessibilidade da linha clicavel

**Files:** `frontend/src/components/reporting/TicketRow.tsx` (e os consumidores em Dashboard e Relatorios)

`TicketRow` poe `role="link"` no `<tr>`, o que remove a linha da arvore de acessibilidade da tabela — leitor de tela perde a semantica de linha e coluna na tabela inteira de resultados.

**Nota antes de comecar:** isso e o que `docs/frontendmockups/Componentes.md` prescreve, entao a mudanca contraria o contrato de componentes aprovado. A alternativa tecnica e um link real na primeira celula mais um handler de clique na linha, o que preserva o comportamento de mouse sem quebrar a tabela. **Confirme a abordagem com o usuario antes de implementar** — e uma decisao de design, nao so de codigo.

- [ ] **Step 1:** confirmar a abordagem com o usuario.
- [ ] **Step 2:** implementar preservando: clique em qualquer lugar da linha navega, Enter e Espaco funcionam, foco visivel, e as duas tabelas (Dashboard e Relatorios) continuam iguais visualmente.
- [ ] **Step 3:** ajustar os e2e que dependem do seletor de linha (`e2e/06-visibilidade.spec.ts` usa `table tbody tr` justamente porque `role="link"` quebrou `getByRole("row")` — se a semantica voltar, o seletor pode voltar a ser o idiomatico).
- [ ] **Step 4:** commit.

### Task 9: Correcoes de documentacao e limpeza

**Files:** `docs/superpowers/specs/2026-07-30-sac-b2pro-fase-3-visibilidade-design.md`, `docs/frontendmockups/Componentes.md`, `frontend/src/components/reporting/StatusDistributionChart.tsx`, `frontend/eslint.config.js`, `backend/src/sac/infrastructure/repositories_tickets.py`

- [ ] **Frase do CSV desatualizada:** a spec (linha 39) afirma que o export e gerado em chunks "para nao materializar tudo em memoria", mas a implementacao materializa de proposito (a sessao do tenant pode fechar antes do generator drenar — o plano autorizou). Corrigir a frase para descrever o que o codigo faz e por que.
- [ ] **Conflito de ticks:** `Componentes.md` (linha 18) pede 4 ticks no eixo X e a spec (linha 64) diz 5; o codigo usa 5. Alinhar os dois documentos.
- [ ] **`STATUS_CHART_FILL` em modulo proprio:** hoje e exportado do arquivo do componente, o que exigiu um override em `eslint.config.js` para `src/components/reporting/**`. Mover a constante para um modulo de constantes e remover o override, deixando a regra estrita de novo.
- [ ] **`_ticket_entity` importado como privado:** `repositories_reporting.py` importa `_ticket_entity` de `repositories_tickets.py`. Na mesma fase o irmao `_entity` foi promovido para `attachment_entity`; fazer o mesmo aqui, por consistencia.
- [ ] **Assercao de rede no e2e:** o teste "relatorio exige filtro" checa o empty state, nao a ausencia de requisicao. Reforcar com `page.route`/contador de requests para provar que a query esta realmente barrada.
- [ ] Verificacoes e commit.

---

### Task 10 (opcional, descoberto em 2026-07-31): dica de login em desenvolvimento

**Files:** `backend/src/sac/application/use_cases/auth.py` ou `backend/src/sac/interface/routers/auth.py`

O login devolve a mesma mensagem ("credenciais invalidas") tanto para senha errada quanto para usuario sem vinculo com o tenant informado. Isso e **correto em producao** — nao revela se o e-mail existe — mas em desenvolvimento custa tempo de diagnostico real (aconteceu nesta sessao).

Se implementar: a distincao so pode aparecer quando um sinal explicito de ambiente de desenvolvimento estiver ligado, nunca por padrao, e a mensagem de producao nao muda. Se isso parecer risco desnecessario, a alternativa e nao fazer nada — o item existe so para nao esquecer o incomodo.
