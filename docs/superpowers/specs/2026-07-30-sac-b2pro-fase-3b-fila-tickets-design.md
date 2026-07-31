# Design — SAC-B2PRO Fase 3B (Fila de tickets repaginada)

Data: 2026-07-30. Status: aprovado pelo usuario em 2026-07-30. Fontes: `docs/frontendmockups/Tickets.dc.html` (mockup aprovado), `docs/PRD.md` (secao 6.3), `docs/legado-ui.md`, design da Fase 2A.

## Objetivo

Substituir a lista de tickets atual — card de filtros no topo e tabela de 10 colunas — pela fila desenhada em `Tickets.dc.html`: filtros no header, chips de filtro rapido com contagem e uma lista de cards de duas linhas por ticket. Inclui o backend que a tela nova exige e que hoje nao existe.

Fase separada da Fase 3 porque repagina uma tela ja entregue (Fase 2A) e adiciona capacidade de busca e filtro ao endpoint de tickets — nao e visibilidade nova. Entra **logo depois da Fase 3**, aproveitando os componentes compartilhados criados lá (`Pagination`, `EmptyState`, `SlaBadge` compacto, `STATUS_ACCENTS`).

Fora de escopo: redesenho do detalhe do ticket e da criacao de ticket; mudanca no formato do numero do ticket.

## Decisoes fechadas com o usuario (2026-07-30)

1. **Ordenacao continua existindo**, como um select compacto no header ao lado dos filtros — nao volta o paredao de campos, mas nao se perde ordenar por vencimento ou por mais antigo, que e uso operacional da fila. O mockup omite o controle; a omissao nao e adotada.
2. **Numero do ticket continua `#489`** (sequence do tenant). Os mockups mostram `#2026-0489`, formato que nao e adotado em nenhuma tela — nem aqui nem nas da Fase 3.
3. **O botao "Novo ticket" permanece** no header, como acao primaria. O mockup nao o mostra porque a sessao de design tratou as telas como somente leitura; a fila nao e — tirar o botao removeria o unico ponto de entrada para criar ticket.
4. **Fase 3B vem depois da Fase 3.**

## 1. Backend

O endpoint `GET /api/tickets` ganha tres filtros e nasce um endpoint de contadores. Nada de tabela nova.

**Revisao de 2026-07-31 (medicao de indices).** A versao original desta spec dizia "nada de migration". Isso mudou: a medicao em 100 mil tickets (`docs/medicao-indices-tenant.md`) mostrou que `ilike '%x%'` sobre `customers.name` custa 25,8 ms em Seq Scan de 40 mil clientes e cresce linear, e curinga a esquerda nao alcanca b-tree. A busca livre passa a depender de `pg_trgm` com indices GIN: **duas** migrations, uma na chain `public` (a extensao e por database) e uma na chain `tenant` (os indices sao por schema).

### `atendente_id` (filtro por atendente)

`TicketFilters.attendant_user_id` **ja existe** e `SqlTicketRepository._base_stmt` **ja o aplica** — falta apenas expor o query param no router e passa-lo adiante. Serve ao select "Atendente" do header e ao chip "Meus tickets" (`atendente_id` = usuario do token).

### `q` (busca livre)

Um campo, quatro alvos, unidos por `OR`:

- **numero**: quando `q` (sem `#` e sem espacos) e composto so de digitos, casa por prefixo em `number` convertido para texto — `"48"` acha `#48` e `#489`.
- **cliente**: `ilike` no nome do cliente (o filtro `customer` atual tambem casa documento; `q` fica só no nome, porque documento continua disponivel no filtro dedicado).
- **produto**: `EXISTS` em `ticket_items` juntando `products`, com `ilike` no nome do produto.
- **pedido**: `ilike` em `tickets.order_code`. Entrou na revisao de 2026-07-31: o header repaginado remove o campo de pedido dedicado, e sem este alvo a capacidade de achar um ticket pelo codigo do pedido sumiria.

Busca com trim, case-insensitive, acento como o Postgres devolve (sem `unaccent` — nao esta instalado). `q` e independente dos filtros `customer`/`product_id`, que continuam existindo para uso programatico e para os deep links do dashboard.

Os tres `ilike` sao atendidos por indices GIN de trigrama (`customers.name`, `products.name`, `tickets.order_code`). Trigrama so ajuda a partir de 3 caracteres; abaixo disso o planner cai em Seq Scan, o que e aceitavel porque um termo de 1-2 letras casa quase tudo de qualquer forma.

### `unread` (nao lidos)

