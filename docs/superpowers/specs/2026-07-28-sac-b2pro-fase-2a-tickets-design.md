# Design — SAC-B2PRO Fase 2A (Tickets — core)

Data: 2026-07-28. Status: aprovado pelo usuario em 2026-07-28. Fontes: `docs/PRD.md` (secoes 4, 5, 6 e 7), `docs/legado-funcionamento.md`, `docs/legado-ui.md`, `docs/identidade-visual.md`, design da Fase 1.

## Objetivo e quebra de escopo

A Fase 2 do PRD foi dividida em dois ciclos spec -> plano -> execucao:

- **Fase 2A (este spec)** — core de tickets: maquina de estados explicita, numeracao por sequence, itens, SLA, comentarios internos, timeline, lido/nao lido, codigos reversos, pedido de garantia; front com lista, detalhe e criacao de ticket.
- **Fase 2B (spec proprio, depois)** — anexos no Wasabi S3 (`docs/armazenamento-anexos.md`): presigned PUT, confirmacao via HEAD, expiracao de pendentes, worker de previews, compressao client-side, upload com drag-and-drop. Na 2A o detalhe do ticket mostra apenas um card placeholder de anexos (desabilitado); a criacao nao tem area de upload.

Fora de escopo da 2A: dashboard/relatorios/galeria (Fase 3), notificacoes e SSE/WebSocket (Fase 4), importador (Fase 3), exclusao de ticket (nao existe — ver decisoes).

## Decisoes fechadas com o usuario (2026-07-28)

1. **Cliente inline na criacao**: lookup por CPF/CNPJ; documento existente vincula e atualiza o cadastro com os dados digitados; inexistente cria o cliente junto com o ticket (padrao bom do legado).
2. **Chat sem tempo real na 2A**: comentarios carregam ao abrir o ticket e refetch apos enviar. Nada de polling; SSE chega na Fase 4.
3. **Sem exclusao de ticket**: nenhum endpoint DELETE; ticket errado vira `cancelado` (com timeline). Coluna `deleted_at` existe no schema para o futuro.
4. **SLA configuravel em tabela por tenant**: `sla_policies` semeada com urgente 24h / alta 48h / media 72h / baixa 120h e alerta a 12h do prazo; sem UI de configuracao nesta fase.
5. **Maquina de estados na abordagem "um use case por transicao"**: tabela declarativa de transicoes no dominio + use case explicito por transicao, cada um com permissao, guards e payload proprios e rota POST dedicada. Alternativas descartadas: use case generico parametrizado (vira rota generica de status disfarcada) e state pattern OO (indirecao desnecessaria).

## 1. Dominio (`domain/tickets.py`)

- `TicketStatus` (StrEnum): `aberto`, `aguardando_cliente`, `aguardando_analise`, `aprovado`, `aguardando_envio_reverso`, `produto_recebido`, `finalizado`, `declinado`, `cancelado`. Conjunto `CLOSED_STATUSES = {finalizado, declinado, cancelado}`.
- `TicketPriority` (StrEnum): `baixa`, `media`, `alta`, `urgente`.
- `VALID_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]]` declarativa + funcao pura `ensure_transition(atual, alvo)` que levanta `InvalidTransitionError` (novo erro de dominio; HTTP 409 com `code: transicao_invalida`).
- Entidades (dataclasses, padrao da Fase 1): `Ticket`, `TicketItem`, `TicketComment`, `TicketTimelineEvent`, `ReverseCode`, `SlaPolicy`.
- SLA puro: `compute_due_at(opened_at, policy)` e `sla_state(now, due_at, closed) -> no_prazo | vence_em_breve | atrasado | encerrado` (`vence_em_breve` quando falta menos que `warn_hours`).
- Completude para envio a analise (funcao pura): cliente vinculado + ao menos um item + descricao nao vazia. Abertura parcial e permitida (`customer_id`, itens e descricao opcionais na criacao).

### Transicoes (cada uma um use case com permissao propria)

