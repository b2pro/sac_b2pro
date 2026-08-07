import { cn } from "@/lib/utils"
import { formatAvgResolutionHours } from "@/lib/format"

export function AvgResolutionStat({
  hours,
  caption,
}: {
  hours: number | null
  caption?: string
}) {
  // Sem ticket finalizado no recorte: a frase substitui o numero, entao sai
  // do font-mono (reservado a numero/codigo, ver identidade visual) e cai de
  // tamanho para nao quebrar linha dentro do card.
  const hasValue = hours !== null && hours > 0
  return (
    <section className="rounded-md border border-border bg-card p-[14px_16px]">
      <div className="text-xs text-muted-foreground">Tempo médio de resolução</div>
      <div
        className={cn(
          "mt-1.5 text-accent-foreground",
          hasValue ? "font-mono text-3xl font-semibold" : "text-sm font-medium",
        )}
      >
        {formatAvgResolutionHours(hours)}
      </div>
      {caption && <div className="mt-0.5 text-[11.5px] text-muted-foreground">{caption}</div>}
    </section>
  )
}
