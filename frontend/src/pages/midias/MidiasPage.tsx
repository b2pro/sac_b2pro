import { useInfiniteQuery, useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"

import { InfiniteScrollSentinel } from "@/components/media/InfiniteScrollSentinel"
import { MediaLightbox, type LightboxItem } from "@/components/media/MediaLightbox"
import { MediaTile } from "@/components/media/MediaTile"
import { EmptyState } from "@/components/reporting/EmptyState"
import { FiltersCard } from "@/components/reporting/FiltersCard"
import { AutocompleteField } from "@/components/tickets/AutocompleteField"
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
import { attachmentUrl } from "@/lib/attachments"
import { listCatalog, listProducts } from "@/lib/cadastros"
import { listMedia, type MediaItem, type MediaKindFilter, type MediaParams } from "@/lib/reporting"
import { STATUS_LABELS, type TicketStatus } from "@/lib/tickets"
import { cn } from "@/lib/utils"

const ALL = "all"
const PER_PAGE = 30
const KIND_VALUES: MediaKindFilter[] = ["imagem", "pdf", "video"]
const KIND_LABELS: Record<MediaKindFilter, string> = {
  imagem: "Imagem",
  pdf: "PDF",
  video: "Video",
}
const STATUS_VALUES = Object.keys(STATUS_LABELS) as TicketStatus[]

function isValidIso(value: string): boolean {
  return !Number.isNaN(new Date(value).getTime())
}

// a API filtra created_at < ate, entao o dia final escolhido precisa entrar
// inteiro: guardamos o dia seguinte a meia-noite UTC (mesma convencao de
// Relatorios).
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

// "ate" invalido (URL editada a mao) e tratado como ausente: nao vai para a
// API e nao quebra o input de data com um Invalid Date.
function isoEndExclusiveToDateInput(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  date.setUTCDate(date.getUTCDate() - 1)
  return date.toISOString().slice(0, 10)
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("rounded-md bg-muted motion-safe:animate-pulse", className)} />
}

