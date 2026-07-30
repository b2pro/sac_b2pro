import type { RankingEntry } from "@/lib/reporting"

export function RankingList({ title, rows }: { title: string; rows: RankingEntry[] }) {
  const max = rows.reduce((acc, row) => Math.max(acc, row.count), 0)

  return (
    <section className="rounded-md border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h2 className="text-[13px] font-semibold text-accent-foreground">{title}</h2>
      </div>
      <div className="flex flex-col gap-2.5 px-4 py-3">
        {rows.length === 0 ? (
          <p className="text-xs text-muted-foreground">Sem dados no recorte</p>
        ) : (
          rows.map((row) => (
            <div key={row.id} className="min-w-0">
              <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
                <span className="min-w-0 truncate" title={row.name}>
                  {row.name}
                </span>
                <span className="shrink-0 font-mono text-xs text-muted-foreground">
                  {row.count}
                </span>
              </div>
              <div className="mt-1 h-1 rounded-sm bg-muted">
                <div
                  className="h-1 rounded-sm bg-foreground"
                  style={{ width: `${max > 0 ? (row.count / max) * 100 : 0}%` }}
                />
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  )
}
