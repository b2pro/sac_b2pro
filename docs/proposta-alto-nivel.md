# Proposta de alto nível — SAC-B2PRO

> Documento de apoio: esta proposta foi consolidada em `docs/PRD.md`, que é a fonte de verdade do produto.

Refazer profissionalmente o que o SAC-Tickets (Laravel vibe-codado) faz hoje, automatizando o fluxo das planilhas de trocas e defeitos (KODI e STALEKS). Referências: `docs/planilhas.md`, `docs/legado-funcionamento.md`, `docs/legado-ui.md`.

## 1. Visão do produto

Plataforma SaaS multi-organização de SAC focada em trocas, defeitos e garantias:
registro da reclamação -> análise/aprovação -> logística (reverso, pedido de garantia, rastreio) -> conclusão, com SLA, auditoria completa e relatórios. Cada marca/empresa opera isolada (tenant), com usuários globais que podem atuar em mais de um tenant.

## 2. Arquitetura

### Backend — Python, FastAPI, Clean Architecture

```
backend/src/
  domain/          entidades, value objects, enums, máquina de estados, regras puras
  application/     use cases (um por ação de negócio), ports (interfaces de repositório/serviços)
  infrastructure/  SQLAlchemy (models, repositórios), Alembic, storage de arquivos, e-mail, auth JWT
  interface/       routers FastAPI, schemas Pydantic, dependências, middleware de tenant
```

- Domínio sem dependência de framework; dependências apontam para dentro; use cases testados sem banco.
- TDD obrigatório (pytest; testes de domínio/use case unitários, testes de API com banco Postgres efêmero via testcontainers ou schema descartável).
- PostgreSQL, SQLAlchemy 2 async + Alembic. Uvicorn.

### Multi-tenancy — schema por tenant no Postgres

- Schema `public` (global): `tenants` (slug, nome, status, módulos), `users` (globais, e-mail único global), `user_tenants` (vínculo usuário-tenant com papel por tenant).
- Schema `t_<slug>` por tenant: todas as tabelas de negócio (customers, products, tickets etc.). Sem coluna `tenant_id` espalhada — o isolamento é físico, por `search_path` resolvido pelo middleware a partir do JWT.
- Alembic com migração dupla: uma árvore para o `public`, outra aplicada a todos os schemas de tenant; criação de tenant provisiona o schema automaticamente.
- Login: `email + senha + slug do tenant` -> valida vínculo em `user_tenants` -> JWT com user, tenant e papel. Rate limiting no login, verificação de usuário/tenant ativos no próprio login (defeito do legado), hash argon2.
- Papéis por tenant (mantidos do legado): admin, supervisor, atendente, visualizador; super_admin global para o painel da plataforma. Autorização num único estilo (dependency de permissão por use case).

### Frontend — React + TypeScript + Vite

- Layout inspirado no legado (sidebar esquerda com grupos, header com notificações e usuário, conteúdo em cards), profissionalizado: design tokens, ícones Lucide (proibido emoji), Tailwind compilado, menu responsivo/mobile, modais e toasts próprios, dark mode preparado.
- TanStack Query para dados, React Router, react-hook-form + zod nos formulários, tabelas com ordenação/paginação/colunas configuráveis, gráficos no dashboard (distribuição por status, top defeitos/produtos).
- Testes E2E com Playwright quando necessário.

## 3. Domínio (núcleo)