export default function MidiasPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [productQuery, setProductQuery] = useState("")
  const [defectQuery, setDefectQuery] = useState("")
  const [solutionQuery, setSolutionQuery] = useState("")
  const [lightboxItem, setLightboxItem] = useState<LightboxItem | null>(null)

  // Filtros aqui aplicam na hora (sem rascunho + botao Filtrar, diferente de
  // Relatorios): cada campo escreve direto na URL.
  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next, { replace: true })
  }

  const kindParam = searchParams.get("kind")
  const kind =
    kindParam && KIND_VALUES.includes(kindParam as MediaKindFilter)
      ? (kindParam as MediaKindFilter)
      : undefined
  const brandId = searchParams.get("brand_id") || undefined
  const productId = searchParams.get("product_id") || undefined
  const defectTypeId = searchParams.get("defect_type_id") || undefined
  const solutionTypeId = searchParams.get("solution_type_id") || undefined
  const statusParam = searchParams.get("status")
  const status =
    statusParam && STATUS_VALUES.includes(statusParam as TicketStatus)
      ? (statusParam as TicketStatus)
      : undefined
  const de = searchParams.get("de") || undefined
  const rawAte = searchParams.get("ate")
  const ate = rawAte && isValidIso(rawAte) ? rawAte : undefined

  const deInput = de ? isoToDateInput(de) : ""
  const ateInput = ate ? isoEndExclusiveToDateInput(ate) : ""

  const params: MediaParams = {
    kind,
    brandId,
    productId,
    defectTypeId,
    solutionTypeId,
    status,
    de,
    ate,
    perPage: PER_PAGE,
  }

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: ["midias", params],
    queryFn: ({ pageParam }) => listMedia({ ...params, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page * last.per_page < last.total ? last.page + 1 : undefined,
  })

  const { data: brands } = useQuery({ queryKey: ["marcas"], queryFn: () => listCatalog("marcas") })

  const items: MediaItem[] = data?.pages.flatMap((page) => page.items) ?? []
  const total = data?.pages[0]?.total ?? 0
  const isCarregandoInicial = isLoading
  const isVazio = !isLoading && total === 0
  const isPadrao = !isLoading && total > 0

  async function openLightbox(item: MediaItem) {
    setLightboxItem({
      kind: item.kind,
      filename: item.filename,
      contentType: item.content_type,
      sizeBytes: item.size_bytes,
      createdAt: item.created_at,
      url: null,
      ticketId: item.ticket_id,
      ticketNumber: item.ticket_number,
    })
    try {
      const variant = item.kind === "imagem" ? "medio" : "original"
      const { url } = await attachmentUrl(item.ticket_id, item.id, variant)
      setLightboxItem((current) =>
        current && current.filename === item.filename && current.createdAt === item.created_at
          ? { ...current, url }
          : current,
      )
    } catch (error) {
      toast.error(errorMessage(error))
      setLightboxItem(null)
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-accent-foreground">Midias</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Todos os anexos de tickets do tenant — fotos, notas fiscais e videos
        </p>
      </div>

      <FiltersCard storageKey="midias.filtros">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="midias-tipo">Tipo</Label>
          <Select
            value={kind ?? ALL}
            onValueChange={(value) => setParam("kind", value === ALL ? "" : value)}
          >
            <SelectTrigger id="midias-tipo" className="w-full">
              <SelectValue placeholder="Todos" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Todos</SelectItem>
              {KIND_VALUES.map((value) => (
                <SelectItem key={value} value={value}>
                  {KIND_LABELS[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="midias-marca">Marca</Label>
          <Select
            value={brandId ?? ALL}
            onValueChange={(value) => setParam("brand_id", value === ALL ? "" : value)}
          >
            <SelectTrigger id="midias-marca" className="w-full">
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
          <Label htmlFor="midias-status">Status</Label>
          <Select
            value={status ?? ALL}
            onValueChange={(value) => setParam("status", value === ALL ? "" : value)}
          >
            <SelectTrigger id="midias-status" className="w-full">
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
          <Label htmlFor="midias-produto">Produto</Label>
          <AutocompleteField
            id="midias-produto"
            placeholder="Buscar produto"
            value={productQuery}
            onValueChange={(value) => {
              setProductQuery(value)
              setParam("product_id", "")
            }}
            onSelect={(option) => {
              setProductQuery(option.label)
              setParam("product_id", option.id)
            }}
            queryKey="midias-produto"
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
          <Label htmlFor="midias-defeito">Defeito</Label>
          <AutocompleteField
            id="midias-defeito"
            placeholder="Buscar defeito"
            value={defectQuery}
            onValueChange={(value) => {
              setDefectQuery(value)
              setParam("defect_type_id", "")
            }}
            onSelect={(option) => {
              setDefectQuery(option.label)
              setParam("defect_type_id", option.id)
            }}
            queryKey="midias-defeito"
            fetchOptions={async (search) => {
              const results = await listCatalog("defeitos", { search })
              return results.map((item) => ({ id: item.id, label: item.name }))
            }}
          />
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="midias-solucao">Solucao</Label>
          <AutocompleteField
            id="midias-solucao"
            placeholder="Buscar solucao"
            value={solutionQuery}
            onValueChange={(value) => {
              setSolutionQuery(value)
              setParam("solution_type_id", "")
            }}
            onSelect={(option) => {
              setSolutionQuery(option.label)
              setParam("solution_type_id", option.id)
            }}
            queryKey="midias-solucao"
            fetchOptions={async (search) => {
              const results = await listCatalog("solucoes", { search })
              return results.map((item) => ({ id: item.id, label: item.name }))
            }}
          />
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="midias-de">Periodo — de</Label>
          <Input
            id="midias-de"
            type="date"
            value={deInput}
            onChange={(e) => setParam("de", e.target.value ? isoStart(e.target.value) : "")}
            className="font-mono text-[12.5px]"
          />
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="midias-ate">Periodo — ate</Label>
          <Input
            id="midias-ate"
            type="date"
            value={ateInput}
            onChange={(e) => setParam("ate", e.target.value ? isoEndExclusive(e.target.value) : "")}
            className="font-mono text-[12.5px]"
          />
        </div>
      </FiltersCard>

      {isCarregandoInicial && (
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(160px,1fr))]">
          {Array.from({ length: 12 }).map((_, index) => (
            <div key={index}>
              <Skeleton className="aspect-square" />
              <Skeleton className="mt-2 h-3 w-[70%]" />
            </div>
          ))}
        </div>
      )}

      {isVazio && (
        <EmptyState
          title="Nenhum anexo para este filtro"
          description="Ajuste os criterios acima ou limpe os filtros para ver todos os anexos."
        />
      )}

      {isPadrao && (
        <>
          <p className="mb-3 text-[12.5px] text-muted-foreground">
            <span className="font-mono">{total}</span> anexos encontrados
          </p>
          <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(160px,1fr))]">
            {items.map((item) => (
              <MediaTile key={item.id} item={item} onOpen={openLightbox} />
            ))}
          </div>
          <InfiniteScrollSentinel
            hasMore={hasNextPage ?? false}
            loading={isFetchingNextPage}
            total={total}
            onIntersect={() => fetchNextPage()}
          />
        </>
      )}

      <MediaLightbox item={lightboxItem} onClose={() => setLightboxItem(null)} showTicketLink />
    </div>
  )
}
