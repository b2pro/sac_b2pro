# Medição dos índices do schema de tenant

Registro da medição que produziu a migration `0007_indices_parciais`
(2026-07-31). O objetivo deste documento é que a próxima pessoa a mexer em
índice de tenant **não precise refazer o trabalho às cegas**: aqui estão a massa
que gerou os números, as distribuições escolhidas e por quê, os planos antes e
depois, e a decisão sobre cada índice amarrada ao número que a sustenta.

Regra que saiu daqui e vale para a próxima vez: **medição de índice em base
pequena não decide nada**. A rodada anterior mediu no tenant `e2e`, com 738
tickets, e concluiu que `ix_tickets_deleted_at_status` era inútil. Em 100 mil
tickets ele é escolhido pelo planner em quatro consultas.

## 1. Como reproduzir a massa

Schema descartável, **nunca** um tenant real e **nunca** um seed commitado — é
instrumento de medição, não fixture. Não use o tenant `e2e`: a suíte e2e depende
dele.

```bash
# 1) provisionar (dentro de backend/) — traz migrations + seeds padrão
uv run python - <<'PY'
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sac.infrastructure.provisioning import AlembicTenantProvisioner
from sac.infrastructure.settings import Settings

async def main():
    engine = create_async_engine(Settings().database_url)
    p = AlembicTenantProvisioner(engine)
    await p.drop("t_bench")
    await p.provision("t_bench")
    await engine.dispose()

asyncio.run(main())
PY

# 2) popular
docker exec -i sac-b2pro-db-1 psql -U sac -d sac -v ON_ERROR_STOP=1 < massa.sql

# 3) derrubar ao final (mesmo script do passo 1, só com p.drop)
```

### Duas armadilhas que custaram tempo

1. **`random()` dentro de `CROSS JOIN LATERAL` sem referenciar a linha externa
   é avaliado UMA vez.** O Postgres trata a subconsulta como constante e a iça
   para fora. O resultado foi 1 item por ticket em 100% dos casos e **zero**
   anexos. A solução foi trocar `random()` por `bench_rand(semente_da_linha)`,
   um hash md5 `IMMUTABLE` que depende da linha — com o efeito colateral útil de
   tornar a massa reprodutível bit a bit, sem depender de `setseed`.
2. **Sem `ANALYZE` a medição não vale nada.** Sem estatística o planner chuta, e
   o plano que você mede não é o plano que a produção terá.

### `massa.sql`