Filtro booleano: entra o ticket que **nao tem** registro em `ticket_reads` para o usuario do token, ou cuja `last_read_at` e anterior a `last_activity_at` — exatamente a condicao que `SqlTicketRepository.list` ja usa para calcular a flag `unread` de cada linha, agora tambem como `WHERE`.

Na forma de SQL, as duas condicoes colapsam numa negacao unica — "nao existe leitura minha igual ou posterior a ultima atividade" — expressa como `NOT EXISTS` correlacionado. A medicao mostrou por que a forma importa: como predicado sobre o LEFT JOIN com `ticket_reads` o planner materializa o join antes de paginar (Seq Scan, 2.001 buffers); como anti-join ele entra por `pk_ticket_reads (ticket_id, user_id)` e preserva o Index Scan ordenado por `last_activity_at`.

### `GET /api/tickets/contadores`

Alimenta os seis chips em uma requisicao (seis chamadas a lista seria desperdicio). Resposta:

```
{ "todos": int, "abertos": int, "aguardando_analise": int,
  "atrasados": int, "nao_lidos": int, "meus": int, "ativos": int }
```

- Respeita o escopo de visao do papel: atendente conta apenas os proprios tickets, como na lista.
- **Ignora os filtros do header** — os numeros do chip sao absolutos, para o usuario saber quanto existe antes de filtrar.
- `todos` = todos os nao excluidos (o default da lista, incluindo encerrados); `ativos` = nao encerrados, usado no subtitulo "N tickets ativos".
- Permissao: a mesma da lista (`VER_TODOS_TICKETS` ou `VER_PROPRIOS_TICKETS`).
- **Uma varredura so**, com `count(*) FILTER` por recorte — nao uma contagem por chip. A Fase 3 ja colapsou os sete KPIs do dashboard assim. Nenhum indice e criado para servir esses `FILTER`: um `FILTER` de agregado e avaliado linha a linha depois da varredura e nunca vira predicado de indice.

## 2. Frontend

`TicketsListPage` reescrita segundo `Tickets.dc.html`. A URL continua sendo a verdade dos filtros (feito na Fase 3), ganhando as chaves `q`, `atendente_id` e `unread`.

- **Header**: titulo "Tickets" e subtitulo "Fila de trocas e defeitos — `N` tickets ativos" (numero em mono); a direita, campo de busca de 250px ("Buscar por no, cliente, produto ou pedido", com debounce), selects de Status / Marca / Atendente, select compacto de ordenacao e o botao "Novo ticket".
- **Chips de filtro rapido**: Todos, Abertos, Aguardando analise, Atrasados, Nao lidos, Meus tickets — cada um com a contagem do endpoint de contadores. O chip ativo fica com fundo Carbon Black e texto claro; "Atrasados" usa Paprika quando nao esta ativo. Clicar troca o recorte na URL.
- **Cards em vez de tabela**: um card por ticket, borda esquerda de 3px na cor do status, duas linhas — a primeira com bolinha de nao lido (Paprika), numero, cliente, badge de status, prioridade e SLA a direita; a segunda, em tom secundario, com produto (truncado), contagem de itens, atendente e, a direita, "aberto DD/MM · atividade DD/MM HH:MM". O card inteiro e link real para o detalhe.
- **Paginacao** identica a de Relatorios (componente reusado).
- **Estados**: carregando com oito skeletons de 76px; vazio com borda tracejada ("Nenhum ticket aberto para este filtro" / "Ajuste a busca ou os filtros acima.").

O que sai da tela atual: card de filtros (vira header), tabela de 10 colunas (vira card), campo de pedido e filtro de prioridade dedicados (o pedido passa a ser alcancavel pela busca livre; prioridade fica visivel no card e filtravel pelo Status? **nao** — prioridade sai dos filtros; se fizer falta, volta como chip). Menu kebab por linha e acoes em lote nao existem hoje e continuam fora.

## 3. Testes

- **Backend (TDD, Postgres real)**: `atendente_id` filtrando; `q` casando por prefixo de numero, por nome de cliente e por nome de produto, e nao casando o que nao deve; `unread` com ticket nunca lido, ticket lido antes da ultima atividade e ticket lido depois; contadores conferindo cada um dos sete numeros, com escopo de atendente e com soft delete fora; permissao das rotas.
- **Front**: `pnpm build` e `pnpm lint`; e2e cobrindo busca por numero, chip de atrasados, chip de nao lidos, ordenacao e navegacao do card para o detalhe. Os specs e2e existentes (01 a 05) apontam para a tabela antiga e serao ajustados aos seletores novos — comportamento preservado, seletor atualizado.
