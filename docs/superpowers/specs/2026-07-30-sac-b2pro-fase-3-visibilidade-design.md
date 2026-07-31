# Design — SAC-B2PRO Fase 3 (Visibilidade: dashboard, relatorios e galeria de midias)

Data: 2026-07-30. Status: aprovado pelo usuario em 2026-07-30 (secoes revisadas uma a uma). Fontes: `docs/PRD.md` (secoes 6.2, 6.7, 6.8 e fase 3), `docs/legado-ui.md`, `docs/legado-funcionamento.md`, designs das Fases 2A e 2B.

## Objetivo

Dar visao consolidada da operacao sobre os dados que as Fases 1 e 2 ja produzem: dashboard com KPIs clicaveis e graficos, relatorios com filtros completos e export CSV fiel a tela, e galeria de midias do tenant consumindo os previews da Fase 2B. Nenhuma rota de escrita nesta fase.

**Importador das planilhas KODI/STALEKS foi cancelado pelo usuario em 2026-07-30** e sai do escopo da fase (o PRD ainda o lista na fase 3; esta decisao prevalece). Fora de escopo tambem: notificacoes, busca global e preferencias (Fase 4).

## Decisoes fechadas com o usuario (2026-07-30)

1. **Fase unica** — um spec e um plano para as tres entregas; volume comparavel a Fase 2A e as entregas compartilham as mesmas queries de agregacao.
2. **Sem importador** — cancelado; se voltar um dia, sera fase propria.
3. **Read model por SQL de agregacao, sem tabelas novas** — queries `GROUP BY`/`COUNT`/`AVG` ao vivo no Postgres. Alternativas descartadas: tabelas de estatisticas mantidas por eventos (complexidade de consistencia/backfill injustificavel no volume atual — centenas de tickets) e agregacao no frontend (quebra com paginacao e inviabiliza o export). Se um dia doer, a primeira medida e indice, nao tabela de stats.

## Abordagem geral

Tres routers somente leitura seguindo o padrao atual (router -> use case -> port -> repositorio): `/api/dashboard`, `/api/relatorios` (+ `/export`) e `/api/midias`. Ports de leitura em `application/ports_reporting.py`, use cases finos em `application/use_cases/reporting.py`, queries de agregacao no repositorio SQLAlchemy, geracao de CSV na infrastructure (o use case devolve linhas; o router monta o `StreamingResponse`). No front, tres paginas novas com graficos em Recharts.

## 1. API

### `GET /api/dashboard`

Query param opcional: `brand_id` (aplica a todos os numeros). Resposta:

- `kpis`: `total`, `abertos`, `aguardando_analise`, `atrasados`, `aprovados_no_mes`, `declinados_no_mes`, `finalizados_no_mes` — cada um com a contagem e os query params correspondentes para o card clicavel pre-filtrar a lista.
- `distribuicao_por_status`: contagem por cada um dos 9 status.
- `rankings`: top 5 `produtos`, `defeitos` e `solucoes` (`id`, `nome`, `contagem`).
- `tempo_medio_resolucao_horas`: `float | null`.
- `recentes`: ultimos 10 tickets pelo shape da lista existente.

### `GET /api/relatorios`

Filtros: `de`/`ate` (periodo por `opened_at`), `brand_id`, `product_id`, `defect_type_id`, `solution_type_id`, `status`, `atendente_id`, `channel_id`; paginacao padrao do projeto. Resposta: `kpis` (`total`, `finalizados`, `declinados`, `tempo_medio_resolucao_horas`), `rankings` (mesmo shape do dashboard) e `tickets` paginados (shape da lista). KPIs, rankings e tabela respeitam exatamente o mesmo recorte.

### `GET /api/relatorios/export`

Mesmos query params (sem paginacao), mesma query do relatorio — tela e arquivo nunca divergem (defeito conhecido do legado, onde o CSV aplicava menos filtros que a tela). Resposta `text/csv` em streaming: UTF-8 com BOM (abre correto no Excel), separador virgula, colunas da tabela da tela mais dados do cliente (nome, documento, telefone, e-mail). Buscado em chunks paginados do repositorio (500 linhas por pagina), mas o handler materializa todos os chunks numa lista antes de abrir o `StreamingResponse`: a sessao do tenant (dependency with-yield) fecha no retorno do handler, entao um generator ainda nao drenado quebraria ao tentar usar a sessao ja fora de escopo. O streaming resultante economiza memoria de payload HTTP (o corpo vai em pedacos, nao inteiro), mas nao de memoria de processo — o relatorio inteiro fica em lista antes do primeiro byte sair.