```sql
\set ON_ERROR_STOP on
SET search_path TO t_bench, public;

CREATE OR REPLACE FUNCTION t_bench.bench_rand(seed text)
RETURNS double precision LANGUAGE sql IMMUTABLE AS $$
    SELECT ((('x' || substr(md5(seed), 1, 8))::bit(32)::bigint & 4294967295)::double precision)
           / 4294967296.0
$$;

INSERT INTO customers (id, name, document, phone, email, city, state, active, created_at, updated_at)
SELECT gen_random_uuid(), 'Cliente ' || i, lpad(i::text, 11, '0'),
       '11' || lpad((900000000 + i)::text, 9, '0'), 'cliente' || i || '@exemplo.com.br',
       (ARRAY['Sao Paulo','Rio de Janeiro','Belo Horizonte','Curitiba','Porto Alegre','Salvador','Recife','Fortaleza'])[1 + (i % 8)],
       (ARRAY['SP','RJ','MG','PR','RS','BA','PE','CE'])[1 + (i % 8)],
       true, now(), now()
FROM generate_series(1, 40000) AS i;

INSERT INTO products (id, name, sku, segment, description, active, created_at, updated_at)
SELECT gen_random_uuid(), 'Produto ' || i, 'SKU-' || lpad(i::text, 5, '0'),
       (ARRAY['Alicates','Tesouras','Pincas','Lixas','Acessorios'])[1 + (i % 5)],
       'Item de catalogo usado na massa de medicao.', true, now(), now()
FROM generate_series(1, 800) AS i;

CREATE TABLE t_bench.bench_ref AS
SELECT (SELECT array_agg(id ORDER BY name) FROM brands)            AS brand_ids,
       (SELECT array_agg(id ORDER BY name) FROM solution_types)    AS solution_ids,
       (SELECT array_agg(id ORDER BY name) FROM purchase_channels) AS channel_ids,
       (SELECT array_agg(id ORDER BY name) FROM defect_types)      AS defect_ids,
       (SELECT array_agg(id ORDER BY sku)  FROM products)          AS product_ids,
       (SELECT array_agg(id ORDER BY document) FROM customers)     AS customer_ids,
       (SELECT array_agg(('00000000-0000-4000-8000-' || lpad(g::text, 12, '0'))::uuid)
          FROM generate_series(1, 12) g)                           AS attendant_ids;

INSERT INTO tickets (
    id, number, brand_id, customer_id, attendant_user_id, supervisor_user_id,
    status, priority, purchase_channel_id, order_code, purchase_date, delivery_date,
    description, decision_notes, final_notes, solution_type_id,
    warranty_order_code, warranty_tracking_code,
    opened_at, submitted_at, approved_at, declined_at, closed_at,
    last_activity_at, due_at, created_at, updated_at, deleted_at)
SELECT
    gen_random_uuid(), s.i,
    r.brand_ids[CASE WHEN bench_rand(s.i || 'brand') < 0.65 THEN 1 ELSE 2 END],
    CASE WHEN bench_rand(s.i || 'custnull') < 0.02 THEN NULL
         ELSE r.customer_ids[1 + floor(power(bench_rand(s.i || 'cust'), 1.6) * 40000)::int] END,
    r.attendant_ids[1 + floor(power(bench_rand(s.i || 'att'), 2.2) * 12)::int],
    NULL, p.status, p.priority,
    r.channel_ids[1 + floor(power(bench_rand(s.i || 'chan'), 1.8) * 7)::int],
    CASE WHEN bench_rand(s.i || 'order') < 0.85 THEN 'PED-' || lpad(s.i::text, 8, '0') END,
    (o.opened_at - interval '12 days')::date, (o.opened_at - interval '5 days')::date,
    CASE WHEN bench_rand(s.i || 'desc') < 0.9 THEN
        'Cliente relatou problema no produto recebido. '
        || repeat('Detalhe do atendimento registrado pelo atendente. ', 4)
        || 'Protocolo ' || s.i END,
    CASE WHEN p.status IN ('aprovado','aguardando_envio_reverso','produto_recebido','finalizado','declinado')
         THEN repeat('Analise tecnica concluida sobre o item relatado. ', 2) END,
    CASE WHEN p.status = 'finalizado'
         THEN repeat('Solucao aplicada e confirmada com o cliente. ', 2) END,
    CASE WHEN p.status IN ('aprovado','aguardando_envio_reverso','produto_recebido','finalizado')
         THEN r.solution_ids[1 + floor(power(bench_rand(s.i || 'sol'), 1.5) * 10)::int] END,
    CASE WHEN p.status IN ('aguardando_envio_reverso','produto_recebido','finalizado')
         THEN 'GAR-' || lpad(s.i::text, 8, '0') END,
    CASE WHEN p.status IN ('produto_recebido','finalizado')
         THEN 'BR' || lpad(s.i::text, 9, '0') || 'BR' END,
    o.opened_at,
    CASE WHEN p.status <> 'aberto' THEN LEAST(o.opened_at + d.dur * 0.2, now()) END,
    CASE WHEN p.status IN ('aprovado','aguardando_envio_reverso','produto_recebido','finalizado')
         THEN e.decided_at END,
    CASE WHEN p.status = 'declinado' THEN e.decided_at END,
    CASE WHEN p.status IN ('finalizado','declinado','cancelado') THEN e.ended_at END,
    CASE WHEN p.status IN ('finalizado','declinado','cancelado') THEN e.ended_at
         ELSE LEAST(o.opened_at + d.dur * 0.6, now()) END,
    o.opened_at + (CASE p.priority WHEN 'urgente' THEN 24 WHEN 'alta' THEN 48
                                   WHEN 'media' THEN 72 ELSE 120 END) * interval '1 hour',
    o.opened_at,
    COALESCE(CASE WHEN p.status IN ('finalizado','declinado','cancelado') THEN e.ended_at END, o.opened_at),
    CASE WHEN bench_rand(s.i || 'del') < 0.01 THEN LEAST(o.opened_at + interval '20 days', now()) END
FROM generate_series(1, 100000) AS s(i)
CROSS JOIN bench_ref r
CROSS JOIN LATERAL (
    SELECT now() - (power(bench_rand(s.i || 'op'), 1.4) * (interval '1095 days')) AS opened_at) o
CROSS JOIN LATERAL (
    SELECT CASE
        WHEN bench_rand(s.i || 'status') < 0.45 THEN 'finalizado'
        WHEN bench_rand(s.i || 'status') < 0.57 THEN 'declinado'
        WHEN bench_rand(s.i || 'status') < 0.67 THEN 'aberto'
        WHEN bench_rand(s.i || 'status') < 0.75 THEN 'aguardando_analise'
        WHEN bench_rand(s.i || 'status') < 0.82 THEN 'aguardando_cliente'
        WHEN bench_rand(s.i || 'status') < 0.88 THEN 'aprovado'
        WHEN bench_rand(s.i || 'status') < 0.93 THEN 'aguardando_envio_reverso'
        WHEN bench_rand(s.i || 'status') < 0.97 THEN 'produto_recebido'
        ELSE 'cancelado' END AS status,
      CASE
        WHEN bench_rand(s.i || 'prio') < 0.20 THEN 'baixa'
        WHEN bench_rand(s.i || 'prio') < 0.70 THEN 'media'
        WHEN bench_rand(s.i || 'prio') < 0.92 THEN 'alta'
        ELSE 'urgente' END AS priority) p
CROSS JOIN LATERAL (
    SELECT (1 + power(bench_rand(s.i || 'dur'), 1.8) * 45) * interval '1 day' AS dur) d
CROSS JOIN LATERAL (
    SELECT LEAST(o.opened_at + d.dur, now())       AS ended_at,
           LEAST(o.opened_at + d.dur * 0.4, now()) AS decided_at) e;

SELECT setval('t_bench.ticket_number_seq', 100000);

INSERT INTO ticket_items (id, ticket_id, product_id, defect_type_id, quantity, seq, created_at, updated_at)
SELECT gen_random_uuid(), t.id,
       r.product_ids[1 + floor(power(bench_rand(t.id || 'prod' || g), 2.0) * 800)::int],
       r.defect_ids[1 + floor(power(bench_rand(t.id || 'def' || g), 1.7) * 14)::int],
       1 + floor(power(bench_rand(t.id || 'qty' || g), 3.0) * 4)::int,
       row_number() OVER (), t.opened_at, t.opened_at
FROM tickets t CROSS JOIN bench_ref r
CROSS JOIN LATERAL generate_series(1, 1 + floor(power(bench_rand(t.id || 'n'), 2.2) * 3)::int) AS g;

SELECT setval('t_bench.ticket_item_seq', (SELECT count(*) + 1 FROM ticket_items));

INSERT INTO ticket_attachments (
    id, ticket_id, filename, content_type, size_bytes, object_key, kind, status,
    preview_key, preview_medium_key, preview_status, author_user_id,
    created_at, confirmed_at, deleted_at)
SELECT gen_random_uuid(), t.id,
    'anexo-' || g || CASE WHEN a.rk < 0.80 THEN '.jpg' WHEN a.rk < 0.95 THEN '.pdf' ELSE '.mp4' END,
    CASE WHEN a.rk < 0.80 THEN 'image/jpeg' WHEN a.rk < 0.95 THEN 'application/pdf' ELSE 'video/mp4' END,
    50000 + floor(bench_rand(t.id || 'size' || g) * 4000000)::bigint,
    't_bench/' || t.id || '/anexo-' || g,
    CASE WHEN a.rk < 0.80 THEN 'imagem' WHEN a.rk < 0.95 THEN 'pdf' ELSE 'video' END,
    CASE WHEN a.rs < 0.92 THEN 'disponivel' WHEN a.rs < 0.97 THEN 'pendente' ELSE 'expirado' END,
    CASE WHEN a.rk < 0.80 THEN 't_bench/' || t.id || '/prev-' || g END,
    CASE WHEN a.rk < 0.80 THEN 't_bench/' || t.id || '/prevm-' || g END,
    CASE WHEN a.rk < 0.80 THEN 'pronto' ELSE 'sem_preview' END,
    t.attendant_user_id, t.opened_at + interval '2 hours', t.opened_at + interval '2 hours',
    CASE WHEN a.rd < 0.02 THEN t.opened_at + interval '30 days' END
FROM tickets t
CROSS JOIN LATERAL generate_series(1, 1 + floor(power(bench_rand(t.id || 'na'), 2.0) * 5)::int) AS g
CROSS JOIN LATERAL (SELECT bench_rand(t.id || 'kind' || g) AS rk,
                           bench_rand(t.id || 'st' || g)   AS rs,
                           bench_rand(t.id || 'del' || g)  AS rd) a
WHERE bench_rand(t.id || 'hasatt') < 0.60;

INSERT INTO ticket_reads (ticket_id, user_id, last_read_at)
SELECT t.id, t.attendant_user_id, t.last_activity_at - interval '1 hour'
FROM tickets t WHERE bench_rand(t.id || 'read1') < 0.55 ON CONFLICT DO NOTHING;
INSERT INTO ticket_reads (ticket_id, user_id, last_read_at)
SELECT t.id, '00000000-0000-4000-8000-000000000001'::uuid, t.last_activity_at - interval '2 hours'
FROM tickets t WHERE bench_rand(t.id || 'read2') < 0.30 ON CONFLICT DO NOTHING;

ANALYZE t_bench.tickets;
ANALYZE t_bench.ticket_items;
ANALYZE t_bench.ticket_attachments;
ANALYZE t_bench.ticket_reads;
ANALYZE t_bench.customers;
ANALYZE t_bench.products;
```

