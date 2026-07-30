# Prompt para o Claude (design) — telas da Fase 3 do SAC-B2PRO

Copie tudo abaixo da linha e cole na conversa de design.

---

Voce e o designer de interface de um sistema interno de SAC ja em producao. Nao e um site de marketing: e uma ferramenta operacional que atendentes usam 8 horas por dia. O sistema ja existe, ja tem identidade visual fechada, design system implementado e 10 telas construidas. Voce **nao vai criar uma identidade nova** — vai desenhar tres telas novas dentro de um sistema que ja tem regras. Diverja das regras somente onde eu pedir explicitamente uma proposta.

O resultado do seu trabalho sera transformado em React + TypeScript por outro Claude, entao a entrega precisa ser precisa o suficiente para virar codigo sem adivinhacao.

## 1. O produto

SAC-B2PRO: controle de trocas e defeitos de produtos (marcas KODI e STALEKS). Um ticket nasce quando um cliente reclama de um produto, passa por uma maquina de estados (aberto, aguardando cliente, aguardando analise, aprovado, aguardando envio reverso, produto recebido, finalizado, declinado, cancelado), tem SLA com prazo, itens (produto + tipo de defeito + quantidade), anexos (fotos do defeito, PDFs de nota fiscal, videos) e um tipo de solucao no fim (troca, reparo, credito, etc).

Usuarios: atendente (opera a fila), supervisor, admin do tenant e visualizador. As tres telas desta fase sao **somente leitura** — nenhuma acao de escrita, nenhum formulario de criacao, nenhum botao destrutivo.

## 2. Stack e restricoes tecnicas (obrigatorio respeitar)

- React 19 + TypeScript + Vite, React Router, TanStack Query.
- Tailwind CSS v4 com tokens em CSS variables (lista abaixo) + shadcn/ui.
- Icones: **somente `lucide-react`**, `strokeWidth={1.5}` sempre, 16px em tabela/lista e 20px em botao/header, nunca preenchidos.
- Graficos: **Recharts** (unica lib de grafico permitida).
- **Proibido emoji** em qualquer lugar: UI, copy, comentarios.
- Portugues do Brasil na interface. Os textos do sistema hoje sao escritos sem acentuacao em varios pontos por convencao interna; escreva a copy com acentuacao normal que eu normalizo depois.

## 3. Identidade visual ja definida (nao alterar)

Sensacao: entre painel de controle industrial e prancheta de oficina. Serio, denso, funcional. O laranja e sinalizacao, nunca decoracao.

| Papel | Hex | Uso |
|---|---|---|
| Floral White | `#fffcf2` | fundo das telas e dos cards (nunca branco puro) |
| Silver | `#ccc5b9` | bordas, divisores, estados neutros |
| Charcoal Brown | `#403d39` | corpo de texto |
| Carbon Black | `#252422` | titulos e fundo da sidebar |
| Spicy Paprika | `#eb5e28` | acao primaria, urgencia de SLA, numero de ticket em destaque |

Tokens Tailwind disponiveis (use os nomes, nao hex soltos): `bg-background`, `text-foreground`, `bg-card`, `text-primary`/`bg-primary`, `bg-secondary`, `bg-muted`, `text-muted-foreground` (`#736e66`), `border-border`, `ring-ring`, `bg-sidebar`. Existe tema escuro com os mesmos nomes de token, entao **nao hardcode hex** em nada que possa inverter.

- Tipografia: `font-sans` = Public Sans Variable (todo o texto). `font-mono` = JetBrains Mono Variable **somente** para numero de ticket, CPF/CNPJ, codigo de rastreio, timestamps e valores numericos de KPI.
- Raio: `--radius: 5px`. Nunca zero, nunca grande.
- Bordas de 1px em Silver em repouso; no hover/focus a borda vira Charcoal Brown.
- **Zero drop-shadow decorativo. Zero gradiente, nem sutil.** Profundidade se resolve com borda.
- Espacamento em escala de 4px: 24-32px entre secoes, 8-12px dentro de linha de tabela. Densidade de linha importa mais que espaco em branco bonito.
- Card de ticket na fila tem borda esquerda de 3px na cor do status.
- Empty state: borda tracejada + frase direta ("Nenhum ticket aberto para este filtro"). Sem ilustracao.
- Elemento-assinatura existente do sistema: a trilha de status horizontal segmentada (barra, nao stepper com bolinhas).

