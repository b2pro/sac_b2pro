import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useSearchParams } from "react-router-dom"

import { ActiveFilterChips } from "@/components/reporting/ActiveFilterChips"
import { EmptyState } from "@/components/reporting/EmptyState"
import { ExportCsvButton } from "@/components/reporting/ExportCsvButton"
import { FiltersCard } from "@/components/reporting/FiltersCard"
import { KpiCard } from "@/components/reporting/KpiCard"
import { Pagination } from "@/components/reporting/Pagination"
import { RankingList } from "@/components/reporting/RankingList"
import { TicketRow } from "@/components/reporting/TicketRow"
import { AutocompleteField } from "@/components/tickets/AutocompleteField"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ApiError } from "@/lib/api"
import { listCatalog, listProducts, type CatalogItem } from "@/lib/cadastros"
import { formatDuration } from "@/lib/format"
import { listMembers } from "@/lib/members"
import { downloadReportCsv, getReport, type ReportParams } from "@/lib/reporting"
import { STATUS_LABELS, type TicketStatus } from "@/lib/tickets"
import { cn } from "@/lib/utils"

const ALL = "all"
const PER_PAGE = 25
const STATUS_VALUES = Object.keys(STATUS_LABELS) as TicketStatus[]
const FILTER_KEYS = [
  "de",
  "ate",
  "brand_id",
  "product_id",
  "defect_type_id",
  "solution_type_id",
  "status",
  "atendente_id",
  "channel_id",
] as const

const RESULT_COLUMNS = [
  "No",
  "Cliente",
  "Produto",
  "Status",
  "Prioridade",
  "SLA",
  "Atendente",
  "Ultima atividade",
]

type Draft = {
  de: string
  ate: string
  brandId: string
  status: TicketStatus | ""
  atendenteId: string
  productId: string
  productQuery: string
  defectTypeId: string
  defectQuery: string
  solutionTypeId: string
  solutionQuery: string
  channelId: string
  channelQuery: string
}

function emptyDraft(): Draft {
  return {
    de: "",
    ate: "",
    brandId: "",
    status: "",
    atendenteId: "",
    productId: "",
    productQuery: "",
    defectTypeId: "",
    defectQuery: "",
    solutionTypeId: "",
    solutionQuery: "",
    channelId: "",
    channelQuery: "",
  }
}

// a API filtra opened_at < ate, entao o dia final escolhido precisa entrar
// inteiro: guardamos o dia seguinte a meia-noite UTC.
function isoStart(dateInput: string): string {
  return new Date(`${dateInput}T00:00:00Z`).toISOString()
}

