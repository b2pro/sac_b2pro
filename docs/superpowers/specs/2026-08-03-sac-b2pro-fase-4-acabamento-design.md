# Design — SAC-B2PRO Fase 4 (Acabamento)

Data: 2026-08-03. Status: aprovado pelo usuario em 2026-08-03. Fontes: `docs/PRD.md` (secoes 6.9, 8 e 10), `docs/identidade-visual.md`, `docs/armazenamento-anexos.md`, pendencias deliberadas das Fases 2A e 2B.

## Objetivo

Ultima fase do PRD: notificacoes in-app com push real (SSE), busca global, preferencias de usuario (tema e comportamento das notificacoes) e hardening — gestao de membros por tenant, rate limit de login mais fino e a limpeza de objetos orfaos no Wasabi. Fecha tambem os residuais de acessibilidade anotados na Fase 3B.

Fora de escopo: notificacao ao cliente final (e-mail/WhatsApp), Redis ou qualquer broker novo, pagina dedicada de historico de notificacoes, highlight de trecho na busca, preferencias de fila (densidade/ordenacao padrao), migracao do worker de previews para fila externa.

## Decisoes fechadas com o usuario (2026-08-03)

1. **Sem Redis.** Avaliado e descartado para esta fase: pubsub sai por Postgres LISTEN/NOTIFY, rate limit continua in-memory (instancia unica), a fila de previews ja e duravel no Postgres e nao ha hot path medido que justifique cache. As portas (limiter, publisher) ficam isoladas para permitir Redis depois, quando houver replicas ou gargalo medido.
2. **Transporte das notificacoes: SSE + LISTEN/NOTIFY.** Uma conexao asyncpg em LISTEN por instancia do backend, fan-out em memoria para as conexoes SSE abertas. Tabela como fonte de verdade; o stream e so o aviso.
3. **Destinatarios: atribuido + envolvidos.** Atribuicao notifica o novo atendente; transicoes e comentarios notificam o atendente atribuido e os autores distintos de comentarios do ticket. O autor da acao nunca se auto-notifica.
4. **Busca global: entidades e identificadores.** Tickets (numero, codigo do pedido), clientes (nome, documento, email, telefone), produtos (nome, SKU). Sem descricao de ticket nem corpo de comentario.
5. **Preferencias: tema + notificacoes.** Tema claro/escuro/sistema (montando o next-themes de verdade) e toggles de toast/som. Persistencia no servidor por usuario (global, schema public).
6. **Orfaos no Wasabi: delecao direta + varredura.** Expirar/descartar/deletar apagam o objeto no storage na hora (best-effort); job periodico de reconciliacao no worker apaga objetos com mais de 24h sem anexo ativo. Staging descartado (mudaria o fluxo de upload testado); regra de bucket ja havia sido descartada na Fase 2B.
7. **Membros por tenant: admin gerencia.** Endpoints protegidos por `GERENCIAR_USUARIOS` (que passa a ser consumida; so o papel admin a tem). Supervisor nao ganha a permissao — a definicao do papel (tudo menos gerenciar usuarios) e deliberada e permanece.

## 1. Notificacoes in-app

### Dados

Tabela nova por schema de tenant, `notifications`:

- `id` (PK), `user_id` (destinatario, usuario global), `ticket_id` (FK), `type` (`atribuicao` | `transicao` | `comentario`), `title` (curto, ex. "Ticket #489 aprovado"), `snippet` (nullable; inicio do comentario), `actor_user_id`, `created_at`, `read_at` (nullable).
- Indices: parcial `(user_id) WHERE read_at IS NULL` (contador) e `(user_id, created_at DESC)` (listagem).
- Migration na chain tenant. A fase cria duas migrations de tenant (esta tabela e os indices da busca global) e uma na chain public (`user_preferences`); a numeracao segue a ordem de implementacao a partir de 0009 (tenant) e da proxima livre na public.

### Emissao (fan-out)

Servico de aplicacao `NotificationFanout`, chamado pelos use cases que ja emitem timeline:

- transicoes de status — ponto unico na base de `tickets_workflow.py`;
- troca de atendente — em `tickets_crud.py` (a timeline nao registra atribuicao hoje; o fan-out e disparado no proprio use case de edicao/atribuicao);
- comentario novo — no `add_comment`.

