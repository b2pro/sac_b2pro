# SAC-B2PRO — Fase 3: componentes propostos

Os mockups (`Dashboard.dc.html`, `Relatorios.dc.html`, `Midias.dc.html`) usam os tokens do sistema como CSS variables. Estados alternativos (loading, vazio, inicial, sem resultado, exportando CSV, fim do scroll) são alternáveis pelo painel de Tweaks de cada arquivo.

## Novos componentes

### `KpiCard`
Usado no Dashboard (clicável) e em Relatórios (estático). Um componente, dois modos.
- `label: string`
- `value: number | string`
- `to?: string` — rota de destino; quando presente renderiza como link (`<Link>`), mostra o ícone arrow-up-right e ganha hover de borda Charcoal. Ausente = card estático, sem affordance.
- `accent?: boolean` — valor em Paprika (só "Atrasados (SLA)").
- `caption?: string` — linha auxiliar ("do recorte atual", em Relatórios).

### `StatusDistributionChart`
Barras horizontais, Recharts (`BarChart layout="vertical"`).
- `counts: Record<TicketStatus, number>`
- Eixo X com 4 ticks (0 → teto arredondado acima do máximo), grid vertical só nos ticks, labels de status no eixo Y (172px), cores de `STATUS_ACCENTS`. Contagem zero: barra ausente, trilho `bg-muted` visível e contagem "0" em `text-muted-foreground`. Tooltip: nome do status + contagem, fundo `bg-card` com borda Silver (sem sombra).

### `RankingList` (compartilhado Dashboard/Relatórios)
- `title: string`
- `rows: { id: string; name: string; count: number }[]`
- Barra de proporção: div 4px, largura `count / max(rows) * 100%`, preenchimento Charcoal Brown sobre trilho `bg-muted`. Empate = larguras idênticas, desambiguado pela contagem mono à direita. Nome com `truncate` + `title` no hover.

### `AvgResolutionStat`
- `hours: number | null` — formata `"2d 6h"` (helper `formatDuration`); `null` renderiza travessão ("—").

### `RecentTicketsTable` / `TicketResultsTable`
Mesma linha base (`TicketRow`): `border-left` 3px via `STATUS_ACCENTS`, linha inteira clicável (`role="link"`, `tabIndex=0`, Enter/Espaço navegam), hover `bg`-sutil, foco visível.
- `RecentTicketsTable`: `items: TicketListItem[]` — colunas Nº, Cliente, Produto, Status, SLA, Última atividade.
- `TicketResultsTable`: + colunas Prioridade e Atendente, e `pagination: { page, perPage, total, onPage }`.

### `ReportFiltersCard`
- `value: ReportFilters`, `onApply`, `onClear`
- Grid `auto-fit minmax(190px, 1fr)`: 2 datas + 3 selects + 4 `AutocompleteField` (reuso). Colapsável: sim, mas **começa aberto** e só persiste o estado recolhido por sessão — é a ferramenta principal da tela, esconder por padrão custaria mais cliques do que economiza.

### `ActiveFilterChips`
- `chips: { key: string; label: string }[]`, `onRemove(key)`

### `ExportCsvButton`
- `onExport: () => Promise<void>` — variante outline; enquanto pende: spinner + "Exportando..." + `disabled`; falha dispara `toast.error` (Sonner).

### `MediaFiltersCard`
- Mesmo padrão do `ReportFiltersCard`, campos: tipo, marca, status + produto/defeito/solução (autocomplete) + período.

### `MediaGrid` + `MediaTile`
- `items: MediaItem[]`, `onOpen(item)`
- Tile quadrado (`aspect-ratio: 1`, `object-cover`), legenda: nº do ticket (mono, Paprika) + data (mono, muted). `preview_url === null` → placeholder `bg-muted` com ícone Lucide por tipo (`Image` / `FileText` / `Video`, 28px, strokeWidth 1.5) + extensão em mono — sem tom de erro. Vídeo com preview ganha overlay de play; chip de tipo no canto inferior direito.

### `InfiniteScrollSentinel`
- `hasMore: boolean`, `loading: boolean`, `onIntersect`
- `IntersectionObserver` num div no fim do grid (`rootMargin: "400px"` para pré-carregar); carregando: spinner + "Carregando mais anexos..."; `hasMore=false`: "Fim da lista — N anexos".

### `MediaLightbox` (compartilhado com detalhe do ticket)
- `item: MediaItem | null`, `onClose`
- `showTicketLink?: boolean` — `false` na tela de detalhe (o usuário já está no ticket).
- `Dialog` (shadcn): imagem ampliada / `<video controls>` / link "Abrir PDF"; painel lateral com nome, tipo, tamanho, data, content-type e "Ver ticket #N". Esc e clique no backdrop fecham.

### Helpers
- `formatDuration(hours: number | null): string` — "1d 4h" / "—".
- `formatBytes(n: number): string` — "2.4 MB".

## Reuso do que já existe
`StatusBadge`, `PriorityBadge`, `SlaBadge` (pulso Paprika quando estourado), `STATUS_ACCENTS`, `AutocompleteField`, `Card`/`Table`/`Select`/`Button`/`Badge`/`Dialog`/`Sonner` do shadcn. Nenhuma mudança neles.
