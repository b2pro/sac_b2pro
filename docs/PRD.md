# PRD — SAC-B2PRO

Documento central do produto. Consolida tudo que foi decidido; os demais arquivos em `docs/` são material de apoio (seção 12). Em caso de divergência, este PRD prevalece.

## 1. Visão geral

Plataforma SaaS de SAC focada em **trocas, defeitos e garantias**: registro da reclamação, análise e aprovação, logística (reverso, pedido de garantia, rastreio) e conclusão, com SLA, auditoria completa e relatórios.

**Problema que resolve:** hoje o controle é feito em duas planilhas manuais (marcas KODI e STALEKS) — sem padronização de dados, sem cadastro único de cliente/produto, sem status confiável, sem visão consolidada. Existe um sistema legado (SAC-Tickets, Laravel, vibe-codado) que serve de referência funcional e de layout, mas com defeitos estruturais que não serão repetidos.

**Objetivo:** refazer o trabalho profissionalmente — backend limpo e testado, front com o layout do legado melhorado — e migrar os dados das planilhas.

## 2. Decisões fechadas

| Tema | Decisão |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, Uvicorn |
| Arquitetura backend | Clean Architecture (domain / application / infrastructure / interface), dependências apontando para dentro |
| Processo | TDD obrigatório no backend (pytest); Playwright no front quando necessário |
| Estilo | PROIBIDO emojis em código, UI, docs, commits e respostas |
| Frontend | React + TypeScript + Vite; layout inspirado no legado, profissionalizado |
| Tenancy | Multi-tenant por schema no Postgres; **a operação atual usa um tenant só** — KODI e STALEKS diferenciadas por campo/cadastro Marca |
| Módulos | Sistema de módulos por tenant (feature flags) desde o início; módulo Eventos fica **fora do escopo** por agora |
| Notificações | SAC apenas interno — nenhuma comunicação com o cliente final por enquanto |
| Anexos | Wasabi S3 (API S3): upload direto com presigned URL, imagens comprimidas acima do limite, PDFs como estão, previews por job próprio (Wasabi não tem thumbnail nativo) |

## 3. Multi-tenancy e autenticação

- Schema `public` (global): `tenants` (slug, nome, status ativa/teste/suspensa/inativa, módulos), `users` (globais, e-mail único global), `user_tenants` (vínculo com **papel por tenant**).
- Schema `t_<slug>` por tenant: todas as tabelas de negócio. Isolamento físico via `search_path` resolvido por middleware a partir do JWT — sem coluna `tenant_id` espalhada.
- Alembic com duas árvores de migração: `public` e tenants (aplicada a todos os schemas). Criar tenant provisiona o schema.
- **Login: email + senha + slug do tenant** -> valida vínculo em `user_tenants` -> JWT com usuário, tenant e papel. Verificação de usuário e tenant ativos no próprio login; rate limiting; hash argon2. Sem registro público; reset de senha por admin.
- Papéis: `super_admin` (global, painel da plataforma, não acessa o operacional) e, por tenant: `admin`, `supervisor`, `atendente`, `visualizador`.

Permissões (herdadas do legado):

| Ação | admin | supervisor | atendente | visualizador |
|---|---|---|---|---|
| Ver tickets | todos | todos | só os próprios | todos (leitura) |
| Criar / editar ticket | sim | sim | sim (os seus, se aberto/aguardando cliente) | não |
| Enviar para análise | sim | sim | sim | não |
| Aprovar / declinar / reabrir | sim | sim | não | não |
| Operar logística e finalizar | sim | sim | só os seus, após aprovação | não |
| Comentar / anexar | sim | sim | sim | não |
| Cadastros | CRUD | CRUD | criar + listar | listar |
| Usuários / vínculos | sim | não | não | não |

Autorização em **um único estilo**: dependency de permissão por use case (nada de checagens manuais espalhadas).

## 4. Modelo de domínio

Cadastros (por tenant, todos com ativo/inativo e soft delete):

- **Brand (Marca)** — KODI, STALEKS; campo obrigatório do ticket e filtro em listas, dashboard e relatórios.
- **Customer** — nome, CPF/CNPJ normalizado com **constraint de unicidade no banco**, telefone, e-mail, endereço completo (lookup de CEP feito pelo backend, com timeout/fallback).
- **Product** — nome, SKU (único por tenant), descrição, foto, segmento.
- **DefectType** — valores iniciais das planilhas: danificado, adaptação/modelo errado, não recebeu, sem afiação/precisão, defeito, oxidação, quebra da ferramenta, extraviado, cancelado.
- **SolutionType** — troca pelo mesmo item, troca por outro item, envio de peça, reembolso, 50% off, 100% off, voucher.
- **PurchaseChannel (Local da compra)** — vira cadastro (hoje é texto livre): site KODI, site STALEKS, SAC, feiras, marketplaces, revendedores.