## 2. Distribuições, e por que cada uma

| Tabela | Linhas | Por que assim |
|---|---:|---|
| `tickets` | 100.000 | ordem de grandeza de produção |
| `ticket_items` | 156.016 | 1 a 4 por ticket, média 1,56 — o ticket típico tem um item só |
| `ticket_attachments` | 135.269 | 60% dos tickets têm anexo, 1 a 5 cada |
| `ticket_reads` | 79.982 | a lista e a tabela do relatório fazem LEFT JOIN aqui; sem massa o join sai de graça e engana |
| `customers` | 40.000 | cardinalidade alta o bastante para o planner não tratar `customer_id` como quase-constante |
| `products` | 800 | catálogo plausível de KODI + STALEKS |

Dentro de `tickets`:

- **status enviesado** (`finalizado` 44.809, `declinado` 11.963, `aberto`
  10.116, e cauda curta nos intermediários). Massa uniforme — 11% em cada
  status — faria o planner achar *todo* status seletivo, e o resultado não
  transferiria para produção.
- **`deleted_at` em 0,98% das linhas.** É esse número que decide a questão do
  índice parcial: soft delete é raro, então `deleted_at IS NULL` não seleciona
  nada.
- **`opened_at` em 3 anos, com expoente 1,4 sobre uniforme** para concentrar no
  passado recente — o SAC cresce, há mais tickets deste ano que de 2023.
