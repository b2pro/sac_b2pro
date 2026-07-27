# Legado SAC-Tickets — Funcionamento (referência funcional)

Levantamento do backend do projeto `../SAC-Tickets`. Stack legada: Laravel 12 (PHP 8.2), MySQL, Blade + Alpine + Tailwind via CDN, sem camada de serviços (regra de negócio nos controllers), sem API separada (rotas web com sessão).

## Multi-tenancy e papéis

- Multi-tenant **single-database** por coluna `tenant_id` (manual, sem pacote). Tenant = "organização" com `slug`, `status` (ativa/teste/suspensa/inativa), flag `active` e módulos habilitáveis (`module_tickets`, `module_events`).
- Usuários pertencem a um tenant (`tenant_id`; null = super admin da plataforma). E-mail único **por tenant**. Sem registro público, sem reset de senha por e-mail, sem 2FA, sem rate limit no login.
- Papéis (enum na tabela users): `super_admin` (painel `/platform`: organizações, super admins, dashboard global — não acessa o operacional), `admin`, `supervisor`, `atendente` (vê/edita apenas os próprios tickets), `visualizador` (somente leitura).
- Isolamento em 3 camadas: middleware `EnsureTenantContext`, `scopeForTenant()` e `resolveRouteBinding()` sobrescrito por model. Autorização inconsistente: uma única Policy (Ticket), `role:` no construtor dos controllers e `abort_if` manuais.

## Modelo de dados (núcleo SAC)

- **Tenant** e **User** (acima).
- **Customer**: nome, CPF/CNPJ (unicidade só na aplicação), telefone, e-mail, endereço completo (CEP via ViaCEP no browser). Busca por tokens fora de ordem e por documento normalizado via `REPLACE()` em SQL.
- **Product**: nome, SKU (único por tenant), descrição, foto, ativo.
- **DefectType** e **SolutionType**: cadastros nome+descrição+ativo por tenant.
- **Ticket**: numeração sequencial por tenant (gerada por `max()+1` com loop — race condition), cliente, atendente, supervisor, status (10 valores), prioridade (baixa/media/alta/urgente), local da compra, código do pedido, datas de compra/entrega, descrição, notas de decisão e finais, pedido de garantia (código Tiny manual) + rastreio, marcos temporais (aberto, enviado à análise, aprovado/declinado, fechado, última atividade) e `due_at` (SLA).
- **TicketItem**: múltiplos produtos+defeitos por ticket (o `product_id/defect_type_id` do ticket duplica o primeiro item — duas fontes de verdade, dashboard usa uma e relatório usa outra).
- **TicketComment**: chat interno com resposta/citação (`reply_to_id`). Sem canal com o cliente final.
- **TicketAttachment**: até 10 arquivos de 50 MB (jpg/png/webp/mp4/mov/webm), armazenados em disco privado por tenant/ticket, servidos só por controller autorizado.
- **TicketTimelineEvent**: auditoria por ticket (tipo, título, valores antigo/novo, autor).
- **TicketRead**: controle de "não lida" por usuário (last_read_at vs last_activity_at).
- **ReverseCode**: códigos de logística reversa (vários por ticket).
- Módulo **Eventos** (domínio paralelo, feature flag): construtor de formulários públicos dinâmicos com lógica condicional, fichas de patrocínio com análise (aprovar/recusar), produtos+valores, contrato e lixeira. Decidir se entra no escopo do novo sistema.

## Fluxo do ticket (máquina de estados implícita)

```
aberto -> aguardando_analise -> aprovado -> aguardando_envio_reverso -> produto_recebido -> finalizado
                             -> declinado (encerrado; motivo obrigatório)
laterais: aguardando_cliente, em_analise, cancelado; reabrir volta a aprovado ou aberto
```

- Abertura pode ser **parcial** (sem produto/defeito/descrição); a completude é exigida apenas no envio para análise do supervisor.
- Aprovação/declínio são do admin/supervisor; declínio exige motivo; conclusão exige solução escolhida.
- Registrar código reverso move para `aguardando_envio_reverso`; excluir todos os códigos volta para `aprovado`.
- Existe uma rota genérica de troca de status que aceita qualquer transição (sem máquina de estados real) — corrigir no novo sistema.
- Prioridade define SLA em horas (urgente 24, alta 48, média 72, baixa 120; alerta a 12h do prazo). Status de SLA: no prazo / vence em breve / atrasado / encerrado.
- Exclusão de ticket faz `forceDelete` (perde histórico e recicla o número) — corrigir.

## Telas/recursos servidos

Dashboard (KPIs, distribuição por status, tempo médio de resolução, recentes); lista de tickets com filtros e "não lida"; detalhe do ticket com ações de workflow, chat, anexos, reversos e timeline; relatórios com filtros, rankings e export CSV (o CSV aplica menos filtros que a tela); galeria de mídias; CRUDs de produtos, defeitos, soluções, clientes (com histórico) e usuários; preferências de notificação; painel da plataforma (organizações e super admins).

## Notificações e integrações

- Notificações somente **in-app** (tabela `notifications`), com sino por polling (20s), popup do browser e som. Gatilhos: atribuição de supervisor, envio à análise, aprovação, declínio, comentário. Chat por polling (7s). Sem e-mail (MAIL=log), SMS ou WhatsApp; cliente final não recebe nada.
- Única integração real: **ViaCEP**, chamado do browser sem tratamento de erro. Tiny ERP é apenas campo manual. Sem importação de planilhas (apenas export CSV de relatório).

## Testes

SQLite in-memory. Módulo Eventos bem coberto (~40 testes); o fluxo core de tickets quase sem testes (nada de submit/approve/decline/finalize, numeração, policies).

## Defeitos estruturais a não repetir

1. Regra de negócio em controllers de 650 linhas, sem services/use cases.
2. Sem máquina de estados de verdade; rota de status livre.
3. Duas fontes de verdade para itens do ticket; numeração com race condition; forceDelete.
4. Login sem verificação de usuário/tenant ativos e sem rate limiting.
5. Autorização em três estilos misturados; unicidade de documento sem constraint no banco.
6. Polling em vez de eventos/websocket; assets por CDN em produção.
7. Docs desatualizados em relação ao schema real.