| Use case | De -> Para | Permissao | Guard / payload |
|---|---|---|---|
| EnviarParaAnalise | aberto, aguardando_cliente -> aguardando_analise | ENVIAR_PARA_ANALISE (atendente: so os seus) | completude; seta `submitted_at` |
| Aprovar | aguardando_analise -> aprovado | DECIDIR_TICKET | nota de decisao opcional; seta `approved_at` |
| Declinar | aguardando_analise -> declinado | DECIDIR_TICKET | motivo obrigatorio (nota de decisao); seta `declined_at` e `closed_at` |
| AguardarCliente | aberto -> aguardando_cliente | EDITAR_QUALQUER_TICKET ou EDITAR_PROPRIO_TICKET (dono) | — |
| Retomar | aguardando_cliente -> aberto | idem AguardarCliente | — |
| RegistrarReverso | permitido em aprovado e aguardando_envio_reverso | OPERAR_LOGISTICA_TODOS ou _PROPRIOS (dono) | codigo obrigatorio; de aprovado move para aguardando_envio_reverso |
| ExcluirReverso | permitido em aguardando_envio_reverso e produto_recebido | idem RegistrarReverso | remover o ultimo reverso em aguardando_envio_reverso volta o status para aprovado |
| ProdutoRecebido | aguardando_envio_reverso -> produto_recebido | OPERAR_LOGISTICA_* | — |
| Finalizar | aprovado, produto_recebido -> finalizado | OPERAR_LOGISTICA_* | solucao (solution_type_id) obrigatoria, nota final opcional; seta `closed_at` |
| Cancelar | qualquer nao encerrado -> cancelado | DECIDIR_TICKET | motivo opcional; seta `closed_at` |
| Reabrir | encerrado -> aprovado se `approved_at` preenchido, senao aberto | DECIDIR_TICKET | limpa `closed_at` (marcos historicos preservados) |

- Toda transicao grava `TicketTimelineEvent` (old_value/new_value = status) e atualiza `last_activity_at`.
- Pedido de garantia (codigo manual + rastreio) e atualizacao de campos (`PUT /garantia`), nao muda status, gera evento na timeline.
- Regra de dono ("so os seus"): compara `attendant_user_id` com o usuario do token; aplicada dentro dos use cases quando a permissao e a variante "proprios". Visualizacao segue VER_TODOS_TICKETS / VER_PROPRIOS_TICKETS.

## 2. Modelo de dados (migration tenant `0003_tickets`)

Todas as tabelas no schema simbolico `tenant` (padrao da Fase 1). Tickets nao tem coluna `active` (o ciclo de vida e o status); tem `deleted_at` (sempre null nesta fase).

- `tickets` — `id UUID`, `number BIGINT NOT NULL UNIQUE DEFAULT nextval('ticket_number_seq')` (sequence criada pela migration no schema do tenant — numeracao por sequence nativa, sem race condition), `brand_id FK NOT NULL`, `customer_id FK NULL`, `attendant_user_id UUID NOT NULL` (id de `public.users`, sem FK cross-schema; nomes resolvidos por join no repositorio), `supervisor_user_id UUID NULL`, `status`, `priority`, `purchase_channel_id FK NULL`, `order_code`, `purchase_date DATE NULL`, `delivery_date DATE NULL`, `description TEXT NULL`, `decision_notes TEXT NULL`, `final_notes TEXT NULL`, `solution_type_id FK NULL`, `warranty_order_code NULL`, `warranty_tracking_code NULL`, marcos (`opened_at NOT NULL`, `submitted_at`, `approved_at`, `declined_at`, `closed_at`, `last_activity_at NOT NULL`, `due_at NOT NULL`), `created_at/updated_at/deleted_at`.
- `ticket_items` — `ticket_id FK`, `product_id FK NOT NULL`, `defect_type_id FK NOT NULL`, `quantity INT NOT NULL CHECK >= 1`, timestamps. **Fonte unica de verdade** — nenhum campo de produto/defeito duplicado em `tickets`.
- `ticket_comments` — `ticket_id FK`, `author_user_id UUID NOT NULL`, `reply_to_id FK self NULL`, `body TEXT NOT NULL`, `created_at`.
- `ticket_timeline_events` — `ticket_id FK`, `type` (string curta: `criacao`, `transicao`, `prioridade_alterada`, `item_adicionado`, `item_removido`, `item_alterado`, `reverso_registrado`, `reverso_excluido`, `garantia_registrada`, `edicao`), `title`, `old_value TEXT NULL`, `new_value TEXT NULL`, `author_user_id UUID NULL`, `created_at`. Comentarios nao entram na timeline (ficam no chat).
- `ticket_reads` — PK composta (`ticket_id`, `user_id`), `last_read_at NOT NULL`. Nao lido = sem linha ou `last_read_at < tickets.last_activity_at`.
- `reverse_codes` — `ticket_id FK`, `code NOT NULL`, `author_user_id`, `created_at`.
- `sla_policies` — `priority UNIQUE`, `hours INT`, `warn_hours INT DEFAULT 12`. Semeada no provisionamento e no comando `seed_tenant` (idempotente, nao sobrescreve valores editados): urgente 24, alta 48, media 72, baixa 120.
- Indices: `tickets(status)`, `tickets(last_activity_at DESC)`, `tickets(due_at)`, `tickets(customer_id)`, `tickets(attendant_user_id)`, FKs dos satelites por `ticket_id`.