- **marca 65/35** (só duas categorias, por decisão de produto).
- **atendente com expoente 2,2** sobre 12 usuários: poucos concentram a fila.
- **linha larga**: `description` com ~260 caracteres em 90% dos tickets. Isso
  importa mais do que parece — o heap de 59 MB / 7.515 páginas é o que torna o
  Seq Scan caro o bastante para o planner considerar índice. Massa "magra" faz
  Seq Scan vencer artificialmente.

## 3. Como medir o SQL certo

**Não reescreva a query à mão.** A rodada anterior mediu aproximações e por isso
errou. O que funciona: um listener `before_cursor_execute` no engine (com
`schema_translate_map` apontando para o schema descartável) grava o statement
final e os parâmetros de cada consulta que os repositórios emitem; depois cada
statement é reexecutado como `EXPLAIN (ANALYZE, BUFFERS) <statement>` com os
mesmos parâmetros.

Cobertura desta rodada: `SqlReportingRepository.dashboard` (com e sem filtro de
marca), `.report` (sem período, com período, restrito a um atendente),
`.export_rows`, `.list_media`, e `SqlTicketRepository.list` em 7 variantes —
39 statements no cenário base e 47 nas variantes filtradas.

## 4. Resultado: decisão por índice

### `tickets` — `deleted_at` vira predicado, não coluna líder

Toda consulta de ticket filtra `deleted_at IS NULL` (`_base_stmt`,
`_report_stmt`, `_media_stmt` e `_conditions` adicionam a condição
incondicionalmente), mas 99% das linhas a satisfazem. Como **coluna líder** de
b-tree isso custa 8 bytes por entrada e entrega zero seletividade; como
**predicado parcial** custa zero e ainda dispensa ir ao heap só para reconferir
a coluna.

