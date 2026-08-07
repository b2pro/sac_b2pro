import { useQuery } from "@tanstack/react-query"
import { ListFilter, Search } from "lucide-react"
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { useNavigate } from "react-router-dom"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { formatDocument } from "@/lib/format"
import {
  globalSearch,
  MIN_SEARCH_LENGTH,
  type CustomerHit,
  type ProductHit,
  type SearchHits,
  type TicketHit,
} from "@/lib/search"
import { STATUS_ACCENT_VARS, STATUS_LABELS } from "@/lib/tickets"
import { useDebounce } from "@/lib/useDebounce"
import { cn } from "@/lib/utils"

const DEBOUNCE_MS = 250

/** A sequencia achatada que as setas percorrem: os tres grupos em ordem, mais a
 *  acao de rodape. Achatar e o que permite a seta cruzar a fronteira de grupo
 *  sem o teclado precisar saber que grupos existem. */
type Entry =
  | { kind: "ticket"; item: TicketHit }
  | { kind: "cliente"; item: CustomerHit }
  | { kind: "produto"; item: ProductHit }
  | { kind: "fila" }

function flatten(hits: SearchHits | undefined, withQueueAction: boolean): Entry[] {
  const entries: Entry[] = []
  for (const item of hits?.tickets ?? []) entries.push({ kind: "ticket", item })
  for (const item of hits?.clientes ?? []) entries.push({ kind: "cliente", item })
  for (const item of hits?.produtos ?? []) entries.push({ kind: "produto", item })
  // A acao de fila fecha a sequencia mesmo sem resultado nenhum: quando a busca
  // por identificador nao acha nada, procurar o termo na fila e justamente o
  // proximo passo, e ele fica a um Enter de distancia.
  if (withQueueAction) entries.push({ kind: "fila" })
  return entries
}

function optionId(index: number): string {
  return `busca-resultado-${index}`
}

/** Cabecalho de grupo: rotulo, regua ate a margem e a contagem em mono. A
 *  contagem nao e enfeite — o servidor corta em 5 por grupo, entao ver "5" e
 *  saber que pode haver mais fora da lista. */
/** `aria-hidden`: o rotulo ja chega ao leitor de tela pelo `aria-label` do
 *  `role="group"` que envolve o grupo, e um div solto entre as opcoes quebraria a
 *  estrutura que o papel de listbox promete. Aqui ele e puramente visual. */
function GroupHeader({ label, count }: { label: string; count: number }) {
  return (
    <div aria-hidden="true" className="flex items-center gap-2 px-3 pt-3 pb-1">
      <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </span>
      <span className="h-px flex-1 bg-border" />
      <span className="font-mono text-[11px] tabular-nums text-muted-foreground">{count}</span>
    </div>
  )
}

/** O conteudo varia por tipo, mas a geometria da linha e sempre a mesma: nome a
 *  esquerda, identificador tecnico em mono a direita. Do lado do usuario, a
 *  coluna da direita e sempre "o codigo disso". */
function EntryContent({ entry }: { entry: Entry }) {
  if (entry.kind === "ticket") {
    return (
      <>
        <span className="shrink-0 font-mono text-xs tabular-nums">#{entry.item.number}</span>
        <span className="min-w-0 flex-1 truncate">
          {entry.item.customer_name ?? <span className="text-muted-foreground">Sem cliente</span>}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {entry.item.brand_name ? `${entry.item.brand_name} · ` : ""}
          {STATUS_LABELS[entry.item.status]}
        </span>
      </>
    )
  }
  if (entry.kind === "cliente") {
    return (
      <>
        <span className="min-w-0 flex-1 truncate">{entry.item.name}</span>
        {entry.item.document ? (
          <span className="shrink-0 font-mono text-xs text-muted-foreground">
            {formatDocument(entry.item.document)}
          </span>
        ) : null}
      </>
    )
  }
  if (entry.kind === "produto") {
    return (
      <>
        <span className="min-w-0 flex-1 truncate">{entry.item.name}</span>
        {entry.item.sku ? (
          <span className="shrink-0 font-mono text-xs text-muted-foreground">{entry.item.sku}</span>
        ) : null}
      </>
    )
  }
  return (
    <>
      <ListFilter size={16} strokeWidth={1.5} className="shrink-0" />
      <span className="min-w-0 flex-1 truncate">Buscar na fila</span>
    </>
  )
}

