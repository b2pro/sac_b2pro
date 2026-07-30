import { formatDuration } from "@/lib/format"

export function AvgResolutionStat({
  hours,
  caption,
}: {
  hours: number | null
  caption?: string
}) {
  return (
    <section className="rounded-md border border-border bg-card p-[14px_16px]">
      <div className="text-xs text-muted-foreground">Tempo medio de resolucao</div>
      <div className="mt-1.5 font-mono text-3xl font-semibold text-accent-foreground">
        {formatDuration(hours)}
      </div>
      {caption && <div className="mt-0.5 text-[11.5px] text-muted-foreground">{caption}</div>}
    </section>
  )
}