| Índice antes | Depois | Número que sustenta |
|---|---|---|
| `ix_tickets_status` + `ix_tickets_deleted_at_status` | `ix_tickets_status` parcial | os dois eram usados; o parcial faz o mesmo e `GROUP BY status` cai de 23,4 ms para 13,0 ms. 1.448 KB → 704 KB |
| `ix_tickets_deleted_at_opened_at` | `ix_tickets_opened_at` parcial | destrava Index Scan + Incremental Sort no `ORDER BY opened_at DESC, id`: tabela do relatório 143,6 ms → 0,43 ms; export CSV 178,4 ms → 29,4 ms (some o merge externo de 24 MB). 3.104 KB → 2.184 KB |
| `ix_tickets_deleted_at_brand_id` | `ix_tickets_brand_id` parcial | não filtra (só há duas marcas), mas cobre a contagem do dashboard por marca: **8,0 ms com, 42,9 ms sem** |
| `ix_tickets_deleted_at_closed_at` | **removido** | nenhum plano o escolheu em 86 medições. O tempo médio de resolução entra por status, e `closed_at IS NOT NULL` não filtra nada dentro de `finalizado` |
| `ix_tickets_last_activity_at`, `_due_at`, `_customer_id`, `_attendant_user_id` | os mesmos, parciais | todos usados; o ganho é de plano, não de tamanho: a contagem por atendente sai de Bitmap Heap Scan (9,6 ms, ~2.000 buffers) para Index Only Scan (0,97 ms, 11 buffers) |

Nunca houve índice de `approved_at`/`declined_at`, e não deve haver: no
dashboard essas colunas só aparecem dentro de `count(*) FILTER (...)`, que é
avaliado linha a linha **depois** da varredura e nunca vira predicado de índice.

### `ticket_attachments` — aqui o parcial estaria ERRADO

`ix_ticket_attachments_deleted_at_status_created_at` e
`ix_ticket_attachments_status` viraram um só, `(status, created_at)`, **sem**
predicado parcial:

1. O varredor de anexos pendentes (`list_pending_before`, do worker) filtra
   `status = 'pendente' AND created_at < :momento` **sem** `deleted_at`. Um
   índice parcial em `deleted_at IS NULL` seria inalcançável para ele.
2. Com `status` como prefixo, o mesmo índice serve a galeria (index cond por
   status, ordenação por `created_at`) e o varredor.

Galeria: 107,5 ms → 0,58 ms (12.683 buffers → 69). Varredor: 11,9 ms → 5,4 ms.

**A lição a levar:** não é o percentual de linhas excluídas que decide se o
índice deve ser parcial — é se **toda** consumidora do índice carrega o
predicado. Em `tickets` carrega; em `ticket_attachments` não.

### O que ficou como está

`ix_ticket_attachments_ticket_id` e `ix_ticket_items_ticket_id` são usados e já
single-column; `ticket_items` nem tem `deleted_at`. Em anexos, o parcial
economizaria 2% e criaria risco desnecessário para a checagem de FK.

Nenhum índice novo foi criado para consulta que ainda não existe. As duas
consultas que seguem sem índice — lista de atrasados (`due_at < now()`, 13% das
linhas) e os três rankings (agregam a base inteira) — são Seq Scan porque a
seletividade não existe.

## 5. Antes e depois

Leitura, com `EXPLAIN (ANALYZE, BUFFERS)` em 100 mil tickets:

| Query | Antes | Depois |
|---|---:|---:|
| dashboard: 7 KPIs colapsados | 45,6 ms | 34,6 ms |
| dashboard: `GROUP BY status` | 23,4 ms | 13,0 ms |
| dashboard: rankings (produtos/defeitos/soluções) | 100-135 ms | 79-107 ms |
| dashboard: tempo médio de resolução | 65,7 ms | 37,6 ms |
| dashboard por marca: contagem | 6,8 ms | 8,0 ms |
| relatório: contagens | 1,8-15,4 ms | 1,5-10,2 ms |
| relatório: rankings | 102-160 ms | 68-113 ms |
| **relatório: tabela paginada** | **143,6 ms** | **0,43 ms** |
| **relatório com período: tabela** | **49,2 ms** | **0,32 ms** |
| **export CSV (5.000 linhas)** | **178,4 ms** | **29,4 ms** |
| galeria: contagem | 98,2 ms | 75,8 ms |
| **galeria: página de 24** | **107,5 ms** | **0,58 ms** |
| **lista/relatório por atendente: contagem** | **9,6 ms** | **0,97 ms** |
| **relatório do atendente: tabela** | **29,8 ms** | **0,60 ms** |
| lista de tickets: página | 0,42 ms | 0,47 ms |
| lista busca cliente (`ilike`) | 27,4 ms | 25,8 ms |
| varredor de anexos pendentes | 11,9 ms | 5,4 ms |

Nenhuma regressão acima de 3,5 ms. A maior (`count declinado` com período,
5,9 → 9,4 ms) perdeu o `BitmapAnd` entre os dois compostos.

