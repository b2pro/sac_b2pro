import { api, apiBlob } from "@/lib/api"
import type { TicketListItem, TicketStatus } from "@/lib/tickets"

export type RankingEntry = { id: string; name: string; count: number }

export type DashboardKpi = { key: string; count: number; filters: Record<string, string> }

export type Dashboard = {
  kpis: DashboardKpi[]
  status_counts: Record<TicketStatus, number>
  products: RankingEntry[]
  defects: RankingEntry[]
  solutions: RankingEntry[]
  avg_resolution_hours: number | null
  recent: TicketListItem[]
}

export type ReportParams = {
  de?: string
  ate?: string
  brandId?: string
  productId?: string
  defectTypeId?: string
  solutionTypeId?: string
  status?: TicketStatus
  atendenteId?: string
  channelId?: string
  page?: number
  perPage?: number
}

export type Report = {
  kpis: { total: number; finalized: number; declined: number; avg_resolution_hours: number | null }
  products: RankingEntry[]
  defects: RankingEntry[]
  solutions: RankingEntry[]
  items: TicketListItem[]
  total: number
  page: number
  per_page: number
}

export type MediaKindFilter = "imagem" | "pdf" | "video"

export type MediaItem = {
  id: string
  ticket_id: string
  ticket_number: number
  filename: string
  kind: MediaKindFilter
  content_type: string
  size_bytes: number
  created_at: string
  preview_url: string | null
}

export type MediaParams = {
  kind?: MediaKindFilter
  brandId?: string
  productId?: string
  defectTypeId?: string
  solutionTypeId?: string
  status?: TicketStatus
  de?: string
  ate?: string
  page?: number
  perPage?: number
}

export type MediaPage = { items: MediaItem[]; total: number; page: number; per_page: number }

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== false) search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ""
}

function mapReportParams(params: ReportParams) {
  return {
    de: params.de,
    ate: params.ate,
    brand_id: params.brandId,
    product_id: params.productId,
    defect_type_id: params.defectTypeId,
    solution_type_id: params.solutionTypeId,
    status: params.status,
    atendente_id: params.atendenteId,
    channel_id: params.channelId,
    page: params.page,
    per_page: params.perPage,
  }
}

function mapMediaParams(params: MediaParams) {
  return {
    kind: params.kind,
    brand_id: params.brandId,
    product_id: params.productId,
    defect_type_id: params.defectTypeId,
    solution_type_id: params.solutionTypeId,
    status: params.status,
    de: params.de,
    ate: params.ate,
    page: params.page,
    per_page: params.perPage,
  }
}

export const getDashboard = (brandId?: string) =>
  api<Dashboard>(`/dashboard${query({ brand_id: brandId })}`)

export const getReport = (params: ReportParams) =>
  api<Report>(`/relatorios${query(mapReportParams(params))}`)

export const listMedia = (params: MediaParams) =>
  api<MediaPage>(`/midias${query(mapMediaParams(params))}`)

export async function downloadReportCsv(params: ReportParams): Promise<void> {
  const blob = await apiBlob(`/relatorios/export${query(mapReportParams(params))}`)
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "relatorio-tickets.csv"
  a.click()
  URL.revokeObjectURL(url)
}