export function GlobalSearch() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [term, setTerm] = useState("")
  const [highlight, setHighlight] = useState<{ list: Entry[]; index: number } | null>(null)
  const optionRefs = useRef<(HTMLDivElement | null)[]>([])

  const debounced = useDebounce(term, DEBOUNCE_MS)
  const trimmed = debounced.trim()
  // `live` e o termo que esta na caixa AGORA; `trimmed` e o espelho atrasado em
  // 250ms. Tudo que aparece na lista e tudo que o Enter aciona sai do `live`:
  // gatear pelo espelho deixava resultado de termo anterior na tela (e
  // acionavel) enquanto a caixa dizia outra coisa — reabrir a palette dentro da
  // janela do debounce mostrava a lista antiga sob um campo vazio, e apagar o
  // termo para 1 caractere nao voltava ao estado inicial.
  const live = term.trim()
  const canSearch = live.length >= MIN_SEARCH_LENGTH
  // O debounce alcancou o termo da caixa. Enquanto nao alcanca, nao ha resultado
  // que pertenca ao termo digitado, e a lista fica em "Buscando...".
  const settled = live === trimmed

  // A chave inclui o termo, e por isso resposta lenta de um termo antigo nao
  // sobrescreve a de um termo novo: cada termo tem sua propria entrada no cache
  // e o componente le sempre a do termo atual.
  const { data, isError } = useQuery({
    queryKey: ["busca", trimmed],
    queryFn: () => globalSearch(trimmed),
    enabled: open && canSearch && settled,
  })

  // Os resultados so contam quando pertencem ao termo da caixa. Sem este porteiro
  // unico, cada trecho do render teria que repetir a checagem — e um que
  // esquecesse voltaria a mostrar (ou a abrir) o resultado do termo anterior.
  const hits = canSearch && settled ? data : undefined

  const entries = useMemo(() => flatten(hits, canSearch), [hits, canSearch])

  // O indice do realce e guardado junto da lista a que pertence, e por isso
  // volta ao topo sozinho quando a lista muda de identidade (termo novo,
  // resultado que chegou). Derivar e melhor que zerar depois do render: entre o
  // render e a correcao, o realce apontaria para a linha errada.
  const active = highlight?.list === entries ? highlight.index : 0

  function moveActive(offset: number) {
    if (entries.length === 0) return
    setHighlight({ list: entries, index: (active + offset + entries.length) % entries.length })
  }

  useEffect(() => {
    // "nearest" mantem a lista quieta enquanto o realce ja esta visivel, e so
    // rola o suficiente quando ele sai pela borda.
    optionRefs.current[active]?.scrollIntoView({ block: "nearest" })
  }, [active, entries])

  useEffect(() => {
    function onShortcut(event: globalThis.KeyboardEvent) {
      if (event.repeat) return
      if (event.key.toLowerCase() !== "k") return
      if (!event.ctrlKey && !event.metaKey) return
      // AltGr do teclado ABNT2 chega como Ctrl+Alt: sem esta guarda, digitar um
      // caractere de terceiro nivel abriria a busca no meio de um formulario.
      // Shift tambem esta fora: Ctrl+Shift+K e o console do Firefox, e o atalho
      // pedido e Ctrl+K — nao "Ctrl+K com qualquer modificador extra".
      if (event.altKey || event.shiftKey) return
      // o navegador tambem usa Ctrl+K (busca na barra de endereco): sem o
      // preventDefault o foco sairia da pagina junto com a abertura do dialog
      event.preventDefault()
      // O atalho fecha por fora do Radix, entao nao passa por `onOpenChange` e
      // precisa fazer o mesmo reset dele — sem isto, fechar pelo atalho guardava
      // o termo e reabrir trazia a busca anterior de volta. Limpar vale nos dois
      // sentidos: ao abrir o termo ja esta vazio e isto e no-op, e assim o
      // listener nao precisa ler `open` (nem ser recriado a cada render).
      setTerm("")
      setHighlight(null)
      setOpen((current) => !current)
    }
    window.addEventListener("keydown", onShortcut)
    return () => window.removeEventListener("keydown", onShortcut)
  }, [])

  function onOpenChange(next: boolean) {
    setOpen(next)
    // Abre sempre limpo: termo e realce de uma busca anterior seriam ruido e,
    // pior, um Enter apressado abriria o resultado errado.
    if (!next) {
      setTerm("")
      setHighlight(null)
    }
  }

  function select(entry: Entry) {
    onOpenChange(false)
    if (entry.kind === "ticket") {
      navigate(`/tickets/${entry.item.id}`)
      return
    }
    // ClientesPage e ProdutosPage guardam a busca em estado local e nao leem
    // nada da URL: navegar com um parametro de filtro seria inventar um
    // contrato que a pagina nao honra, entao vai para a listagem sem filtro.
    if (entry.kind === "cliente") {
      navigate("/cadastros/clientes")
      return
    }
    if (entry.kind === "produto") {
      navigate("/cadastros/produtos")
      return
    }
    // `live` e nao `trimmed`: a fila nao depende de resposta do servidor, entao
    // nao ha motivo para levar o termo atrasado. Com o espelho, dar Enter aqui
    // antes do debounce fechar mandava para /tickets?q= do termo anterior.
    navigate(`/tickets?q=${encodeURIComponent(live)}`)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (entries.length === 0) return
    if (event.key === "ArrowDown") {
      event.preventDefault()
      moveActive(1)
      return
    }
    if (event.key === "ArrowUp") {
      event.preventDefault()
      moveActive(-1)
      return
    }
    if (event.key === "Enter") {
      event.preventDefault()
      const entry = entries[active]
      if (entry) select(entry)
    }
  }

  const tickets = hits?.tickets ?? []
  const clientes = hits?.clientes ?? []
  const produtos = hits?.produtos ?? []
  // Os deslocamentos vem dos mesmos grupos que a lista renderiza, e por isso o
  // indice de cada linha na tela e exatamente o indice dela em `entries` — o
  // que o teclado percorre e o que o olho ve.
  const clienteOffset = tickets.length
  const produtoOffset = clienteOffset + clientes.length
  const filaIndex = produtoOffset + produtos.length
  // Os quatro estados da lista, exaustivos e nesta ordem — nenhum termo, erro
  // sem nada em tela, esperando o termo da caixa, e resultado. Derivar de `hits`
  // (nao de `data`) e o que garante que a mensagem descreve o termo digitado.
  const mostrarErro = canSearch && settled && isError && data == null
  const buscando = canSearch && !mostrarErro && hits == null
  // `entries` tem so a acao de fila: consultou e nenhum grupo trouxe nada.
  const semResultados = hits != null && entries.length === 1

  function renderEntry(entry: Entry, index: number, extraClass?: string) {
    const isActive = index === active
    // A trilha em repouso vem do token do status, em estilo inline; no realce
    // ela cede a vez para o Paprika, e ai o inline sai de cena para a classe
    // `border-l-primary` poder valer (estilo inline venceria a classe).
    const railAtRest =
      !isActive && entry.kind === "ticket" ? STATUS_ACCENT_VARS[entry.item.status] : undefined
    return (
      <div
        key={entry.kind === "fila" ? "fila" : `${entry.kind}-${entry.item.id}`}
        id={optionId(index)}
        role="option"
        aria-selected={isActive}
        ref={(node) => {
          optionRefs.current[index] = node
        }}
        onClick={() => select(entry)}
        // onMouseMove e nao onMouseEnter: rolando com as setas, uma linha
        // passaria por baixo do cursor parado e roubaria o realce do teclado. O
        // teste de indice evita um render por evento de movimento do mouse.
        onMouseMove={() => {
          if (index !== active) setHighlight({ list: entries, index })
        }}
        style={railAtRest ? { borderLeftColor: railAtRest } : undefined}
        className={cn(
          // borda esquerda de 3px como nos cards da fila — no ticket ela ja
          // carrega a cor do status, e o realce toma essa mesma trilha em
          // Paprika: um elemento so diz "que tipo de linha" e "onde estou".
          "flex cursor-pointer items-center gap-3 border-l-[3px] px-3 py-2 text-sm",
          isActive ? "border-l-primary bg-secondary" : "border-l-transparent",
          extraClass,
        )}
      >
        <EntryContent entry={entry} />
      </div>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <button
          type="button"
          aria-keyshortcuts="Control+K"
          className="flex h-9 w-64 items-center gap-2 rounded-md border border-border px-2.5 text-sm text-muted-foreground transition-colors hover:border-foreground hover:text-foreground focus-visible:border-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none"
        >
          <Search size={20} strokeWidth={1.5} />
          <span className="flex-1 text-left">Buscar</span>
          <kbd className="rounded-sm border border-border px-1.5 py-0.5 font-mono text-[11px] leading-none">
            Ctrl K
          </kbd>
        </button>
      </DialogTrigger>
      {/* topo em 12vh e nao centralizado: a palette cresce para baixo conforme
          os resultados chegam, sem empurrar o campo de busca sob o cursor */}
      <DialogContent
        showCloseButton={false}
        className="top-[12vh] flex translate-y-0 flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl"
      >
        <DialogTitle className="sr-only">Busca global</DialogTitle>
        <DialogDescription className="sr-only">
          Busque tickets, clientes e produtos por número, nome, documento ou SKU.
        </DialogDescription>
        <div className="flex items-center gap-2 border-b border-border px-3">
          <input
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            onKeyDown={onKeyDown}
            role="combobox"
            aria-expanded={entries.length > 0}
            aria-controls="busca-resultados"
            aria-autocomplete="list"
            aria-activedescendant={entries.length > 0 ? optionId(active) : undefined}
            aria-label="Termo de busca"
            autoComplete="off"
            placeholder="Número do ticket, cliente, produto"
            className="h-11 flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
          />
          <kbd className="shrink-0 rounded-sm border border-border px-1.5 py-0.5 font-mono text-[11px] leading-none text-muted-foreground">
            esc
          </kbd>
        </div>
        <div className="max-h-[60vh] overflow-y-auto pb-1">
          {/* fora do listbox de proposito: um paragrafo solto entre as opcoes
              quebraria a estrutura que o leitor de tela espera, e como regiao
              viva o aviso e anunciado quando muda, sem o usuario ter que ir
              procurar. */}
          <div aria-live="polite">
            {!canSearch ? (
              <div className="px-3 py-6">
                <p className="text-sm">Digite ao menos 2 caracteres</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Número do ticket, nome ou documento do cliente, nome ou SKU do produto.
                </p>
              </div>
            ) : null}
            {buscando ? (
              <p className="px-3 py-6 text-sm text-muted-foreground">Buscando...</p>
            ) : null}
            {mostrarErro ? (
              <p className="px-3 py-6 text-sm text-destructive">Não foi possível buscar agora.</p>
            ) : null}
            {semResultados ? (
              <p className="px-3 py-6 text-sm">Nenhum resultado para este termo.</p>
            ) : null}
          </div>
          <div id="busca-resultados" role="listbox" aria-label="Resultados da busca">
            {tickets.length > 0 ? (
              <div role="group" aria-label="Tickets">
                <GroupHeader label="Tickets" count={tickets.length} />
                {tickets.map((item, i) => renderEntry({ kind: "ticket", item }, i))}
              </div>
            ) : null}
            {clientes.length > 0 ? (
              <div role="group" aria-label="Clientes">
                <GroupHeader label="Clientes" count={clientes.length} />
                {clientes.map((item, i) =>
                  renderEntry({ kind: "cliente", item }, clienteOffset + i),
                )}
              </div>
            ) : null}
            {produtos.length > 0 ? (
              <div role="group" aria-label="Produtos">
                <GroupHeader label="Produtos" count={produtos.length} />
                {produtos.map((item, i) =>
                  renderEntry({ kind: "produto", item }, produtoOffset + i),
                )}
              </div>
            ) : null}
            {/* o separador vai na propria opcao: um div envolvendo-a seria filho
                direto do listbox sem ser opcao nem grupo. A cor do border-t vem
                do `* { border-border }` da base, entao nao ha classe de cor que
                possa vazar para a trilha da esquerda. */}
            {canSearch ? renderEntry({ kind: "fila" }, filaIndex, "mt-1 border-t") : null}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