Tamanho, medido **após `REINDEX SCHEMA` no estado antes** — sem isso a
comparação fica inflada pelo bloat dos índices antigos contra os novos,
recém-criados:

| Tabela | Antes | Depois |
|---|---|---|
| `tickets` | 9 índices, 14.232 KB | 7 índices, 10.376 KB |
| `ticket_attachments` | 3 índices, 7.832 KB | 2 índices, 6.200 KB |
| **Total** | **12 índices, 22.064 KB** | **9 índices, 16.576 KB (-24,9%)** |

Escrita, em dois schemas idênticos com o mesmo dado, um parado na 0006 e outro
na 0007, rodando duas vezes com a ordem trocada (o segundo a rodar pega cache
quente):

| Operação | 0006 (compostos) | 0007 (parciais) |
|---|---:|---:|
| INSERT de 50.000 tickets, ordem A | 2.433 ms | 1.952 ms |
| INSERT de 50.000 tickets, ordem B | 2.846 ms | 2.294 ms |
| UPDATE de status em 16.543 tickets, ordem A | 613 ms | 472 ms |
| UPDATE de status em 16.543 tickets, ordem B | 710 ms | 606 ms |

Os parciais ganham nas duas ordens: 19-20% no INSERT e 15-23% no UPDATE. A
variação entre rodadas é grande, então o resultado honesto é "a escrita ficou
mais rápida na casa dos 15-20%", não um número exato. São operações em massa,
não o INSERT linha a linha da aplicação — a comparação entre os conjuntos é
justa, os tempos absolutos não representam a carga real.

## 6. Ressalvas

- Postgres 16 em Docker no Windows, `shared_buffers` padrão, massa inteira em
  cache. Com cache frio a vantagem do índice sobre o Seq Scan tende a ser
  **maior**, não menor — mas os números absolutos não transferem.
- O ganho da tabela do relatório depende de `opened_at` ser quase único, o que
  faz o Incremental Sort sair de graça. Se algum dia houver ingestão em lote que
  empate milhares de tickets no mesmo `opened_at`, o grupo de desempate cresce e
  `(opened_at, id)` volta a ser a escolha certa.
- Os três rankings continuam em 70-115 ms e são a parte mais cara do dashboard.
  São agregações sobre a base inteira; índice não resolve — se virarem gargalo,
  o caminho é cache ou tabela agregada.
- A galeria ainda faz a contagem total em 76 ms. A página ficou instantânea, mas
  o `count(*)` do paginador não tem seletividade nenhuma (90% dos anexos passam
  no filtro). Saída seria contagem aproximada ou paginação por cursor.
- A massa não inclui `ticket_comments` nem `ticket_timeline_events`; os índices
  de FK dessas tabelas ficaram sem medição.

## 7. O que a Fase 3B precisa saber

A 3B (`docs/superpowers/plans/2026-07-30-fase-3b-fila-tickets.md`) adiciona
filtro por atendente, busca livre por texto, filtro de não lidos e contadores de
fila. Nenhum índice foi criado para essas consultas — elas ainda não existem.
O que a medição revelou e a 3B deve levar em conta:

1. **A busca livre por texto é o problema real.** O filtro de cliente que já
   existe (`CustomerModel.name.ilike('%x%')`) gasta **25,8 ms em Seq Scan de
   40 mil clientes** só para resolver a subconsulta de ids. `ilike '%...%'` com
   curinga à esquerda não alcança b-tree nenhum, em nenhuma collation. O caminho
   é `pg_trgm` com índice GIN — e a extensão é **por database, não por schema de
   tenant**, logo entra como migration `public`, não `tenant`.
2. **O filtro por atendente já está resolvido:** Index Only Scan em 0,97 ms para
   8.815 tickets. Não precisa de índice novo.
3. **O filtro de não lidos vai doer.** "Não lido" é um predicado sobre o
   resultado do LEFT JOIN com `ticket_reads`; não há índice que o resolva, e ele
   força materializar o join antes de paginar (Seq Scan em `ticket_reads`,
   2.001 buffers). Vale considerar `NOT EXISTS` correlacionado, que mantém o
   acesso por `pk_ticket_reads` e preserva o plano ordenado por
   `last_activity_at`.
4. **Contadores de fila:** se forem `count(*) FILTER (...)` serão Seq Scan
   (~34 ms); se forem counts separados por status entram por
   `ix_tickets_status` parcial em 1-5 ms cada. Vale medir antes de escolher.
