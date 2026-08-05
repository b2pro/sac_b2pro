import { useQuery } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, Plus, Search, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"

import { EmptyState } from "@/components/reporting/EmptyState"
import { Pagination } from "@/components/reporting/Pagination"
import { QuickFilterChips, type QuickFilterKey } from "@/components/tickets/QuickFilterChips"
import { TicketQueueCard } from "@/components/tickets/TicketQueueCard"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useAuth } from "@/lib/auth"
import { listCatalog } from "@/lib/cadastros"
import { listMembers } from "@/lib/members"
import {
  canCreateTicket,
  getTicketCounters,
  listTickets,
  STATUS_LABELS,
  type TicketStatus,
} from "@/lib/tickets"
import { useDebounce } from "@/lib/useDebounce"

const PER_PAGE = 20
const ALL = "all"

type SortField = "last_activity_at" | "number" | "opened_at" | "due_at"

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: "last_activity_at", label: "Ultima atividade" },
  { value: "number", label: "Numero" },
  { value: "opened_at", label: "Abertura" },
  { value: "due_at", label: "Prazo SLA" },
]

const SORT_FIELDS = SORT_OPTIONS.map((option) => option.value)
const STATUS_VALUES = Object.keys(STATUS_LABELS) as TicketStatus[]
const ORDER_VALUES = ["asc", "desc"] as const

