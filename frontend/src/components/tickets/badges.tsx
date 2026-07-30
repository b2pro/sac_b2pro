import { slaRemaining } from "@/lib/format"
import { cn } from "@/lib/utils"
import {
  PRIORITY_LABELS,
  SLA_LABELS,
  STATUS_LABELS,
  type SlaState,
  type TicketPriority,
  type TicketStatus,
} from "@/lib/tickets"

export const STATUS_ACCENTS: Record<TicketStatus, string> = {
  aberto: "border-l-sky-600",
  aguardando_cliente: "border-l-amber-500",
  aguardando_analise: "border-l-violet-500",
  aprovado: "border-l-emerald-600",
  aguardando_envio_reverso: "border-l-indigo-500",
  produto_recebido: "border-l-teal-600",
  finalizado: "border-l-emerald-700",
  declinado: "border-l-rose-600",
  cancelado: "border-l-zinc-400",
}

const STATUS_BADGE: Record<TicketStatus, string> = {
  aberto: "bg-sky-50 text-sky-800 ring-sky-200",
  aguardando_cliente: "bg-amber-50 text-amber-800 ring-amber-200",
  aguardando_analise: "bg-violet-50 text-violet-800 ring-violet-200",
  aprovado: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  aguardando_envio_reverso: "bg-indigo-50 text-indigo-800 ring-indigo-200",
  produto_recebido: "bg-teal-50 text-teal-800 ring-teal-200",
  finalizado: "bg-emerald-50 text-emerald-900 ring-emerald-200",
  declinado: "bg-rose-50 text-rose-800 ring-rose-200",
  cancelado: "bg-zinc-100 text-zinc-600 ring-zinc-200",
}

export function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        STATUS_BADGE[status],
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}

const PRIORITY_DOTS: Record<TicketPriority, string> = {
  baixa: "bg-zinc-400",
  media: "bg-sky-500",
  alta: "bg-amber-500",
  urgente: "bg-primary",
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={cn("size-2 rounded-full", PRIORITY_DOTS[priority])} />
      {PRIORITY_LABELS[priority]}
    </span>
  )
}

function relativeDue(dueAt: string): string {
  const diffMs = new Date(dueAt).getTime() - Date.now()
  const hours = Math.round(Math.abs(diffMs) / 3_600_000)
  const spec = hours >= 48 ? `${Math.round(hours / 24)}d` : `${hours}h`
  return diffMs >= 0 ? `em ${spec}` : `ha ${spec}`
}

function slaTitle(sla: SlaState, dueAt: string): string {
  if (sla === "encerrado") return SLA_LABELS.encerrado
  const verb = sla === "atrasado" ? "venceu" : "vence"
  return `${SLA_LABELS[sla]} — ${verb} ${relativeDue(dueAt)}`
}

const SLA_STYLES: Record<Exclude<SlaState, "encerrado">, string> = {
  no_prazo: "text-muted-foreground",
  vence_em_breve: "text-amber-700 motion-safe:animate-pulse",
  atrasado: "text-primary font-semibold motion-safe:animate-pulse",
}

export function SlaBadge({ sla, dueAt }: { sla: SlaState; dueAt: string }) {
  if (sla === "encerrado") {
    return (
      <span className="text-xs text-muted-foreground" title={SLA_LABELS.encerrado}>
        —
      </span>
    )
  }
  return (
    <span
      className={cn("font-mono text-xs", SLA_STYLES[sla])}
      title={slaTitle(sla, dueAt)}
    >
      {slaRemaining(dueAt)}
    </span>
  )
}
