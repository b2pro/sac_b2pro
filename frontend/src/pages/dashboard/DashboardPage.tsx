import { useQuery } from "@tanstack/react-query"
import { lazy, Suspense, useState } from "react"
import { Link } from "react-router-dom"

import { AvgResolutionStat } from "@/components/reporting/AvgResolutionStat"
import { EmptyState } from "@/components/reporting/EmptyState"
import { KpiCard } from "@/components/reporting/KpiCard"
import { RankingList } from "@/components/reporting/RankingList"
import { Skeleton } from "@/components/reporting/Skeleton"
import { ThCell } from "@/components/reporting/ThCell"
import { TicketRow } from "@/components/reporting/TicketRow"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ApiError } from "@/lib/api"
import { listCatalog } from "@/lib/cadastros"
import { getDashboard } from "@/lib/reporting"

// Recharts (usado apenas pelo grafico) e pesado o suficiente para estourar o
// aviso de chunk de 500kB, e Relatorios/Midias pagariam esse custo sem
// desenhar grafico nenhum. Carregado sob demanda com React.lazy; a exportacao
// e nomeada (nao default), entao adaptamos com .then(...).
const StatusDistributionChart = lazy(() =>
  import("@/components/reporting/StatusDistributionChart").then((mod) => ({
    default: mod.StatusDistributionChart,
  })),
)

// Mesma altura que o grafico calcula (9 status * ROW_HEIGHT de 28px + 24px de
// margem, ver StatusDistributionChart), para o fallback nao causar salto de
// layout enquanto o chunk carrega.
const CHART_FALLBACK_HEIGHT = "h-[276px]"

const ALL = "all"

const KPI_ORDER = [
  "total",
  "abertos",
  "aguardando_analise",
  "atrasados",
  "aprovados_no_mes",
  "declinados_no_mes",
  "finalizados_no_mes",
] as const

const KPI_LABELS: Record<(typeof KPI_ORDER)[number], string> = {
  total: "Total",
  abertos: "Abertos",
  aguardando_analise: "Aguardando analise",
  atrasados: "Atrasados (SLA)",
  aprovados_no_mes: "Aprovados no mes",
  declinados_no_mes: "Declinados no mes",
  finalizados_no_mes: "Finalizados no mes",
}

const RECENT_COLUMNS = ["No", "Cliente", "Produto", "Status", "SLA", "Ultima atividade"]

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

export default function DashboardPage() {
  const [brandId, setBrandId] = useState("")

  const { data: brands } = useQuery({
    queryKey: ["marcas", { active: true }],
    queryFn: () => listCatalog("marcas", { active: true }),
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", brandId],
    queryFn: () => getDashboard(brandId || undefined),
  })

  const kpiByKey = new Map(data?.kpis.map((kpi) => [kpi.key, kpi]) ?? [])
  const total = kpiByKey.get("total")?.count ?? 0
  const isVazio = !isLoading && !error && data !== undefined && total === 0

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-accent-foreground">Dashboard</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Visao geral de trocas e defeitos do tenant
          </p>
        </div>
        <Select value={brandId || ALL} onValueChange={(value) => setBrandId(value === ALL ? "" : value)}>
          <SelectTrigger aria-label="Filtrar por marca">
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
      </div>

      {isLoading && (
        <>
          <div className="mb-6 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
            {Array.from({ length: 7 }).map((_, index) => (
              <Skeleton key={index} className="h-[84px]" />
            ))}
          </div>
          <div className="flex flex-wrap items-start gap-4">
            <div className="flex-[2_1_560px] flex min-w-0 flex-col gap-4">
              <Skeleton className="h-[320px]" />
              <Skeleton className="h-[380px]" />
            </div>
            <div className="flex-[1_1_300px] flex min-w-0 flex-col gap-4">
              <Skeleton className="h-[110px]" />
              <Skeleton className="h-[190px]" />
              <Skeleton className="h-[190px]" />
            </div>
          </div>
        </>
      )}

      {!isLoading && error && (
        <EmptyState
          title="Nao foi possivel carregar o dashboard"
          description={errorMessage(error)}
        />
      )}

      {!isLoading && !error && data && isVazio && (
        <>
          <div className="mb-6 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
            {KPI_ORDER.map((key) => (
              <div
                key={key}
                className="min-w-0 rounded-md border border-border bg-card p-[14px_16px]"
              >
                <span className="text-xs leading-tight text-muted-foreground">
                  {KPI_LABELS[key]}
                </span>
                <div className="mt-1.5 font-mono text-[26px] font-semibold text-muted-foreground">
                  0
                </div>
              </div>
            ))}
          </div>
          <EmptyState
            title="Nenhum ticket registrado neste tenant"
            description="Os indicadores aparecem quando o primeiro ticket for aberto."
          />
        </>
      )}

      {!isLoading && !error && data && !isVazio && (
        <>
          <div className="mb-6 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
            {KPI_ORDER.map((key) => {
              const kpi = kpiByKey.get(key)
              if (!kpi) return null
              const params = new URLSearchParams({
                ...kpi.filters,
                ...(brandId ? { brand_id: brandId } : {}),
              })
              return (
                <KpiCard
                  key={key}
                  label={KPI_LABELS[key]}
                  value={kpi.count}
                  to={`/tickets?${params.toString()}`}
                  accent={key === "atrasados"}
                />
              )
            })}
          </div>

          <div className="flex flex-wrap items-start gap-4">
            <div className="flex-[2_1_560px] flex min-w-0 flex-col gap-4">
              <section className="rounded-md border border-border bg-card">
                <div className="border-b border-border px-4 py-3.5">
                  <h2 className="text-[13.5px] font-semibold text-accent-foreground">
                    Distribuicao por status
                  </h2>
                </div>
                <div className="px-4 pt-3.5 pb-2.5">
                  <Suspense fallback={<Skeleton className={CHART_FALLBACK_HEIGHT} />}>
                    <StatusDistributionChart counts={data.status_counts} />
                  </Suspense>
                </div>
              </section>

              <section className="rounded-md border border-border bg-card">
                <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3.5">
                  <h2 className="text-[13.5px] font-semibold text-accent-foreground">
                    Tickets recentes
                  </h2>
                  <Link to="/tickets" className="text-[12.5px] text-primary hover:text-primary/80">
                    Ver todos
                  </Link>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-[13px]">
                    <thead>
                      <tr>
                        {RECENT_COLUMNS.map((column, index) => (
                          <ThCell
                            key={column}
                            align={index === RECENT_COLUMNS.length - 1 ? "right" : "left"}
                          >
                            {column}
                          </ThCell>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent.map((item) => (
                        <TicketRow key={item.id} item={item} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>

            <div className="flex-[1_1_300px] flex min-w-0 flex-col gap-4">
              <AvgResolutionStat
                hours={data.avg_resolution_hours}
                caption="da abertura a finalizacao, no recorte atual"
              />
              <RankingList title="Top 5 produtos" rows={data.products} />
              <RankingList title="Top 5 defeitos" rows={data.defects} />
              <RankingList title="Top 5 solucoes" rows={data.solutions} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
