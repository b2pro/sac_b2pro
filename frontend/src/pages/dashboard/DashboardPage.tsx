import { useQuery } from "@tanstack/react-query"
import { Component, lazy, Suspense, type ReactNode } from "react"
import { Link, useSearchParams } from "react-router-dom"

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
import { cn } from "@/lib/utils"

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

// Suspense so cobre o carregamento; se o import() do chunk falhar (deploy
// com hash antigo, rede instavel), React lanca o erro para cima e sem uma
// boundary aqui ele derruba a pagina inteira. Este boundary local restringe
// a falha ao card do grafico, mantendo o resto do dashboard funcionando.
class ChartLoadBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className={cn(CHART_FALLBACK_HEIGHT, "flex items-center justify-center")}>
          <EmptyState
            title="Não foi possível carregar o gráfico"
            description="Atualize a página para tentar novamente."
          />
        </div>
      )
    }
    return this.props.children
  }
}

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
  aguardando_analise: "Aguardando análise",
  atrasados: "Atrasados (SLA)",
  aprovados_no_mes: "Aprovados no mês",
  declinados_no_mes: "Declinados no mês",
  finalizados_no_mes: "Finalizados no mês",
}

// Textos do "title" (tooltip nativo) de cada KpiCard, do mockup Dashboard.dc.html.
// Os dois "no mes" usam "atual" em vez do mes fixo do mockup (que era so um
// valor de demonstracao) para nao ficar errado o resto do ano.
const KPI_TOOLTIPS: Record<(typeof KPI_ORDER)[number], string> = {
  total: "Ver todos os tickets",
  abertos: "Tickets com status Aberto",
  aguardando_analise: "Tickets aguardando análise",
  atrasados: "Tickets com SLA vencido",
  aprovados_no_mes: "Aprovados no mês atual",
  declinados_no_mes: "Declinados no mês atual",
  finalizados_no_mes: "Finalizados no mês atual",
}

const RECENT_COLUMNS = ["Nº", "Cliente", "Produto", "Status", "SLA", "Última atividade"]

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

export default function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  // Mesmo padrao setParam de Relatorios/Midias: filtro direto na URL, para
  // ficar compartilhavel por link e sobreviver a navegacao de volta.
  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next, { replace: true })
  }

  const brandId = searchParams.get("brand_id") || ""

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
            Visão geral de trocas e defeitos do tenant
          </p>
        </div>
        <Select
          value={brandId || ALL}
          onValueChange={(value) => setParam("brand_id", value === ALL ? "" : value)}
        >
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
          title="Não foi possível carregar o dashboard"
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
            title={
              brandId ? "Nenhum ticket para a marca selecionada" : "Nenhum ticket registrado neste tenant"
            }
            description={
              brandId
                ? "Troque o filtro de marca ou selecione Todas as marcas para ver os demais tickets do tenant."
                : "Os indicadores aparecem quando o primeiro ticket for aberto."
            }
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
                  title={KPI_TOOLTIPS[key]}
                />
              )
            })}
          </div>

          <div className="flex flex-wrap items-start gap-4">
            <div className="flex-[2_1_560px] flex min-w-0 flex-col gap-4">
              <section className="rounded-md border border-border bg-card">
                <div className="border-b border-border px-4 py-3.5">
                  <h2 className="text-[13.5px] font-semibold text-accent-foreground">
                    Distribuição por status
                  </h2>
                </div>
                <div className="px-4 pt-3.5 pb-2.5">
                  <ChartLoadBoundary>
                    <Suspense fallback={<Skeleton className={CHART_FALLBACK_HEIGHT} />}>
                      <StatusDistributionChart counts={data.status_counts} />
                    </Suspense>
                  </ChartLoadBoundary>
                </div>
              </section>

              <section className="rounded-md border border-border bg-card">
                <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3.5">
                  <h2 className="text-[13.5px] font-semibold text-accent-foreground">
                    Tickets recentes
                  </h2>
                  <Link to="/tickets" className="text-[12.5px] text-primary-text hover:underline">
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
                caption="da abertura à finalização, no recorte atual"
              />
              <RankingList title="Top 5 produtos" rows={data.products} />
              <RankingList title="Top 5 defeitos" rows={data.defects} />
              <RankingList title="Top 5 soluções" rows={data.solutions} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