### `GET /api/midias`

Galeria paginada sobre `ticket_attachments` com `status = disponivel` e `deleted_at IS NULL`. Filtros via join com o ticket: `kind` (imagem/pdf/video), `brand_id`, `product_id`, `defect_type_id`, `solution_type_id`, `status` do ticket, `de`/`ate` (por `created_at` do anexo). Ordenacao: `created_at` desc. Cada item: `id`, `ticket_id`, `ticket_numero`, `filename`, `kind`, `content_type`, `size_bytes`, `created_at`, `preview_url` (presigned GET da thumb, `null` quando preview pendente/falhou/inexistente — front mostra placeholder por tipo, tratamento que a 2B ja tem).

## 2. Regras das queries e casos de borda

- **Encerrado** = `finalizado`, `declinado` ou `cancelado`.
- **Atrasados**: `due_at < agora` e nao encerrado (mesma regra de `sla_state` do dominio).
- **No mes**: pelo marco correspondente (`approved_at`, `declined_at`, `closed_at`) dentro do mes civil corrente em UTC (convencao de datas do sistema). Ticket aprovado em junho e finalizado em julho conta em aprovados de junho e finalizados de julho.
- **Tempo medio de resolucao**: media de `closed_at - opened_at` **somente dos finalizados** (declinado/cancelado nao e resolucao). Sem finalizados no recorte: `null` (front mostra travessao).
- **Rankings**: produtos e defeitos contam itens de `ticket_items` ponderados por `quantidade`; solucoes contam tickets com `solution_type_id` preenchido. Top 5; empate desempatado por nome.
- **Filtros de produto/defeito no relatorio**: `EXISTS` em `ticket_items` (o ticket entra se qualquer item bate).
- **Soft delete**: tickets e anexos excluidos fora de todas as contagens, rankings, relatorio, export e galeria.
- **Tenant vazio**: zeros e listas vazias, nunca 404.

## 3. Frontend

Tres rotas novas no grupo Operacao da sidebar: **Dashboard** (`/dashboard`), **Relatorios** (`/relatorios`), **Midias** (`/midias`). O Dashboard vira a rota inicial apos o login (hoje cai na lista de tickets). Implementacao com o skill `frontend-design` e `docs/identidade-visual.md`; graficos com **Recharts** (dependencia nova).

**Fonte de verdade visual (2026-07-30):** as tres telas foram desenhadas em sessao propria e os mockups aprovados estao em `docs/frontendmockups/` — `Dashboard.dc.html`, `Relatorios.dc.html`, `Midias.dc.html` (todos os estados alternaveis) e `Componentes.md` (contrato dos componentes novos e o que reusa o que ja existe). O prompt de design usado esta em `docs/prompt-design-fase-3.md`. O HTML e normativo para layout, densidade, colunas e copy; as secoes abaixo resumem o comportamento.

Decisoes tomadas onde mockup e documentacao divergiam:

1. **Grafico de distribuicao por status em Recharts** (`BarChart layout="vertical"`), como manda `Componentes.md` — o mockup desenha com divs por limitacao do formato, mas define a aparencia-alvo (coluna de rotulo de 172px, barra de 16px sobre trilho visivel, contagem em mono a direita, eixo X com 5 ticks).
2. **Relatorios exige filtro antes de consultar**: abrir `/relatorios` sem filtro na URL mostra o estado "Nenhum filtro aplicado" e nao dispara requisicao. A tela e de recorte; a listagem completa continua sendo a lista de tickets.
3. **`SlaBadge` evolui** para a forma compacta do mockup (tempo restante em `font-mono`, travessao quando encerrado, pulso Paprika quando atrasado ou vencendo) e a mudanca vale tambem para a lista de tickets — um formato de SLA so no sistema.

### Dashboard