- **Customer**: cadastro único por tenant, documento normalizado com constraint de unicidade no banco, endereço com lookup de CEP feito pelo backend (com timeout/fallback).
- **Product** (SKU único), **DefectType**, **SolutionType**, **PurchaseChannel** (local da compra vira cadastro — hoje é texto livre nas planilhas), **Brand (Marca)**: KODI e STALEKS convivem no mesmo tenant; a marca é um cadastro e um campo do ticket (e filtro em listas, dashboard e relatórios).
- **Ticket (Reclamação)**: numeração por sequence nativa do Postgres por tenant (elimina race condition), cliente, atendente, supervisor, prioridade -> SLA, dados da compra (canal, pedido, datas), descrição.
  - **TicketItem**: N produtos+defeito+quantidade por ticket (fonte única de verdade — sem a duplicação do legado).
  - **Máquina de estados explícita** no domínio (transições válidas declaradas, cada transição é um use case):
    `aberto -> aguardando_analise -> aprovado|declinado`; `aprovado -> aguardando_envio_reverso -> produto_recebido -> finalizado`; laterais `aguardando_cliente`, `cancelado`, reabertura controlada. Declínio exige motivo; conclusão exige solução.
  - Logística: códigos reversos, pedido de garantia + rastreio (campos manuais como hoje; integração Tiny ERP fica para fase futura).
  - Comentários internos com resposta/citação; anexos (imagens e PDFs) no **Wasabi S3** com upload direto por presigned URL, compressão de imagens acima do limite e previews gerados por job — ver `docs/armazenamento-anexos.md`; timeline de auditoria; controle de lido/não lido.
  - Soft delete real em tudo (nunca forceDelete).
- **Importador de planilhas**: comando/endpoint que lê os CSVs (KODI/STALEKS), normaliza (datas, telefones, CPFs, SKUs, canais), cria clientes/produtos/tickets e reporta inconsistências — é a migração dos dados atuais e o teste de fogo do modelo.

## 4. Telas (paridade com o legado, melhoradas)

1. Login (email + senha + slug do tenant).
2. Dashboard: KPIs clicáveis que filtram a lista (padrão bom do legado), gráficos de status e rankings, tempo médio de resolução.
3. Tickets: lista com filtros persistentes, ordenação, busca global, indicador de não lido; detalhe em 2/3 + 1/3 com uma ação primária contextual por estado (em vez da pilha de formulários coloridos), chat, anexos com drag-and-drop e preview, timeline com conector visual.
4. Criação de ticket: lookup de cliente por CPF/CNPJ com autofill (manter), autocomplete de canal de compra, itens repetíveis, anexos.
5. Cadastros: produtos, defeitos, soluções, canais, clientes (com histórico), usuários/vínculos.
6. Relatórios: filtros completos aplicados também no export CSV, com links e paginação.
7. Galeria de mídias; preferências de notificação; painel da plataforma (tenants, usuários globais).

Fora do escopo inicial: módulo Eventos/patrocínios do legado — porém o **sistema de módulos** (feature flags por tenant, como `module_tickets`/`module_events` do legado, refletidos no menu e nas rotas) é construído desde o início para recebê-lo depois. Também fora por enquanto: notificações ao cliente final por e-mail/WhatsApp (SAC é só interno) e integração Tiny (roadmap).

## 5. Fases de entrega

- **Fase 0 — Fundação**: monorepo `backend/` + `frontend/`, docker-compose (Postgres), esqueleto clean arch, CI (lint, testes), Alembic multi-schema, auth completa (login com slug, JWT, papéis), painel plataforma mínimo (criar tenant provisiona schema).
- **Fase 1 — Cadastros**: customers, products, defect/solution types, canais; CRUDs no front com o design system estabelecido.
- **Fase 2 — Tickets (core)**: máquina de estados, itens, SLA, comentários, anexos, timeline, lista+detalhe+criação no front. É a fase mais longa.
- **Fase 3 — Visibilidade**: dashboard com gráficos, relatórios + export, galeria de mídias, importador das planilhas (migração dos dados reais).
- **Fase 4 — Acabamento**: notificações in-app (SSE/WebSocket em vez de polling), busca global, preferências, hardening (rate limit, auditoria de acesso), Playwright nos fluxos críticos.

## 6. Decisões tomadas (2026-07-27)

1. **Um tenant só** para a operação atual: KODI e STALEKS compartilham o tenant e a marca é um campo/cadastro do ticket. A arquitetura multi-schema permanece para novos clientes/organizações.
2. **Eventos fica de fora** por agora, mas o sistema de módulos por tenant é implementado desde o início.
3. **SAC apenas interno**: nenhuma notificação ao cliente final por enquanto.
4. **Anexos no Wasabi S3** com upload direto assinado, compressão de imagens e previews por job — especificação em `docs/armazenamento-anexos.md`.