## 4. Chrome existente (as telas novas vivem dentro dele)

```
+----------------+--------------------------------------------------+
| SAC B2PRO      |  header 56px: nome do usuario + menu Sair         |
| (sidebar 240px |--------------------------------------------------+
|  fundo         |                                                  |
|  #252422,      |  main: overflow-y auto, padding 24px             |
|  item ativo    |  <- AQUI ENTRA O CONTEUDO QUE VOCE DESENHA       |
|  com barra     |                                                  |
|  esquerda      |                                                  |
|  Paprika 2px)  |                                                  |
+----------------+--------------------------------------------------+
```

Sidebar por grupos: **Operacao** (Dashboard, Tickets, Relatorios, Midias — os tres novos entram aqui) e **Cadastros** (Marcas, Produtos, Defeitos, Solucoes, Canais, Clientes). Nao redesenhe sidebar nem header.

## 5. Componentes que ja existem e devem ser reusados

shadcn/ui ja instalados: `Button` (variants default/ghost/outline), `Card` + `CardHeader`/`CardTitle`/`CardContent`, `Input`, `Label`, `Select`, `Checkbox`, `Switch`, `Textarea`, `Dialog`, `DropdownMenu`, `Table` (+ `TableHeader`/`TableBody`/`TableRow`/`TableHead`/`TableCell`), `Badge`, `Sonner` (toasts).

Do projeto: `StatusBadge`, `PriorityBadge`, `SlaBadge`, `STATUS_ACCENTS` (mapa de borda esquerda por status), `StatusTrail`, `AutocompleteField` (input com busca assincrona, usado para produto/defeito/solucao/canal), `AttachmentsCard`.

Cores semanticas de status ja fixadas (escala Tailwind, usar exatamente estas familias):

| Status | Cor |
|---|---|
| aberto | sky |
| aguardando_cliente | amber |
| aguardando_analise | violet |
| aprovado | emerald 600 |
| aguardando_envio_reverso | indigo |
| produto_recebido | teal |
| finalizado | emerald 700 |
| declinado | rose |
| cancelado | zinc |

## 6. As tres telas

### 6.1 Dashboard (`/dashboard`) — rota inicial apos o login

Um endpoint unico devolve tudo, com filtro opcional por marca aplicado a todos os numeros:

```ts
kpis: { key: string; count: number; filters: Record<string,string> }[]
// 7 chaves, nesta ordem: total, abertos, aguardando_analise, atrasados,
// aprovados_no_mes, declinados_no_mes, finalizados_no_mes
status_counts: Record<TicketStatus, number>         // os 9 status
products / defects / solutions: { id, name, count }[]  // top 5 cada
avg_resolution_hours: number | null
recent: TicketListItem[]                             // ultimos 10
```

`TicketListItem` = `{ id, number, status, priority, sla, due_at, customer_name, first_product_name, items_count, attendant_name, opened_at, last_activity_at, unread }`.

Precisa cobrir:
- Header da pagina com titulo e um select de marca (Todas as marcas / KODI / STALEKS) que recarrega tudo.
- **7 KPI cards clicaveis** — cada um navega para a lista de tickets ja pre-filtrada (`/tickets?status=...`). Labels: Total, Abertos, Aguardando analise, Atrasados (SLA), Aprovados no mes, Declinados no mes, Finalizados no mes. Precisam ler bem em grid responsivo e deixar claro que sao navegaveis (affordance de link, nao de botao primario). "Atrasados (SLA)" e o unico que pode usar Paprika.
- Distribuicao por status: grafico de barras horizontais, 9 categorias, cores semanticas acima. Defina rotulos, eixo, grid, tooltip e o que acontece com contagem zero.
- Tempo medio de resolucao: um stat isolado, formatado tipo "1d 4h"; travessao quando `null` (nenhum ticket finalizado no recorte).
- Tres rankings top 5 (produtos, defeitos, solucoes) como lista com barra de proporcao — sem lib de grafico, so div com largura percentual. Resolva empate visual e nomes longos.
- Tabela de tickets recentes, compacta, linha inteira clicavel para o detalhe.
- O layout de referencia e 2/3 (grafico + recentes) + 1/3 (stat + rankings), mas **proponha o que for melhor** se discordar, justificando em uma linha.
- Estados: loading com skeleton, tenant vazio (total 0) com empty state.

