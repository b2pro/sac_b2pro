import { useQuery } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"

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
import { listCatalog } from "@/lib/cadastros"
import {
  canCreateTicket,
  listTickets,
  PRIORITY_LABELS,
  STATUS_LABELS,
  type TicketPriority,
  type TicketStatus,
} from "@/lib/tickets"
import { useDebounce } from "@/lib/useDebounce"
import { cn } from "@/lib/utils"

const PER_PAGE = 20
const ALL = "all"

export default function TicketsListPage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState<TicketStatus | "">(
    (searchParams.get("status") as TicketStatus) ?? "",
  )
  const [brandId, setBrandId] = useState("")
  const [customer, setCustomer] = useState(searchParams.get("customer") ?? "")
  const [orderCode, setOrderCode] = useState("")
  const [priority, setPriority] = useState<TicketPriority | "">("")
  const [overdue, setOverdue] = useState(searchParams.get("overdue") === "1")
  const [page, setPage] = useState(1)
  const customerId = searchParams.get("customer_id") ?? undefined

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
      { status, brandId, debouncedCustomer, debouncedOrder, priority, overdue, page, customerId },
    ],
    queryFn: () =>
      listTickets({
        status: status || undefined,
        brandId: brandId || undefined,
        customer: debouncedCustomer || undefined,
        orderCode: debouncedOrder || undefined,
        priority: priority || undefined,
        overdue: overdue || undefined,
        customerId,
        page,
        perPage: PER_PAGE,
      }),
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PER_PAGE)) : 1
  const columnCount = 8

  function onStatusChange(value: string) {
    setStatus(value === ALL ? "" : (value as TicketStatus))
    setPage(1)
  }

  function onBrandChange(value: string) {
    setBrandId(value === ALL ? "" : value)
    setPage(1)
  }

  function onCustomerChange(value: string) {
    setCustomer(value)
    setPage(1)
  }

  function onOrderChange(value: string) {
    setOrderCode(value)
    setPage(1)
  }

  function onPriorityChange(value: string) {
    setPriority(value === ALL ? "" : (value as TicketPriority))
    setPage(1)
  }

  function onOverdueChange(checked: boolean) {
    setOverdue(checked)
    setPage(1)
  }

  function onClear() {
    setStatus("")
    setBrandId("")
    setCustomer("")
    setOrderCode("")
    setPriority("")
    setOverdue(false)
    setPage(1)
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
                      <TableCell className="relative font-mono">
                        <Link
                          to={`/tickets/${item.id}`}
                          className="absolute inset-0"
                          aria-label={`Abrir ticket numero ${item.number}`}
                        />
                        <span className="relative flex items-center gap-2">
                          {item.unread && (
                            <span className="size-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
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
              onClick={() => setPage((p) => p - 1)}
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
              onClick={() => setPage((p) => p + 1)}
            >
              Proxima
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