Regra de destinatarios (decisao 3), resolvida com uma query: atendente atribuido + `DISTINCT author_user_id` dos comentarios do ticket, menos o ator. Zero destinatarios = nenhuma linha, nenhum NOTIFY.

As linhas sao gravadas **na mesma transacao** do caso de uso, seguida de `pg_notify` no canal do tenant (payload: ids de usuario destinatarios). NOTIFY e transacional: o aviso so sai se o commit acontecer; nao existe notificacao fantasma nem acao sem aviso. Nada muda no worker — todos os eventos nascem no processo da API.

### Entrega (SSE)

- `GET /api/notificacoes/stream` — endpoint SSE autenticado.
- O backend mantem por instancia: uma conexao asyncpg dedicada em `LISTEN` (reconexao com backoff se cair) e um registro em memoria das conexoes SSE abertas, chaveado por (tenant, usuario). NOTIFY recebido vira push apenas para as conexoes daquele destinatario.
- Heartbeat (comentario SSE) a cada ~25s para atravessar proxies.
- No frontend, `EventSource` nao envia header `Authorization`; o stream e consumido com `fetch` + parse manual do `ReadableStream` (protocolo SSE e linha-a-linha, ~40 linhas de codigo), mantendo o Bearer e o refresh-on-401 do `apiRaw`. Reconexao com backoff; ao reconectar, o cliente refaz o GET da lista — a tabela e a fonte de verdade.

### API REST

- `GET /api/notificacoes` — paginada, filtro lidas/nao lidas.
- `GET /api/notificacoes/contador` — total de nao lidas.
- `POST /api/notificacoes/marcar-lidas` — todas ou ids especificos.

### UI

Sino no `Header.tsx` com badge de nao lidas; dropdown com as recentes e "marcar todas como lidas"; clicar numa notificacao navega ao ticket e a marca como lida. Evento chegando pelo stream invalida as queries do sino e dispara toast (sonner) e/ou som curto conforme as preferencias do usuario (secao 3). Sem pagina dedicada de historico — o dropdown pagina.

### Erros

Queda do listener: reconexao com backoff no servidor; o cliente continua funcional via refetch. Queda de rede no cliente: backoff e re-sincronizacao no reconnect. Fan-out nao tem caminho de falha separado da acao principal (mesma transacao).

## 2. Busca global

### Backend

`GET /api/busca?q=` — router novo, escopo do tenant, qualquer papel autenticado. Resposta com tres grupos de ate 5 resultados:

- **tickets**: numero (termo so-digitos, com ou sem `#`) e `order_code` (trgm existente); item traz numero, cliente, status, marca.
- **clientes**: nome (trgm existente), documento, email, telefone. Documento e telefone casam por digitos normalizados (termo limpo de pontuacao).
- **produtos**: nome (trgm existente) e SKU.

Reusa `escape_like` de `sql_search.py`. Termo com menos de 2 caracteres nao consulta. Tres queries na mesma sessao.

Migration tenant nova (`indices_busca_global`): GIN trgm em `customers.document`, `customers.email`, `customers.phone`, `products.sku` — campos curtos, indices baratos (racional de medicao em `docs/medicao-indices-tenant.md`).

### Frontend

Command palette: campo de busca no lado esquerdo do header (hoje vazio) que abre um dialog; atalho `Ctrl+K`/`Cmd+K`. Debounce ~250ms, resultados agrupados por tipo, navegacao por teclado, Enter abre o detalhe; acao final "buscar na fila" leva para `/tickets?q=`. Estados de vazio/loading pela identidade visual.

## 3. Preferencias de usuario

### Dados e API

Tabela `user_preferences` no schema `public` (usuarios sao globais): `user_id` (PK, FK users), `theme` (`claro` | `escuro` | `sistema`, default `sistema`), `notify_toast` (bool, default true), `notify_sound` (bool, default false), `updated_at`. Linha criada sob demanda; `GET /api/preferencias` sem linha devolve defaults. `PUT /api/preferencias` grava. Ambos exigem apenas autenticacao — a preferencia acompanha o usuario em qualquer tenant.

### Frontend

- Pagina "Preferencias" acessada pelo dropdown do usuario no header (nao entra na sidebar de negocio): seletor de tema e toggles de toast/som.
- `ThemeProvider` do next-themes montado em `main.tsx` (`attribute="class"`); ao carregar a sessao, o valor do servidor sincroniza o tema local. next-themes cuida de flash e persistencia local.
- O sino le `notify_toast`/`notify_sound` do cache do react-query antes de tocar toast/som. Som: beep curto embutido como asset unico.