### Divida da Fase 1 tratada

O repositorio de tickets nao usa o `_flush_or_conflict` generico (que traduz qualquer `IntegrityError` para 409). Ele inspeciona o nome da constraint violada: FK de cadastro inexistente -> 422 apontando o campo; unique -> 409; constraint desconhecida -> re-raise. O unique parcial (`WHERE deleted_at IS NULL`) segue desnecessario — nao ha delete de cadastros nem de tickets.

## 3. Application (use cases)

- `CreateTicket` — CRIAR_TICKET. Criacao parcial permitida (minimo: marca, prioridade; atendente default = usuario logado). Aceita lista de itens e cliente inline (por documento: vincula/atualiza ou cria — reusa validacao de documento do dominio). Calcula `due_at` via `sla_policies`, grava evento `criacao`, marca como lido para o criador.
- `UpdateTicket` — EDITAR_QUALQUER_TICKET ou EDITAR_PROPRIO_TICKET (dono, apenas em aberto/aguardando_cliente, conforme matriz do PRD). Edita dados gerais (marca, cliente, supervisor, compra, prioridade, descricao). Mudanca de prioridade recalcula `due_at` e gera evento `prioridade_alterada`.
- Itens: `AddTicketItem`, `UpdateTicketItem`, `RemoveTicketItem` — mesma regra de permissao/estado do UpdateTicket; eventos na timeline.
- `ListTickets` — VER_TODOS_TICKETS ou VER_PROPRIOS_TICKETS (atendente ve so os seus). Filtros: status, marca, cliente (nome ou documento normalizado), produto, pedido, prioridade, atrasados (`due_at < now` e nao encerrado), `customer_id` (historico do cliente). Paginacao `{items, total, page, per_page}` (default 20, max 100), ordenacao (default `last_activity_at DESC`), flag `unread` por linha (left join `ticket_reads`).
- `GetTicketDetail` — agrega ticket + cliente + itens (com nomes de produto/defeito) + comentarios + timeline + reversos + garantia + nomes de atendente/supervisor + `sla_state`. Marca como lido (upsert em `ticket_reads`).
- `MarkTicketUnread` — remove a linha de `ticket_reads` do usuario.
- `AddComment` — COMENTAR_ANEXAR; bloqueado em ticket encerrado (409); `reply_to_id` deve pertencer ao mesmo ticket; atualiza `last_activity_at` (torna o ticket nao lido para os demais).
- Transicoes — um use case por linha da tabela da secao 1.
- `SetWarranty` — OPERAR_LOGISTICA_* (dono se proprios); grava codigo do pedido de garantia + rastreio, evento `garantia_registrada`.

## 4. API (`interface/routers/tickets.py`, prefixo `/api/tickets`)

Autorizacao via `require_permission` + `get_tenant_session` (padroes existentes).

- `POST /` cria; `GET /` lista com filtros; `GET /{id}` detalhe; `PUT /{id}` edita.
- `POST /{id}/itens`, `PUT /{id}/itens/{item_id}`, `DELETE /{id}/itens/{item_id}`.
- Transicoes: `POST /{id}/enviar-analise`, `/aprovar`, `/declinar`, `/cancelar`, `/aguardar-cliente`, `/retomar`, `/produto-recebido`, `/finalizar`, `/reabrir`.
- `POST /{id}/reversos`, `DELETE /{id}/reversos/{reverso_id}`, `PUT /{id}/garantia`.
- `POST /{id}/comentarios`, `POST /{id}/nao-lido`.
- Erros no handler unico: 401 sem token; 403 sem permissao ou ticket de outro atendente; 404 ticket/satelite inexistente (ou fora do escopo de visao do atendente); 409 transicao invalida, comentario em encerrado, unique; 422 payload invalido, completude insuficiente no envio a analise (lista os campos faltantes), FK de cadastro inexistente.

## 5. Frontend (skill frontend-design + `docs/identidade-visual.md`)

