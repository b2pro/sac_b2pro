import { useQuery } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, Plus } from "lucide-react"
import { useCallback, useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"

import { AutocompleteField } from "@/components/tickets/AutocompleteField"
import { PriorityBadge, SlaBadge, StatusBadge, STATUS_ACCENTS } from "@/components/tickets/badges"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuth } from "@/lib/auth"
import { listCatalog, listProducts } from "@/lib/cadastros"
import {
  canCreateTicket,
  listTickets,
  PRIORITY_LABELS,
  STATUS_LABELS,
  type TicketPriority,
  type TicketStatus,
} from "@/lib/tickets"
import { useDebounce } from "@/lib/useDebounce"
import { useProductLabelById } from "@/lib/useProductLabelById"
import { cn } from "@/lib/utils"

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
const PRIORITY_VALUES = Object.keys(PRIORITY_LABELS) as TicketPriority[]
const ORDER_VALUES = ["asc", "desc"] as const

export default function TicketsListPage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const statusParam = searchParams.get("status")
  const status = (
    statusParam && STATUS_VALUES.includes(statusParam as TicketStatus) ? statusParam : ""
  ) as TicketStatus | ""
  const brandId = searchParams.get("brand_id") ?? ""
  const customer = searchParams.get("customer") ?? ""
  const productId = searchParams.get("product_id") ?? ""
  const orderCode = searchParams.get("order_code") ?? ""
  const priorityParam = searchParams.get("priority")
  const priority = (
    priorityParam && PRIORITY_VALUES.includes(priorityParam as TicketPriority)
      ? priorityParam
      : ""
  ) as TicketPriority | ""
  const overdue = searchParams.get("overdue") === "1"
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
  const [productQuery, setProductQuery] = useState("")
  const customerId = searchParams.get("customer_id") ?? undefined

  // Ao abrir um link compartilhado, product_id vem na URL mas o campo do
  // autocomplete ainda esta vazio. Resolve o nome pela listagem de produtos
  // so nessa lacuna (sem rotulo em estado ainda).
  const applyResolvedProductLabel = useCallback((name: string) => setProductQuery(name), [])
  useProductLabelById(productId, !!productQuery, applyResolvedProductLabel)

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== "page") next.delete("page")
    setSearchParams(next, { replace: true })
  }

  const debouncedCustomer = useDebounce(customer)
  const debouncedOrder = useDebounce(orderCode)

  const role = session?.role ?? null
  const podeCriar = canCreateTicket(role)

  const { data: brands } = useQuery({
    queryKey: ["marcas"],
    queryFn: () => listCatalog("marcas"),
  })
  const { data, isLoading } = useQuery({
    queryKey: [
      "tickets",
      {
        status,
        brandId,
        debouncedCustomer,
        debouncedOrder,
        priority,
        overdue,
        productId,
        sort,
        order,
        page,
        customerId,
      },
    ],
    queryFn: () =>
      listTickets({
        status: status || undefined,
        brandId: brandId || undefined,
        customer: debouncedCustomer || undefined,
        orderCode: debouncedOrder || undefined,
        priority: priority || undefined,
        overdue: overdue || undefined,
        productId: productId || undefined,
        sort,
        order,
        customerId,
        page,
        perPage: PER_PAGE,
      }),
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PER_PAGE)) : 1
  const columnCount = 8

  function onStatusChange(value: string) {
    setParam("status", value === ALL ? "" : value)
  }

  function onBrandChange(value: string) {
    setParam("brand_id", value === ALL ? "" : value)
  }

  function onCustomerChange(value: string) {
    setParam("customer", value)
  }

  function onOrderChange(value: string) {
    setParam("order_code", value)
  }

  function onPriorityChange(value: string) {
    setParam("priority", value === ALL ? "" : value)
  }

  function onOverdueChange(checked: boolean) {
    setParam("overdue", checked ? "1" : "")
  }

  function onSortChange(value: string) {
    setParam("sort", value)
  }

  function onToggleOrder() {
    setParam("order", order === "asc" ? "desc" : "asc")
  }

  function onClear() {
    setProductQuery("")
    setSearchParams(new URLSearchParams(), { replace: true })
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Filtros</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="filtro-status">Status</Label>
            <Select value={status || ALL} onValueChange={onStatusChange}>
              <SelectTrigger id="filtro-status" className="w-full">
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Todos</SelectItem>
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="filtro-marca">Marca</Label>
            <Select value={brandId || ALL} onValueChange={onBrandChange}>
              <SelectTrigger id="filtro-marca" className="w-full">
                <SelectValue placeholder="Todas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Todas</SelectItem>
                {(brands ?? []).map((brand) => (
                  <SelectItem key={brand.id} value={brand.id}>
                    {brand.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="filtro-cliente">Cliente</Label>
            <Input
              id="filtro-cliente"
              placeholder="Nome ou documento"
              value={customer}
              onChange={(e) => onCustomerChange(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="filtro-produto">Produto</Label>
            <AutocompleteField
              id="filtro-produto"
              placeholder="Buscar produto por nome ou SKU"
              value={productQuery}
              onValueChange={(value) => {
                setProductQuery(value)
                setParam("product_id", "")
              }}
              onSelect={(option) => {
                setProductQuery(option.label)
                setParam("product_id", option.id)
              }}
              queryKey="filtro-produto"
              fetchOptions={async (search) => {
                const results = await listProducts({ search, perPage: 10 })
                return results.items.map((product) => ({
                  id: product.id,
                  label: product.name,
                  sublabel: product.sku,
                }))
              }}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="filtro-pedido">Pedido</Label>
            <Input
              id="filtro-pedido"
              placeholder="Codigo do pedido"
              value={orderCode}
              onChange={(e) => onOrderChange(e.target.value)}
              className="font-mono"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="filtro-prioridade">Prioridade</Label>
            <Select value={priority || ALL} onValueChange={onPriorityChange}>
              <SelectTrigger id="filtro-prioridade" className="w-full">
                <SelectValue placeholder="Todas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Todas</SelectItem>
                {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="filtro-ordenar">Ordenar por</Label>
            <div className="flex gap-2">
              <Select value={sort} onValueChange={onSortChange}>
                <SelectTrigger id="filtro-ordenar" className="w-full">
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
                size="icon"
                onClick={onToggleOrder}
                aria-label={order === "asc" ? "Ordem crescente" : "Ordem decrescente"}
              >
                {order === "asc" ? (
                  <ArrowUp size={16} strokeWidth={1.5} />
                ) : (
                  <ArrowDown size={16} strokeWidth={1.5} />
                )}
              </Button>
            </div>
          </div>

          <div className="flex items-center gap-2 self-end pb-2">
            <Checkbox
              id="filtro-atrasados"
              checked={overdue}
              onCheckedChange={(checked) => onOverdueChange(checked === true)}
            />
            <Label htmlFor="filtro-atrasados" className="font-normal">
              Somente atrasados
            </Label>
          </div>

          <div className="flex items-end">
            <Button variant="ghost" onClick={onClear} className="self-end">
              Limpar
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
          <CardTitle className="flex items-baseline gap-2 text-lg font-semibold tracking-tight text-foreground">
            Tickets
            <span className="text-sm font-normal text-muted-foreground">
              {data ? `${data.total} ticket(s)` : ""}
            </span>
          </CardTitle>
          {podeCriar && (
            <Button onClick={() => navigate("/tickets/novo")}>
              <Plus size={20} strokeWidth={1.5} />
              Novo ticket
            </Button>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Numero</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Produto</TableHead>
                  <TableHead>Prioridade</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>SLA</TableHead>
                  <TableHead>Atendente</TableHead>
                  <TableHead>Abertura</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={columnCount} className="text-center text-muted-foreground">
                      Carregando tickets...
                    </TableCell>
                  </TableRow>
                ) : (data?.items ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={columnCount} className="text-center text-muted-foreground">
                      Nenhum ticket para este filtro.
                    </TableCell>
                  </TableRow>
                ) : (
                  (data?.items ?? []).map((item) => (
                    <TableRow
                      key={item.id}
                      className={cn(
                        "relative border-l-[3px]",
                        STATUS_ACCENTS[item.status],
                        item.unread && "bg-primary/[0.04]",
                      )}
                    >
                      <TableCell className="font-mono">
                        <Link
                          to={`/tickets/${item.id}`}
                          className="absolute inset-0"
                          aria-label={`Abrir ticket numero ${item.number}`}
                        />
                        <span className="relative z-10 flex items-center gap-2">
                          {item.unread && (
                            <>
                              <span
                                className="size-1.5 shrink-0 rounded-full bg-primary"
                                aria-hidden
                              />
                              <span className="sr-only">Nao lido</span>
                            </>
                          )}
                          #{item.number}
                        </span>
                      </TableCell>
                      <TableCell>{item.customer_name ?? "-"}</TableCell>
                      <TableCell>
                        {item.first_product_name ?? "-"}
                        {item.items_count > 1 && (
                          <span className="ml-1 text-xs text-muted-foreground">
                            +{item.items_count - 1}
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        <PriorityBadge priority={item.priority} />
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={item.status} />
                      </TableCell>
                      <TableCell>
                        <SlaBadge sla={item.sla} dueAt={item.due_at} />
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {item.attendant_name ?? "-"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {new Date(item.opened_at).toLocaleDateString("pt-BR")}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-end gap-2 text-sm text-muted-foreground">
            <Button
              variant="ghost"
              size="sm"
              disabled={page <= 1}
              onClick={() => setParam("page", String(page - 1))}
            >
              Anterior
            </Button>
            <span>
              Pagina {page} de {totalPages}
            </span>
            <Button
              variant="ghost"
              size="sm"
              disabled={!data || page >= totalPages}
              onClick={() => setParam("page", String(page + 1))}
            >
              Proxima
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