### Passe de dark mode

O esforco dominante da secao: auditoria de contraste/cores no tema escuro, tela a tela (shell, fila, detalhe, cadastros, dashboard, relatorios, galeria, login), com o skill `frontend-design` e `docs/identidade-visual.md`. A identidade usa tokens; o passe define a paleta escura dos tokens e corrige componentes que fixam cor fora deles. Graficos do dashboard entram no passe (cores de serie legiveis nos dois temas).

## 4. Hardening

### Membros por tenant (pendencia 2A)

Endpoints no escopo do tenant, protegidos por `require_permission(GERENCIAR_USUARIOS)`:

- `GET /api/membros` ganha variante gerencial (papel, status do vinculo, email); a resposta enxuta atual permanece para os dropdowns de atribuicao.
- `POST /api/membros` — email existente ganha vinculo com papel; email novo cria usuario global (senha inicial definida pelo admin) + vinculo.
- `PATCH /api/membros/{user_id}` — papel do vinculo, ativar/desativar vinculo.
- `POST /api/membros/{user_id}/senha` — redefinir senha.

Salvaguardas: nunca toca usuarios super_admin; o admin nao altera o proprio vinculo (papel ou desativacao); tudo restrito ao tenant do token. UI: pagina "Membros" visivel apenas com a permissao.

### Rate limit de login (pendencia 2A)

- `/refresh` passa a ser limitado (mesmo limiter, chave propria).
- `X-Forwarded-For` honrado atras de flag `trusted_proxy` nas settings (off por default).
- Duas janelas: por IP+tenant (fina, 5 tentativas/60s como hoje) e por IP global (mais larga, 30 tentativas/60s, pega varredura de slugs). Valores configuraveis nas settings.
- Continua in-memory: instancia unica; a porta do limiter permite trocar o backend depois. Decisao documentada aqui.

### Orfaos no Wasabi (pendencia 2B)

- `ExpirePendingUseCase`, `DiscardIntentUseCase` e `DeleteAttachmentUseCase` passam a apagar objeto e previews no storage, best-effort: falha de storage loga e nao quebra o caso de uso.
- Job de reconciliacao no worker, no ciclo diario junto do `expire_pending_all`: lista o bucket por prefixo de tenant e apaga objetos com mais de 24h sem anexo ativo correspondente no banco. A margem de 24h garante que upload em andamento nunca e apagado. O job e a rede de seguranca do que a delecao direta perder.

### Residuais de acessibilidade

- Pill do filtro de cliente na fila ganha `aria-live`.
- Componentes novos da fase (sino, palette, preferencias, membros) nascem com focus-visible, aria e navegacao por teclado.
- Duplicacao estrutural do match de cliente fica como esta (so extrair no 4o call site).

## 5. Testes

### Backend (TDD)

Unit: destinatarios do fan-out (atribuido, envolvidos, exclusao do ator, zero destinatarios), montagem da notificacao por tipo, normalizacao do termo de busca, validacoes de preferencias, salvaguardas de membros, janelas do limiter (IP+tenant e IP global, refresh), decisao de orfao da reconciliacao com storage fake.

Integracao (Postgres real): repositorio de notificacoes (contador, marcar lidas, paginacao), fan-out disparado pelos use cases reais (transicao, comentario, atribuicao), stream SSE com cliente httpx em streaming (conecta, comenta, evento chega), endpoint de busca com indices novos, migrations novas cobertas pelo `test_migrations`, API de preferencias, matriz de autorizacao de membros, `/refresh` limitado, ciclo de delecao no storage (expire/discard/delete + reconciliacao).

### E2E Playwright

- `08-notificacoes.spec.ts` — A comenta em ticket de B; B ve badge e dropdown, marca lida (padrao de dois contextos do spec 04).
- `09-busca-global.spec.ts` — Ctrl+K, cliente por documento, ticket por numero, navegacao.
- `10-preferencias-e-membros.spec.ts` — troca de tema refletida no `html`; admin cria membro; membro novo loga.

`E2E_PORT=5188`, nunca em background.

### Verificacoes locais por commit

Backend: `ruff check`, `ruff format --check`, `mypy` (sem path), `pytest` com o venv do projeto. Frontend: `tsc --noEmit`, `eslint`, `build`.