function isoEndExclusive(dateInput: string): string {
  const date = new Date(`${dateInput}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + 1)
  return date.toISOString()
}

function isoToDateInput(iso: string): string {
  return iso.slice(0, 10)
}

function isoEndExclusiveToDateInput(iso: string): string {
  const date = new Date(iso)
  date.setUTCDate(date.getUTCDate() - 1)
  return date.toISOString().slice(0, 10)
}

function formatDateBR(dateInput: string): string {
  const [y, m, d] = dateInput.split("-")
  return `${d}/${m}/${y}`
}

function draftFromParams(params: URLSearchParams): Draft {
  const de = params.get("de")
  const ate = params.get("ate")
  const status = params.get("status")
  return {
    de: de ? isoToDateInput(de) : "",
    ate: ate ? isoEndExclusiveToDateInput(ate) : "",
    brandId: params.get("brand_id") ?? "",
    status: status && STATUS_VALUES.includes(status as TicketStatus) ? (status as TicketStatus) : "",
    atendenteId: params.get("atendente_id") ?? "",
    productId: params.get("product_id") ?? "",
    productQuery: "",
    defectTypeId: params.get("defect_type_id") ?? "",
    defectQuery: "",
    solutionTypeId: params.get("solution_type_id") ?? "",
    solutionQuery: "",
    channelId: params.get("channel_id") ?? "",
    channelQuery: "",
  }
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

function catalogName(list: CatalogItem[] | undefined, id: string): string {
  return list?.find((item) => item.id === id)?.name ?? id
}

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("rounded-md bg-muted motion-safe:animate-pulse", className)} />
}

function ThCell({ align = "left", children }: { align?: "left" | "right"; children: string }) {
  return (
    <th
      className={cn(
        "border-b border-border px-2.5 py-2 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase",
        align === "left" ? "pl-3.5 text-left" : "pr-4 text-right",
      )}
    >
      {children}
    </th>
  )
}

export default function RelatoriosPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [draft, setDraft] = useState<Draft>(() => draftFromParams(searchParams))
  const [appliedProductLabel, setAppliedProductLabel] = useState<string | undefined>(undefined)

  function patchDraft(patch: Partial<Draft>) {
    setDraft((current) => ({ ...current, ...patch }))
  }

  const temFiltro = FILTER_KEYS.some((key) => !!searchParams.get(key))

  const pageBruta = Number(searchParams.get("page"))
  const page = Number.isFinite(pageBruta) && pageBruta > 0 ? Math.trunc(pageBruta) : 1

  const statusParam = searchParams.get("status")
  const status =
    statusParam && STATUS_VALUES.includes(statusParam as TicketStatus)
      ? (statusParam as TicketStatus)
      : undefined

  const params: ReportParams = {
    de: searchParams.get("de") || undefined,
    ate: searchParams.get("ate") || undefined,
    brandId: searchParams.get("brand_id") || undefined,
    productId: searchParams.get("product_id") || undefined,
    defectTypeId: searchParams.get("defect_type_id") || undefined,
    solutionTypeId: searchParams.get("solution_type_id") || undefined,
    status,
    atendenteId: searchParams.get("atendente_id") || undefined,
    channelId: searchParams.get("channel_id") || undefined,
    page,
    perPage: PER_PAGE,
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ["relatorio", params],
    queryFn: () => getReport(params),
    enabled: temFiltro,
  })

  const { data: brands } = useQuery({ queryKey: ["marcas"], queryFn: () => listCatalog("marcas") })
  const { data: members } = useQuery({ queryKey: ["membros"], queryFn: () => listMembers() })
  const { data: defectsAll } = useQuery({
    queryKey: ["defeitos-todos"],
    queryFn: () => listCatalog("defeitos"),
  })
  const { data: solutionsAll } = useQuery({
    queryKey: ["solucoes-todas"],
    queryFn: () => listCatalog("solucoes"),
  })
  const { data: channelsAll } = useQuery({
    queryKey: ["canais-todos"],
    queryFn: () => listCatalog("canais"),
  })

  function applyFilters() {
    const next = new URLSearchParams()
    if (draft.de) next.set("de", isoStart(draft.de))
    if (draft.ate) next.set("ate", isoEndExclusive(draft.ate))
    if (draft.brandId) next.set("brand_id", draft.brandId)
    if (draft.status) next.set("status", draft.status)
    if (draft.atendenteId) next.set("atendente_id", draft.atendenteId)
    if (draft.productId) next.set("product_id", draft.productId)
    if (draft.defectTypeId) next.set("defect_type_id", draft.defectTypeId)
    if (draft.solutionTypeId) next.set("solution_type_id", draft.solutionTypeId)
    if (draft.channelId) next.set("channel_id", draft.channelId)
    setAppliedProductLabel(draft.productId ? draft.productQuery : undefined)
    setSearchParams(next, { replace: true })
  }

  function clearFilters() {
    setDraft(emptyDraft())
    setAppliedProductLabel(undefined)
    setSearchParams(new URLSearchParams(), { replace: true })
  }

  function removeChip(key: string) {
    const next = new URLSearchParams(searchParams)
    next.delete(key)
    next.delete("page")
    setSearchParams(next, { replace: true })

    if (key === "de") patchDraft({ de: "" })
    else if (key === "ate") patchDraft({ ate: "" })
    else if (key === "brand_id") patchDraft({ brandId: "" })
    else if (key === "status") patchDraft({ status: "" })
    else if (key === "atendente_id") patchDraft({ atendenteId: "" })
    else if (key === "product_id") {
      patchDraft({ productId: "", productQuery: "" })
      setAppliedProductLabel(undefined)
    } else if (key === "defect_type_id") patchDraft({ defectTypeId: "", defectQuery: "" })
    else if (key === "solution_type_id") patchDraft({ solutionTypeId: "", solutionQuery: "" })
    else if (key === "channel_id") patchDraft({ channelId: "", channelQuery: "" })
  }

  function onPage(nextPage: number) {
    const next = new URLSearchParams(searchParams)
    next.set("page", String(nextPage))
    setSearchParams(next, { replace: true })
  }

  const chips: { key: string; label: string }[] = []
  const deParam = searchParams.get("de")
  const ateParam = searchParams.get("ate")
  const brandIdParam = searchParams.get("brand_id")
  const atendenteIdParam = searchParams.get("atendente_id")
  const productIdParam = searchParams.get("product_id")
  const defectIdParam = searchParams.get("defect_type_id")
  const solutionIdParam = searchParams.get("solution_type_id")
  const channelIdParam = searchParams.get("channel_id")
  if (deParam) chips.push({ key: "de", label: `De: ${formatDateBR(isoToDateInput(deParam))}` })
  if (ateParam)
    chips.push({ key: "ate", label: `Ate: ${formatDateBR(isoEndExclusiveToDateInput(ateParam))}` })
  if (brandIdParam)
    chips.push({
      key: "brand_id",
      label: `Marca: ${brands?.find((brand) => brand.id === brandIdParam)?.name ?? brandIdParam}`,
    })
  if (status) chips.push({ key: "status", label: `Status: ${STATUS_LABELS[status]}` })
  if (atendenteIdParam)
    chips.push({
      key: "atendente_id",
      label: `Atendente: ${members?.find((member) => member.id === atendenteIdParam)?.name ?? atendenteIdParam}`,
    })
  if (productIdParam)
    chips.push({
      key: "product_id",
      label: `Produto: ${appliedProductLabel ?? draft.productQuery ?? productIdParam}`,
    })
  if (defectIdParam)
    chips.push({ key: "defect_type_id", label: `Defeito: ${catalogName(defectsAll, defectIdParam)}` })
  if (solutionIdParam)
    chips.push({
      key: "solution_type_id",
      label: `Solucao: ${catalogName(solutionsAll, solutionIdParam)}`,
    })
  if (channelIdParam)
    chips.push({ key: "channel_id", label: `Canal: ${catalogName(channelsAll, channelIdParam)}` })

  const isInicial = !temFiltro
  const isCarregando = temFiltro && isLoading
  const isErro = temFiltro && !isLoading && !!error
  const isSemResultado = temFiltro && !isLoading && !error && data !== undefined && data.total === 0
  const isPadrao = temFiltro && !isLoading && !error && data !== undefined && data.total > 0

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-accent-foreground">Relatorios</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Recorte de tickets por periodo, marca, status e catalogo
        </p>
      </div>

      <FiltersCard
        storageKey="relatorios.filtros"
        footer={
          <>
            <Button type="button" variant="ghost" onClick={clearFilters}>
              Limpar
            </Button>
            <Button type="button" onClick={applyFilters}>
              Filtrar
            </Button>
          </>
        }
      >
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="relatorios-de">Periodo — de</Label>
          <Input
            id="relatorios-de"
            type="date"
            value={draft.de}
            onChange={(e) => patchDraft({ de: e.target.value })}
            className="font-mono text-[12.5px]"
          />
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="relatorios-ate">Periodo — ate</Label>
          <Input
            id="relatorios-ate"
            type="date"
            value={draft.ate}
            onChange={(e) => patchDraft({ ate: e.target.value })}
            className="font-mono text-[12.5px]"
          />
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="relatorios-marca">Marca</Label>
          <Select
            value={draft.brandId || ALL}
            onValueChange={(value) => patchDraft({ brandId: value === ALL ? "" : value })}
          >
            <SelectTrigger id="relatorios-marca" className="w-full">
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

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="relatorios-status">Status</Label>
          <Select
            value={draft.status || ALL}
            onValueChange={(value) =>
              patchDraft({ status: value === ALL ? "" : (value as TicketStatus) })
            }
          >
            <SelectTrigger id="relatorios-status" className="w-full">
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

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="relatorios-atendente">Atendente</Label>
          <Select
            value={draft.atendenteId || ALL}
            onValueChange={(value) => patchDraft({ atendenteId: value === ALL ? "" : value })}
          >
            <SelectTrigger id="relatorios-atendente" className="w-full">
              <SelectValue placeholder="Todos" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Todos</SelectItem>
              {(members ?? []).map((member) => (
                <SelectItem key={member.id} value={member.id}>
                  {member.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="relatorios-produto">Produto</Label>
          <AutocompleteField
            id="relatorios-produto"
            placeholder="Buscar produto"
            value={draft.productQuery}
            onValueChange={(value) => patchDraft({ productQuery: value, productId: "" })}
            onSelect={(option) => patchDraft({ productId: option.id, productQuery: option.label })}
            queryKey="relatorios-produto"
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

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="relatorios-defeito">Defeito</Label>
          <AutocompleteField
            id="relatorios-defeito"
            placeholder="Buscar defeito"
            value={draft.defectQuery}
            onValueChange={(value) => patchDraft({ defectQuery: value, defectTypeId: "" })}
            onSelect={(option) => patchDraft({ defectTypeId: option.id, defectQuery: option.label })}
            queryKey="relatorios-defeito"
            fetchOptions={async (search) => {
              const results = await listCatalog("defeitos", { search })
              return results.map((item) => ({ id: item.id, label: item.name }))
            }}
          />
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="relatorios-solucao">Solucao</Label>
          <AutocompleteField
            id="relatorios-solucao"
            placeholder="Buscar solucao"
            value={draft.solutionQuery}
            onValueChange={(value) => patchDraft({ solutionQuery: value, solutionTypeId: "" })}
            onSelect={(option) =>
              patchDraft({ solutionTypeId: option.id, solutionQuery: option.label })
            }
            queryKey="relatorios-solucao"
            fetchOptions={async (search) => {
              const results = await listCatalog("solucoes", { search })
              return results.map((item) => ({ id: item.id, label: item.name }))
            }}
          />
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="relatorios-canal">Canal</Label>
          <AutocompleteField
            id="relatorios-canal"
            placeholder="Buscar canal"
            value={draft.channelQuery}
            onValueChange={(value) => patchDraft({ channelQuery: value, channelId: "" })}
            onSelect={(option) => patchDraft({ channelId: option.id, channelQuery: option.label })}
            queryKey="relatorios-canal"
            fetchOptions={async (search) => {
              const results = await listCatalog("canais", { search })
              return results.map((item) => ({ id: item.id, label: item.name }))
            }}
          />
        </div>
      </FiltersCard>

      <ActiveFilterChips chips={chips} onRemove={removeChip} />

      {isInicial && (
        <EmptyState
          title="Nenhum filtro aplicado"
          description="Defina um periodo ou outro criterio acima e clique em Filtrar para gerar o relatorio."
        />
      )}

      {isCarregando && (
        <>
          <div className="mb-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-[84px]" />
            ))}
          </div>
          <div className="mb-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-[190px]" />
            ))}
          </div>
          <Skeleton className="h-[420px]" />
        </>
      )}

      {isErro && (
        <EmptyState
          title="Nao foi possivel carregar o relatorio"
          description={errorMessage(error)}
        />
      )}

      {isSemResultado && (
        <EmptyState
          title="Nenhum ticket para este filtro"
          description="Amplie o periodo ou remova um dos criterios ativos."
        />
      )}

      {isPadrao && data && (
        <>
          <div className="mb-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]">
            <KpiCard label="Total" value={data.kpis.total} caption="do recorte atual" />
            <KpiCard label="Finalizados" value={data.kpis.finalized} caption="do recorte atual" />
            <KpiCard label="Declinados" value={data.kpis.declined} caption="do recorte atual" />
            <KpiCard
              label="Tempo medio de resolucao"
              value={formatDuration(data.kpis.avg_resolution_hours)}
              caption="do recorte atual"
            />
          </div>

          <div className="mb-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
            <RankingList title="Top 5 produtos" rows={data.products} />
            <RankingList title="Top 5 defeitos" rows={data.defects} />
            <RankingList title="Top 5 solucoes" rows={data.solutions} />
          </div>

          <section className="rounded-md border border-border bg-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
              <h2 className="text-[13.5px] font-semibold text-accent-foreground">
                Resultados{" "}
                <span className="font-mono text-xs font-normal text-muted-foreground">
                  {data.total} tickets
                </span>
              </h2>
              <ExportCsvButton onExport={() => downloadReportCsv(params)} />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[13px]">
                <thead>
                  <tr>
                    {RESULT_COLUMNS.map((column, index) => (
                      <ThCell
                        key={column}
                        align={index === RESULT_COLUMNS.length - 1 ? "right" : "left"}
                      >
                        {column}
                      </ThCell>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <TicketRow key={item.id} item={item} showPriorityAndAttendant />
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={data.page} perPage={data.per_page} total={data.total} onPage={onPage} />
          </section>
        </>
      )}
    </div>
  )
}
