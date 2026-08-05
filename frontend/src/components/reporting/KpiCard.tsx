import { ArrowUpRight } from "lucide-react"
import { Link } from "react-router-dom"

import { cn } from "@/lib/utils"

export function KpiCard({
  label,
  value,
  to,
  accent,
  caption,
  title,
  mono = true,
}: {
  label: string
  value: number | string
  to?: string
  accent?: boolean
  caption?: string
  title?: string
  // false quando `value` e uma frase (ex.: "Sem tickets finalizados") em vez
  // de numero/codigo: mono e reservado a dado numerico pela identidade visual.
  mono?: boolean
}) {
  const content = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs leading-tight text-muted-foreground">{label}</span>
        {to && (
          <ArrowUpRight
            size={14}
            strokeWidth={1.5}
            className="mt-px shrink-0 text-muted-foreground/70"
            aria-hidden
          />
        )}
      </div>
      <div
        className={cn(
          "mt-1.5 font-semibold",
          mono ? "font-mono text-[26px]" : "text-base",
          accent ? "text-primary-text" : "text-accent-foreground",
        )}
      >
        {value}
      </div>
      {caption && <div className="mt-0.5 text-[11px] text-muted-foreground">{caption}</div>}
    </>
  )

  const shellClass = "min-w-0 rounded-md border border-border bg-card p-[14px_16px]"

  if (to) {
    return (
      <Link
        to={to}
        title={title}
        className={cn(
          shellClass,
          "block text-foreground outline-none hover:border-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
        )}
      >
        {content}
      </Link>
    )
  }

  return (
    <div className={shellClass} title={title}>
      {content}
    </div>
  )
}
