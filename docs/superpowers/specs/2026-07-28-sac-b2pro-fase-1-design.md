# Design — SAC-B2PRO Fase 1 (Cadastros)

Data: 2026-07-28. Status: aprovado pelo usuario em 2026-07-28. Fontes: `docs/PRD.md` (secoes 4 e 10), `docs/planilhas.md`, `docs/legado-funcionamento.md`, seeder do legado (`../SAC-Tickets/database/seeders/TenantSeeder.php`), design da Fase 0.

## Objetivo

Entregar os cadastros por tenant (Marca, Cliente, Produto, Defeito, Solucao, Canal de compra) com CRUD completo no backend e no frontend, ativando de verdade o isolamento multi-tenant por schema (primeiras tabelas de negocio). Fora de escopo: tickets (Fase 2), importador (Fase 3), historico de tickets do cliente (Fase 2).

## Decisoes fechadas com o usuario (2026-07-28)

- Cadastro de produto e catalogo, com foto de catalogo OPCIONAL (como no legado e no PRD). Na Fase 1 a tabela ja nasce com a coluna `photo_key` (nullable); o upload e a exibicao entram na Fase 2 junto com a infra Wasabi (presigned URL), evitando storage provisorio. Fotos de itens defeituosos sao outra coisa: anexos do ticket (Fase 2).
- Seeds hibridos: valores iniciais consolidados das planilhas + seeder do legado, criados no provisionamento e editaveis pela UI.
- Cadastros sao core: SEM gate de modulo (feature flags ficam para modulos realmente opcionais, ex.: Eventos).

## Abordagem

Catalogo generico + especificos: Marca, Defeito, Solucao e Canal sao todos "nome + descricao + ativo" e compartilham um unico mecanismo generico (entidade, use cases, repositorio, router e pagina parametrizados por tipo). Cliente e Produto tem regras proprias e ganham implementacao dedicada. Alternativas descartadas: seis CRUDs copiados (repeticao) e engine metadata-driven total (over-engineering).

## 1. Tenancy de verdade (divida da Fase 0)

- Models de negocio em `models_tenant.py` sobre `TenantBase`, com `__table_args__ = {"schema": "tenant"}` (schema simbolico).
- Migration `0002` na arvore tenant cria as 6 tabelas; `migrate tenants` aplica em todos os schemas `t_*` existentes; tenant novo ja nasce com elas (provisionamento roda head).
- Nova dependency `get_tenant_session`: exige `tenant_slug` no JWT (401 se ausente) e monta a session com `execution_options(schema_translate_map={"tenant": "t_<slug>"})`. Toda rota de cadastro usa essa session.

## 2. Modelo de dados (schema do tenant)

Todas as tabelas com `id UUID`, `active bool`, `created_at/updated_at`, `deleted_at` (soft delete preparado; NAO ha exclusao fisica nem endpoint de delete — "inativar" e o caminho).

- `brands`, `defect_types`, `solution_types`, `purchase_channels` — mesmas colunas: `name` (unique por tabela), `description` (opcional).
- `products` — `name`, `sku` (unique), `segment` (texto livre, opcional), `description` (opcional), `photo_key` (opcional; preenchido a partir da Fase 2 com a chave do objeto no Wasabi).
- `customers` — `name`, `document` (CPF/CNPJ so digitos, unique), `phone` (so digitos, opcional), `email` (opcional), endereco: `cep`, `street`, `number`, `complement`, `neighborhood`, `city`, `state` (UF, 2 chars) — todos opcionais.

Unicidades como constraint no banco (unique index), com `ConflictError` mapeado de `IntegrityError` (padrao da Fase 0).

## 3. Dominio e application

- `CatalogItem` (id, name, description, active, deleted_at) + `CatalogKind` (enum: brand, defect_type, solution_type, purchase_channel).
- Use cases do catalogo (parametrizados por kind): listar (busca por nome, filtro ativo), criar (nome obrigatorio, unico -> ConflictError), atualizar, ativar/inativar (NotFoundError quando nao existe).
- `Customer`: validacao de documento com digitos verificadores (CPF 11 digitos, CNPJ 14 — algoritmo classico, funcao pura no dominio, testada com casos validos/invalidos), normalizacao de documento/telefone para digitos, UF em lista valida. Use cases: listar (busca por nome OU documento normalizado, paginado), criar, atualizar, ativar/inativar.
- `Product`: SKU obrigatorio e unico; use cases equivalentes aos do cliente (busca por nome/SKU, paginado).
- Permissoes (matriz do PRD): listar -> `LISTAR_CADASTROS`; criar -> `CRIAR_LISTAR_CADASTROS`; editar/inativar -> `GERENCIAR_CADASTROS`. Ajuste na matriz da Fase 0: ATENDENTE ganha tambem `LISTAR_CADASTROS` (a matriz sempre disse "criar + listar"; o enum separado impedia o listar).