export default function TicketsListPage() {
  const { session } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const statusParam = searchParams.get("status")
  const status = (
    statusParam && STATUS_VALUES.includes(statusParam as TicketStatus) ? statusParam : ""
  ) as TicketStatus | ""
  const brandId = searchParams.get("brand_id") ?? ""
  const atendenteId = searchParams.get("atendente_id") ?? ""
  const overdue = searchParams.get("overdue") === "1"
  const unread = searchParams.get("unread") === "1"
  const q = searchParams.get("q") ?? ""
  // Sem select proprio na tela: entra so pelo link "Ver historico" do
  // cliente no detalhe do ticket (`/tickets?customer_id=...`). A pill abaixo
  // dos chips e o unico indicador e o unico jeito de remover o recorte.
  const customerId = searchParams.get("customer_id") ?? undefined
  const paginaBruta = Number(searchParams.get("page"))
  const page = Number.isFinite(paginaBruta) ? Math.max(Math.trunc(paginaBruta), 1) : 1
  const sortParam = searchParams.get("sort")
  const sort = (
    sortParam && SORT_FIELDS.includes(sortParam as SortField) ? sortParam : "last_activity_at"
  ) as SortField
  const orderParam = searchParams.get("order")
  const order = (
    orderParam && ORDER_VALUES.includes(orderParam as "asc" | "desc") ? orderParam : "desc"
  ) as "asc" | "desc"

  const userId = session?.user.id

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== "page") next.delete("page")
    setSearchParams(next, { replace: true })
  }

  // Busca livre: campo local para digitar sem travar, e so escreve na URL
  // (e portanto so dispara requisicao) depois do debounce. Le e escreve via
  // o updater funcional do setSearchParams (sempre com o valor mais recente
  // da URL, sem depender de "searchParams" no closure) e vira um no-op
  // quando o "q" da URL ja bate com o debounce — assim uma re-execucao do
  // efeito por causa de outro filtro mudar a URL (setSearchParams ganha
  // identidade nova a cada navegacao) nao derruba a pagina atual.
  const [searchText, setSearchText] = useState(() => searchParams.get("q") ?? "")
  const debouncedSearch = useDebounce(searchText, 400)
  // Guarda o ultimo valor de "q" que este componente colocou na URL, para
  // distinguir "a URL mudou porque eu mesmo escrevi o debounce" de "a URL
  // mudou por outro motivo" (ex.: navegar para /tickets pelo menu lateral
  // enquanto ainda havia uma busca ativa). So no segundo caso o campo local
  // e resincronizado — nunca a cada tecla digitada.
  const committedSearchRef = useRef(q)
  useEffect(() => {
    if (q !== committedSearchRef.current) {
      committedSearchRef.current = q
      setSearchText(q)
    }
  }, [q])
  useEffect(() => {
    setSearchParams((prev) => {
      const currentQ = prev.get("q") ?? ""
      if (currentQ === debouncedSearch) return prev
      const next = new URLSearchParams(prev)
      if (debouncedSearch) next.set("q", debouncedSearch)
      else next.delete("q")
      next.delete("page")
      return next
    }, { replace: true })
    committedSearchRef.current = debouncedSearch
  }, [debouncedSearch, setSearchParams])

  const role = session?.role ?? null
  const podeCriar = canCreateTicket(role)

  // Deriva o chip ativo (ou nenhum) so a partir da URL. "Nenhum chip" cobre
  // recortes que os selects do header conseguem expressar mas os chips nao
  // representam: um status sem chip equivalente (ex.: "aprovado",
  // "declinado", "finalizado" — os cards de KPI do dashboard linkam para
  // esses) ou um atendente_id que nao e o usuario logado (selecionado pelo
  // proprio select de Atendente, nao pelo chip "Meus tickets").
  let activeQuickFilter: QuickFilterKey | null
  if (unread) activeQuickFilter = "nao_lidos"
  else if (overdue) activeQuickFilter = "atrasados"
  else if (atendenteId) activeQuickFilter = userId && atendenteId === userId ? "meus" : null
  else if (status) {
    activeQuickFilter =
      status === "aguardando_analise" ? "aguardando_analise" : status === "aberto" ? "abertos" : null
  } else activeQuickFilter = "todos"

  function onSelectQuickFilter(key: QuickFilterKey) {
    const next = new URLSearchParams(searchParams)
    next.delete("status")
    next.delete("overdue")
    next.delete("unread")
    next.delete("atendente_id")
    next.delete("page")
    if (key === "abertos") next.set("status", "aberto")
    else if (key === "aguardando_analise") next.set("status", "aguardando_analise")
    else if (key === "atrasados") next.set("overdue", "1")
    else if (key === "nao_lidos") next.set("unread", "1")
    else if (key === "meus" && userId) next.set("atendente_id", userId)
    setSearchParams(next, { replace: true })
  }

  const { data: brands } = useQuery({
    queryKey: ["marcas"],
    queryFn: () => listCatalog("marcas"),
  })
  const { data: members } = useQuery({
    queryKey: ["membros"],
    queryFn: () => listMembers(),
  })
  const { data: counters } = useQuery({
    queryKey: ["ticket-contadores"],
    queryFn: () => getTicketCounters(),
  })
  const { data, isLoading } = useQuery({
    queryKey: [
      "tickets",
      { status, brandId, atendenteId, unread, overdue, q, customerId, sort, order, page },
    ],
    queryFn: () =>
      listTickets({
        status: status || undefined,
        brandId: brandId || undefined,
        atendenteId: atendenteId || undefined,
        unread: unread || undefined,
        overdue: overdue || undefined,
        q: q || undefined,
        customerId,
        sort,
        order,
        page,
        perPage: PER_PAGE,
      }),
  })

  const items = data?.items ?? []
  // Nome para a pill do deep link: todo ticket do recorte pertence ao mesmo
  // cliente, entao o primeiro nome carregado serve (sem endpoint de cliente
  // por id no backend; com a lista vazia a pill fica sem nome, mas visivel).
  const customerName = customerId
    ? (items.find((item) => item.customer_name)?.customer_name ?? null)
    : null

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-accent-foreground">Tickets</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Fila de trocas e defeitos
            {counters !== undefined && (
              <>
                {" — "}
                <span className="font-mono">{counters.ativos}</span> tickets ativos, de{" "}
                <span className="font-mono">{counters.todos}</span> no total
              </>
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              size={16}
              strokeWidth={1.5}
              className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Buscar por no, cliente, produto ou pedido"
              className="h-8 w-[250px] pl-8"
            />
          </div>

          <Select
            value={status || ALL}
            onValueChange={(value) => setParam("status", value === ALL ? "" : value)}
          >
            <SelectTrigger aria-label="Status" size="sm">
              <SelectValue placeholder="Todos os status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Todos os status</SelectItem>
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={brandId || ALL}
            onValueChange={(value) => setParam("brand_id", value === ALL ? "" : value)}
          >
            <SelectTrigger aria-label="Marca" size="sm">
              <SelectValue placeholder="Todas as marcas" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Todas as marcas</SelectItem>
              {(brands ?? []).map((brand) => (
                <SelectItem key={brand.id} value={brand.id}>
                  {brand.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={atendenteId || ALL}
            onValueChange={(value) => setParam("atendente_id", value === ALL ? "" : value)}
          >
            <SelectTrigger aria-label="Atendente" size="sm">
              <SelectValue placeholder="Todos os atendentes" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Todos os atendentes</SelectItem>
              {(members ?? []).map((member) => (
                <SelectItem key={member.id} value={member.id}>
                  {member.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex items-center gap-1">
            <Select value={sort} onValueChange={(value) => setParam("sort", value)}>
              <SelectTrigger aria-label="Ordenar por" size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SORT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              onClick={() => setParam("order", order === "asc" ? "desc" : "asc")}
              aria-label={order === "asc" ? "Ordem crescente" : "Ordem decrescente"}
            >
              {order === "asc" ? (
                <ArrowUp size={16} strokeWidth={1.5} />
              ) : (
                <ArrowDown size={16} strokeWidth={1.5} />
              )}
            </Button>
          </div>

          {podeCriar && (
            <Button asChild size="sm">
              <Link to="/tickets/novo">
                <Plus size={20} strokeWidth={1.5} />
                Novo ticket
              </Link>
            </Button>
          )}
        </div>
      </div>

      <QuickFilterChips
        counters={counters}
        active={activeQuickFilter}
        onSelect={onSelectQuickFilter}
      />

      {/* aria-live precisa do container sempre no DOM: se o bloco todo so
          entrasse quando ha customerId, a pill nasceria ja dentro da regiao e
          o leitor de tela nunca perceberia a insercao. */}
      <div aria-live="polite">
        {customerId && (
          <div className="-mt-2.5 mb-5">
            <span className="inline-flex h-7 items-center gap-1.5 rounded-md border bg-card pr-1 pl-2.5 text-[13px]">
              <span className="text-muted-foreground">Filtrando por cliente</span>
              {customerName && <span className="font-medium">{customerName}</span>}
              <button
                type="button"
                onClick={() => setParam("customer_id", "")}
                aria-label="Remover filtro de cliente"
                className="inline-flex size-5 items-center justify-center rounded-sm text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X size={16} strokeWidth={1.5} aria-hidden />
              </button>
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2.5">
        {isLoading ? (
          Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="h-[76px] animate-pulse rounded-md bg-muted" />
          ))
        ) : items.length === 0 ? (
          <EmptyState
            title="Nenhum ticket aberto para este filtro"
            description="Ajuste a busca ou os filtros acima."
          />
        ) : (
          items.map((item) => <TicketQueueCard key={item.id} item={item} />)
        )}
      </div>

      {!isLoading && items.length > 0 && (
        <Pagination
          page={page}
          perPage={PER_PAGE}
          total={data?.total ?? 0}
          onPage={(nextPage) => setParam("page", String(nextPage))}
        />
      )}
    </div>
  )
}
