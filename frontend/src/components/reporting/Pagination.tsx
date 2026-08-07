import { ChevronLeft, ChevronRight } from "lucide-react"

export function Pagination({
  page,
  perPage,
  total,
  onPage,
}: {
  page: number
  perPage: number
  total: number
  onPage: (page: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(total / perPage))
  const start = total === 0 ? 0 : (page - 1) * perPage + 1
  const end = Math.min(page * perPage, total)

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border p-2.5 px-4">
      <span className="text-xs text-muted-foreground">
        Mostrando <span className="font-mono">{start}</span>
        {"–"}
        <span className="font-mono">{end}</span> de <span className="font-mono">{total}</span>
      </span>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          disabled={page <= 1}
          aria-label="Página anterior"
          onClick={() => onPage(page - 1)}
          className="flex size-[30px] items-center justify-center rounded-md border border-border text-foreground enabled:hover:border-foreground disabled:cursor-default disabled:text-muted-foreground/60"
        >
          <ChevronLeft size={15} strokeWidth={1.5} />
        </button>
        <span className="px-1.5 font-mono text-xs text-foreground">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          aria-label="Próxima página"
          onClick={() => onPage(page + 1)}
          className="flex size-[30px] items-center justify-center rounded-md border border-border text-foreground enabled:hover:border-foreground disabled:cursor-default disabled:text-muted-foreground/60"
        >
          <ChevronRight size={15} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  )
}