## 4. API

Rotas sob `/api/cadastros`, autorizacao via `require_permission` + `get_tenant_session`:

- Genericas (4x, mesmo shape): `GET/POST /api/cadastros/{marcas|defeitos|solucoes|canais}`, `PUT /{id}`, `PATCH /{id}/active`. GET aceita `search` e `active`; retorna lista completa (listas curtas, sem paginacao).
- `GET/POST /api/cadastros/clientes`, `PUT /{id}`, `PATCH /{id}/active` — GET com `search` (nome ou documento), `page`, `per_page` (default 20, max 100), resposta `{items, total, page, per_page}`.
- `GET/POST /api/cadastros/produtos`, `PUT /{id}`, `PATCH /{id}/active` — GET com `search` (nome ou SKU), paginado igual.
- `GET /api/cep/{cep}` — backend consulta ViaCEP com httpx (vira dependencia de runtime), timeout 3s; resposta normalizada `{cep, street, neighborhood, city, state}`; CEP mal formatado -> 422; nao encontrado -> 404; ViaCEP fora -> 503 `{code: "cep_indisponivel"}`. O front trata 4xx/5xx deixando preencher manualmente (fallback exigido pelo PRD).

## 5. Seeds hibridos (planilhas + legado, deduplicados, editaveis)

Aplicados ao provisionar tenant novo e via comando idempotente `uv run python -m sac.infrastructure.seed_tenant <slug>` para tenants existentes (compara por nome; nao recria nem reativa o que ja existe).

- Marcas: KODI, STALEKS.
- Defeitos (descricoes do seeder legado onde existem): Danificado; Adaptacao/modelo errado; Nao recebeu; Sem afiacao/precisao; Defeito de fabricacao; Oxidacao; Quebra da ferramenta; Extraviado; Cancelado; Arrependimento de compra; Produto divergente; Embalagem vazia; Mau uso; Fora do prazo.
- Solucoes: Troca pelo mesmo item; Troca por outro item; Envio de peca; Reembolso; 50% off; 100% off; Voucher; Desconto em nova compra; Orientado procurar marketplace/transportadora; Encaminhado para afiacao.
- Canais: Site KODI; Site STALEKS; SAC; Beauty Show; Mercado Livre; Shopee; Revendedor.

## 6. Frontend

- Sidebar ganha grupo **Cadastros** (Marcas, Produtos, Defeitos, Solucoes, Canais, Clientes) visivel para papeis de tenant (nao para super admin puro).
- `CatalogPage` generica configurada por tipo: tabela (nome, descricao, badge de status), busca, dialog criar/editar, switch ativar/inativar. Visualizador ve tudo somente leitura (sem botoes de acao); atendente ve criar mas nao editar/inativar.
- **ProdutosPage**: colunas nome, SKU (`font-mono`), segmento, status; form com nome/SKU/segmento/descricao; busca; paginacao. Upload da foto de catalogo entra na Fase 2 (infra Wasabi).
- **ClientesPage**: colunas nome, documento formatado (`font-mono`), telefone, cidade/UF, status; busca por nome/documento; form com mascara de CPF/CNPJ e telefone, CEP com autofill via `/api/cep` (loading no campo, fallback manual em erro); paginacao.
- Todo trabalho segue o skill frontend-design e `docs/identidade-visual.md` (tabelas densas, dado tecnico em mono, Paprika so na acao primaria, empty states de texto direto).

## 7. Erros e testes

- Mesmo handler unico da Fase 0: 409 nome/SKU/documento duplicado; 422 documento/CEP/UF invalidos; 404 registro inexistente; 403 permissao; 401 sem tenant no token.
- TDD. Unit: validador de CPF/CNPJ (casos validos, invalidos, digitos repetidos), use cases com fakes (catalogo generico, cliente, produto), normalizacoes.
- Integracao: fixtures novas — helper que provisiona tenant real + emite token de tenant por papel; testes por router (CRUD feliz, conflitos, permissoes por papel: visualizador nao cria, atendente nao edita); **teste de isolamento**: registro criado no tenant A nao aparece listado no tenant B; `/api/cep` testado com stub do ViaCEP (sem rede em teste).

## 8. Mudancas em codigo existente

- `domain/permissions.py`: ATENDENTE += LISTAR_CADASTROS (teste da matriz atualizado).
- `infrastructure/provisioning.py`: apos migrar, aplica seeds de cadastros.
- `interface/deps.py`: nova `get_tenant_session`.
- `frontend/src/components/layout/Sidebar.tsx`: grupo Cadastros por papel.
- `backend/pyproject.toml`: httpx passa de dev para dependencia de runtime.