Ticket e satélites:

- **Ticket** — número por **sequence nativa do Postgres** (sem race condition), marca, cliente, atendente, supervisor, prioridade (baixa/média/alta/urgente) -> SLA, canal de compra, código do pedido, datas de compra/entrega, descrição, notas de decisão e finais, pedido de garantia + rastreio, marcos temporais (aberto, enviado à análise, aprovado/declinado, fechado, última atividade), `due_at`.
- **TicketItem** — N itens por ticket (produto + defeito + quantidade). **Fonte única de verdade** — sem campos duplicados no ticket.
- **TicketComment** — chat interno com resposta/citação. Bloqueado em ticket encerrado.
- **TicketAttachment** — ver seção 7.
- **TicketTimelineEvent** — auditoria por ticket (tipo, título, valores antigo/novo, autor, data).
- **TicketRead** — controle de lido/não lido por usuário (last_read_at vs last_activity_at).
- **ReverseCode** — códigos de logística reversa (vários por ticket).

Soft delete universal — **nunca** exclusão física de ticket (defeito do legado).

## 5. Máquina de estados do ticket

Explícita no domínio: transições válidas declaradas, cada transição é um use case com permissão própria. Nenhuma rota genérica de troca de status.

```
aberto --> aguardando_analise --> aprovado --> aguardando_envio_reverso --> produto_recebido --> finalizado
                              \-> declinado (encerrado)
laterais: aguardando_cliente (de/para aberto), cancelado (de qualquer não encerrado)
reabrir: encerrado -> aprovado (se ja houve aprovacao) ou aberto
```

Regras:

- **Abertura parcial** permitida (sem itens/descrição); completude exigida no envio para análise (cliente, ao menos um item com defeito, descrição).
- **Declinar exige motivo**; **finalizar exige solução** escolhida; aprovado também pode finalizar direto (sem reverso).
- Registrar código reverso move para `aguardando_envio_reverso`; excluir todos os reversos volta para `aprovado`.
- Pedido de garantia (código manual + rastreio) não altera status.
- SLA por prioridade: urgente 24h, alta 48h, média 72h, baixa 120h (configurável); alerta a 12h do prazo. Estados de SLA: no prazo / vence em breve / atrasado / encerrado.
- Toda transição gera evento na timeline e atualiza `last_activity_at`.

## 6. Requisitos funcionais por tela

Layout geral: sidebar esquerda com grupos por módulo, header com notificações e menu de usuário, conteúdo em cards. Design tokens, ícones Lucide, menu responsivo (mobile), modais e toasts próprios (nunca confirm/alert nativos), tabelas com ordenação e paginação.

1. **Login** — email + senha + slug do tenant; "manter sessão".
2. **Dashboard** — KPI cards clicáveis que abrem a lista pré-filtrada (total, abertos, aguardando análise, atrasados SLA, aprovados/declinados/finalizados no mês); gráficos de distribuição por status e rankings (top produtos/defeitos/soluções); tempo médio de resolução; tickets recentes. Filtro por marca.
3. **Lista de tickets** — filtros (status, marca, cliente por nome/documento, produto, pedido, prioridade, atrasados), busca, ordenação, indicador de não lido, ações por linha; linhas como links reais.
4. **Detalhe do ticket** — estrutura 2/3 + 1/3: dados (gerais, cliente com histórico, compra, itens) + anexos + chat à esquerda; à direita **uma ação primária contextual por estado** (demais ações em menu, formulários em modal/drawer), reversos, garantia e timeline com conector visual. Sem dados duplicados.
5. **Criação de ticket** — lookup de cliente por CPF/CNPJ com autofill (padrão bom do legado), CEP com autofill, autocomplete de canal de compra, marca, itens repetíveis (produto+defeito+quantidade), prioridade, descrição, anexos com drag-and-drop e preview.
6. **Cadastros** — marcas, produtos, defeitos, soluções, canais, clientes (com histórico de tickets), usuários/vínculos (só admin). Padrão único de CRUD.
7. **Relatórios** — filtros completos (período, marca, produto, defeito, solução, status, atendente, canal), KPIs, tabela paginada com links, rankings; **export CSV com os mesmos filtros da tela**.
8. **Galeria de mídias** — grid de previews com filtros (tipo, marca, produto, defeito, solução, status, período), lazy loading, lightbox, link para o ticket.
9. **Notificações** — in-app: sino com contador, eventos (atribuição, envio à análise, aprovação, declínio, comentário), preferências de popup/som por usuário. SSE/WebSocket em vez de polling.
10. **Painel da plataforma** (super_admin) — tenants (criar provisiona schema, ativar/suspender, módulos), usuários globais e vínculos, indicadores.