- Filtro por marca no topo (todas / KODI / STALEKS) que reconsulta o endpoint inteiro.
- Linha de 7 KPI cards clicaveis; cada card navega para `/tickets` com os query params do filtro correspondente. **Ajuste na lista de tickets**: os filtros passam a ser lidos e escritos na URL (hoje vivem so no estado do componente), o que tambem torna filtros compartilhaveis por link.
- Abaixo, 2/3 + 1/3 como no legado: a esquerda grafico de distribuicao por status (barras horizontais com as cores semanticas de status ja tokenizadas) e tabela de tickets recentes; a direita stat de tempo medio de resolucao e os tres rankings top 5 como listas com barra de proporcao.

### Relatorios

- Card de filtros colapsavel (comeca aberto) com 9 campos (periodo de/ate, selects de marca/status/atendente, autocompletes de produto/defeito/solucao/canal), botoes Filtrar/Limpar e chips de filtros ativos removiveis. O formulario e rascunho local; "Filtrar" e que escreve o recorte na URL.
- Quatro estados: inicial (nenhum filtro aplicado, sem consulta), carregando, sem resultado e padrao.
- 4 KPI cards do recorte (nao clicaveis, ao contrario dos do dashboard), rankings e tabela paginada de 8 colunas com linhas navegaveis para o detalhe do ticket (correcao sobre o legado, que nao tinha paginacao nem links).
- Botao Exportar CSV: fetch autenticado com os mesmos params da tela, download via blob; resposta nao-2xx vira toast de erro.

### Midias

- Card de filtros (tipo, marca, produto, defeito, solucao, status, periodo) + grid responsivo de thumbs com lazy loading por `IntersectionObserver` (carrega a proxima pagina ao chegar no fim).
- Clique abre o lightbox do detalhe do ticket, extraido para componente compartilhado, com metadados e link "Ver ticket".
- Placeholder por tipo quando `preview_url` e `null`.

## 4. Permissoes e erros

- Permissao nova `VER_VISIBILIDADE = "ver_visibilidade"` concedida a todos os papeis do tenant, inclusive `visualizador` (tudo leitura; visualizador ve todos os tickets por regra herdada do legado). Atendente ve os numeros do tenant inteiro: dashboard e relatorios sao visao gerencial consolidada, como no legado. As tres rotas usam a dependency de permissao existente.
- Validacao de query params (UUID malformado, pagina invalida): 422 pelo padrao FastAPI/Pydantic vigente.
- Periodo invertido nos relatorios (`/relatorios` e `/relatorios/export`): 422 de dominio quando `de >= ate`. O limite superior do filtro e **exclusivo** (`opened_at < ate`), entao `de == ate` descreve o conjunto vazio, nao "um unico dia" — e o front ja soma um dia ao valor escolhido (`isoEndExclusive`), de modo que `de == ate` na requisicao corresponde exatamente ao usuario ter invertido as datas em um dia, o caso mais comum de inversao. Antes de comparar, os dois valores sao normalizados para UTC: o Pydantic aceita tanto `?de=2026-08-01` (naive) quanto `?ate=2026-08-01T00:00:00Z` (aware), e compara-los direto levantaria `TypeError`. A normalizacao vale so para a comparacao; os filtros recebem os valores originais.
- Galeria: falha ao assinar o preview de um item nao derruba a pagina — o item sai com `preview_url = null`.
- Cada tela tem empty state com borda tracejada, no padrao do design system.

## 5. Testes (TDD, contra Postgres real, padrao atual)

- **Dashboard**: cenario semeado com tickets em varios status/marcas/datas verificando cada KPI (incluindo corte do mes civil e atrasados), distribuicao, rankings ponderados por quantidade, tempo medio so de finalizados (e `null` sem finalizados), exclusao de soft delete e filtro por marca.
- **Relatorios**: cada filtro isolado + combinacao; KPIs, rankings e tabela sobre o mesmo recorte; paginacao.
- **Export CSV**: mesmas fixtures do relatorio — cabecalho, conteudo das linhas, BOM UTF-8 e igualdade entre o total do CSV e o total da tela com os mesmos filtros.
- **Midias**: so `disponivel` nao excluidos, filtros via join do ticket, paginacao, item sem preview.
- **Permissoes**: cada rota com `visualizador` (200) e sem vinculo no tenant (403).
- **Front**: `tsc --noEmit`, `eslint`, `build` antes de cada commit; ao final da fase, passeio e2e com Playwright cobrindo dashboard -> card clicavel -> lista pre-filtrada, relatorio com filtro + export, e galeria -> lightbox -> link para o ticket (formato do passeio da 2A).
