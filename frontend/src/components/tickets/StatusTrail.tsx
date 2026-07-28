import { cn } from "@/lib/utils"
import {
  MAIN_FLOW,
  STATUS_LABELS,
  type SlaState,
  type TicketStatus,
} from "@/lib/tickets"

export function StatusTrail({ status, sla }: { status: TicketStatus; sla: SlaState }) {
  const lateral = !MAIN_FLOW.includes(status)
  const effective: TicketStatus = lateral
    ? status === "aguardando_cliente"
      ? "aberto"
      : "aguardando_analise"
    : status
  const currentIndex = MAIN_FLOW.indexOf(effective)
  const atRisk = sla === "vence_em_breve" || sla === "atrasado"
  return (
    <div>
      <div className="flex gap-1" role="img" aria-label={`Status: ${STATUS_LABELS[status]}`}>
        {MAIN_FLOW.map((step, index) => (
          <div
            key={step}
            className={cn(
              "h-1.5 flex-1 rounded-sm bg-border/40",
              index < currentIndex && "bg-foreground",
              index === currentIndex &&
                (atRisk && !lateral ? "animate-pulse bg-primary" : "bg-foreground"),
            )}
          />
        ))}
      </div>
      <div className="mt-1.5 flex items-center justify-between text-xs text-foreground/70">
        <span>{STATUS_LABELS[status]}</span>
        {lateral && status !== "aguardando_cliente" ? (
          <span className="font-medium text-rose-700">{STATUS_LABELS[status]}</span>
        ) : null}
      </div>
    </div>
  )
}