## 7. Anexos e mídia (Wasabi S3)

Especificação completa em `docs/armazenamento-anexos.md`. Resumo:

- Upload **direto ao Wasabi** com presigned PUT: chave gerada pelo servidor (`{tenant}/{ticket}/{uuid}`), TTL curto, restrição de content-type e tamanho; anexo nasce `pendente` e é confirmado via HEAD no objeto; pendentes expiram.
- Bucket privado, IAM restrito; download/visualização só por presigned GET curto após checagem de permissão.
- **PDFs** salvos como estão; **imagens** comprimidas acima de limites configuráveis (no client antes do upload; job recomprime o que chegar grande).
- **Previews** (thumbnail WebP + tamanho médio) gerados por worker em fila com concorrência e recursos limitados, idempotente com retry; estados sem_preview/pendente/pronto/falhou.

## 8. Requisitos não funcionais

- Segurança: argon2, rate limiting no login, verificação de ativo no login, JWT curto com refresh, CORS restrito, autorização centralizada, bucket privado, uploads validados no servidor.
- Integridade: constraints no banco (unicidade de documento, SKU, número do ticket), sequences para numeração, soft delete universal, timeline como auditoria.
- Qualidade: TDD, CI com lint + testes, testes de API contra Postgres real (testcontainers ou schema descartável), cobertura do fluxo core (o legado não tinha).
- Front: acessibilidade (focus-visible, aria, contraste), estados de loading/skeleton, progresso de upload, responsivo, dark mode preparado.
- Sem polling onde SSE/WebSocket couber (notificações, chat).

## 9. Importação das planilhas

Requisito de entrega (Fase 3): comando/endpoint que lê os CSVs KODI/STALEKS, normaliza (datas, telefones, CPFs, SKUs, canais, valores de frete), cria clientes/produtos/tickets com a marca correta, mapeia os valores de domínio (problema -> DefectType, solução -> SolutionType, status -> estado do ticket) e gera relatório de inconsistências. Estrutura das planilhas em `docs/planilhas.md`.

## 10. Fases de entrega

- **Fase 0 — Fundação**: monorepo `backend/` + `frontend/`, docker-compose (Postgres), esqueleto Clean Architecture, CI, Alembic multi-schema, auth completa (login com slug, JWT, papéis), sistema de módulos, painel da plataforma mínimo.
- **Fase 1 — Cadastros**: marcas, clientes, produtos, defeitos, soluções, canais; design system e CRUDs no front.
- **Fase 2 — Tickets (core)**: máquina de estados, itens, SLA, comentários, anexos (Wasabi), timeline; lista + detalhe + criação no front. Fase mais longa.
- **Fase 3 — Visibilidade**: dashboard com gráficos, relatórios + export, galeria de mídias, **importador das planilhas**.
- **Fase 4 — Acabamento**: notificações in-app (SSE/WS), busca global, preferências, hardening, Playwright nos fluxos críticos.

## 11. Fora de escopo / roadmap

- Módulo Eventos/patrocínios do legado (o sistema de módulos fica pronto para recebê-lo).
- Notificações ao cliente final (e-mail/WhatsApp/SMS).
- Integração Tiny ERP (campos de pedido de garantia seguem manuais).
- Planos/faturamento, domínio próprio por tenant, app mobile.

## 12. Documentos de apoio

- `docs/planilhas.md` — estrutura e valores das planilhas KODI/STALEKS (fonte dos valores de domínio e do importador).
- `docs/legado-funcionamento.md` — regras de negócio do legado e defeitos estruturais a não repetir.
- `docs/legado-ui.md` — layout e telas do legado; o que preservar e o que corrigir no redesign.
- `docs/proposta-alto-nivel.md` — proposta original consolidada neste PRD.
- `docs/armazenamento-anexos.md` — especificação completa do fluxo de anexos no Wasabi.