- Sidebar: item **Tickets** (grupo operacional, acima de Cadastros), visivel para papeis de tenant. Rotas: `/tickets`, `/tickets/novo`, `/tickets/:id`. `lib/tickets.ts` como client da API (padrao `lib/cadastros.ts`).
- **Lista** (`TicketsListPage`): card de filtros (status, marca, cliente nome/documento, produto, pedido, prioridade, atrasados) com **debounce** nos campos de busca (divida da Fase 1); tabela densa — numero em mono, cliente, itens (primeiro produto + contador), prioridade com dot, badge de status, SLA com prazo relativo, atendente, abertura; indicador de nao lido (dot + peso tipografico); linha inteira como link real (`<a>`); paginacao e ordenacao; botao "Novo ticket" (oculto para visualizador).
- **Detalhe** (`TicketDetailPage`), estrutura 2/3 + 1/3:
  - Esquerda: cards Informacoes gerais, Cliente (link "ver historico" -> lista filtrada por `customer_id`), Compra, Itens (tabela; editavel conforme estado/papel), Anexos (placeholder desabilitado "anexos na Fase 2B") e Comentarios em chat (bolhas, reply com citacao, refetch ao enviar; bloqueado em encerrado).
  - Direita: **uma acao primaria contextual por estado** — aberto: Enviar para analise; aguardando_cliente: Retomar; aguardando_analise: Aprovar (Declinar como secundaria; atendente ve apenas "aguardando decisao"); aprovado: Registrar reverso (Finalizar direto como secundaria); aguardando_envio_reverso: Produto recebido; produto_recebido: Finalizar; encerrado: Reabrir (so quem decide). Demais acoes (cancelar, aguardar cliente, garantia, nao lido) em menu; formularios com input (declinar, finalizar, cancelar, reverso, garantia) em modal/drawer proprios (nunca confirm/alert nativos). Cards de Reversos e Garantia; **timeline com trilha/conector visual** da identidade visual.
  - Acoes renderizadas conforme permissao do papel e estado — a mesma matriz do backend, espelhada num helper de front.
- **Criacao** (`TicketCreatePage`): secoes — Cliente (CPF/CNPJ com mascara + lookup com debounce: achou -> autofill completo + vinculo; nao achou -> campos liberados para cadastro inline; CEP com autofill via `/api/cep` com fallback manual), Compra (canal com autocomplete do cadastro, pedido, datas), Caso (marca, prioridade com indicacao do SLA resultante, supervisor opcional, itens repetiveis produto+defeito+quantidade com busca, descricao). Sem upload nesta fase. Submit cria e navega para o detalhe.
- Visualizador: paginas em modo somente leitura (sem botoes de acao/criacao).

## 6. Testes (TDD)

- Unit (dominio): `ensure_transition` exaustiva (validas e invalidas), `compute_due_at`/`sla_state` (limites de warn e encerrado), completude de envio.
- Unit (application, com fakes): cada use case de transicao (guard, permissao, dono, timeline, marcos), CreateTicket (cliente inline: cria/vincula/atualiza; due_at; parcial), UpdateTicket (recalculo de SLA), AddComment (bloqueio em encerrado, reply de outro ticket), regras de reverso (ultimo excluido volta a aprovado).
- Integracao (Postgres real, fixtures da Fase 1): caminho feliz completo aberto -> analise -> aprovado -> reverso -> recebido -> finalizado conferindo timeline e marcos; declinio (motivo obrigatorio); cancelamento; reabertura com e sem aprovacao previa; numeracao unica e crescente em criacoes concorrentes; permissoes por papel (atendente nao ve/opera ticket alheio — 404/403; visualizador so le); comentario em encerrado -> 409; nao-lido (comentario de outro usuario torna nao lido; abrir detalhe marca lido; acao nao-lido); isolamento entre tenants; FK invalida -> 422 (nao 409).
- Front: `tsc --noEmit`, `eslint`, `build`. Playwright fica para os fluxos criticos na Fase 4.

## 7. Mudancas em codigo existente

- `domain/errors.py`: novo `InvalidTransitionError` (mapeado para 409 no handler unico em `interface/errors.py`).
- `infrastructure/provisioning.py` e `seed_tenant.py`: semeiam `sla_policies`.
- `infrastructure/models_tenant.py`: novos models; `interface/deps.py`: factories dos novos use cases.
- `frontend/src/components/layout/Sidebar.tsx`: item Tickets.
- Nenhuma mudanca na matriz de permissoes: os enums de ticket da Fase 0 (`ENVIAR_PARA_ANALISE`, `DECIDIR_TICKET`, `OPERAR_LOGISTICA_*`, `COMENTAR_ANEXAR`, `VER_*`, `EDITAR_*`, `CRIAR_TICKET`) passam a ser usados de verdade.