### 6.2 Relatorios (`/relatorios`)

```ts
kpis: { total; finalized; declined; avg_resolution_hours: number | null }
products / defects / solutions: { id, name, count }[]
items: TicketListItem[]; total; page; per_page
```

Precisa cobrir:
- Card de filtros com **8 campos**: periodo de/ate (date), marca (select), status (select), atendente (select), produto / defeito / solucao / canal (autocomplete com busca). Botoes Filtrar e Limpar. Esse card e o elemento mais pesado da tela — resolva o arranjo sem virar um paredao de inputs, e diga se ele deve ser colapsavel.
- Chips de filtros ativos, cada um removivel.
- 4 KPI cards do recorte (Total, Finalizados, Declinados, Tempo medio) — **nao clicaveis**, diferente do dashboard. Deixe essa diferenca legivel.
- Os mesmos tres rankings do dashboard (componente compartilhado — se voce mudar o visual aqui, muda la).
- Tabela paginada com as colunas da lista de tickets (numero, cliente, produto, status, prioridade, SLA, atendente, ultima atividade), linha clicavel, controles de paginacao.
- Botao Exportar CSV no header do card de resultados, com estado de carregando e toast de erro em caso de falha.
- Estados: loading, nenhum resultado para os filtros, e o estado inicial (sem filtro nenhum).

### 6.3 Midias (`/midias`)

Galeria de todos os anexos do tenant.

```ts
items: { id, ticket_id, ticket_number, filename, kind: "imagem"|"pdf"|"video",
         content_type, size_bytes, created_at, preview_url: string | null }[]
total; page; per_page
```

Precisa cobrir:
- Card de filtros: tipo (imagem/pdf/video), marca, produto, defeito, solucao, status do ticket, periodo.
- Grid responsivo de thumbnails (aspecto quadrado, `object-cover`), com legenda por item: numero do ticket em mono e data.
- **`preview_url` pode ser `null`** (preview ainda nao gerado ou falhou): defina o placeholder por tipo, com icone Lucide, sem parecer erro.
- Scroll infinito: define o comportamento da sentinela no fim do grid, o indicador de carregando e o fim da lista.
- Lightbox ao clicar: imagem ampliada / player de video / link de PDF, com metadados (nome do arquivo, tamanho, data, tipo) e link "Ver ticket #N". Esse lightbox e compartilhado com a tela de detalhe do ticket, entao precisa funcionar com e sem o link de ticket.
- Estados: loading inicial, nenhum anexo para o filtro, tenant sem anexo nenhum.

## 7. Piso de qualidade

Responsivo ate mobile (a sidebar ja tem tratamento proprio, foque no conteudo). Foco de teclado visivel em tudo que e clicavel, incluindo card-link e linha de tabela. `prefers-reduced-motion` respeitado. Contraste AA no texto e nas cores de grafico sobre `#fffcf2`. Nada de animacao decorativa: o unico movimento previsto no sistema hoje e o pulso sutil em Paprika quando o SLA aperta.

## 8. Entrega esperada

Para **cada uma das tres telas**:

1. Um mockup HTML estatico e autocontido (artifact), com dados de exemplo realistas de SAC de cosmetico/manicure — nomes de produto como "Alicate de cuticula Staleks Expert 11", defeitos como "Lamina cega", clientes brasileiros, numeros de ticket sequenciais. Renderize com os tokens acima como CSS variables e inclua a sidebar/header em volta para eu ver o encaixe.
2. Os principais estados alem do padrao: loading, vazio e (onde couber) erro. Pode ser uma segunda tela do mesmo artifact.
3. Uma lista de componentes que voce esta propondo, com nome sugerido e as props que cada um recebe — separando o que e novo do que reusa o que ja existe (secao 5).

No fim, um resumo curto das decisoes de layout, hierarquia e cor de grafico, e onde voce discordou do que descrevi e por que.

Nao invente campos, endpoints ou filtros que nao estao aqui: o backend ja esta pronto e o contrato e exatamente esse.

---
