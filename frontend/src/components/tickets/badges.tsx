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

// Mesma familia de cor do token --status-* de cada estado (ver lib/tickets), so
// que como tinta de badge: fundo quase da cor da superficie, texto no extremo
// oposto e anel um passo adiante do fundo. O tema escuro inverte a escala em vez
// de reaproveitar as tintas claras — sem isso, nove manchas claras (bg-*-50)
// acendiam sobre o card escuro da fila. "Cancelado" e o unico neutro e sai nos
// tokens do tema, que ja tem valor para os dois temas.
const STATUS_BADGE: Record<TicketStatus, string> = {
  aberto: "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-950 dark:text-sky-200 dark:ring-sky-800",
  aguardando_cliente:
    "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-800",
  aguardando_analise:
    "bg-violet-50 text-violet-800 ring-violet-200 dark:bg-violet-950 dark:text-violet-200 dark:ring-violet-800",
  aprovado:
    "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-200 dark:ring-emerald-800",
  aguardando_envio_reverso:
    "bg-indigo-50 text-indigo-800 ring-indigo-200 dark:bg-indigo-950 dark:text-indigo-200 dark:ring-indigo-800",
  produto_recebido:
    "bg-teal-50 text-teal-800 ring-teal-200 dark:bg-teal-950 dark:text-teal-200 dark:ring-teal-800",
  finalizado:
    "bg-emerald-50 text-emerald-900 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:ring-emerald-800",
  declinado:
    "bg-rose-50 text-rose-800 ring-rose-200 dark:bg-rose-950 dark:text-rose-200 dark:ring-rose-800",
  cancelado: "bg-muted text-muted-foreground ring-border",
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
  // token, e nao zinc-400: o cinza neutro da paleta e quente (identidade
  // visual), e assim o ponto acompanha os dois temas sem variante
  baixa: "bg-muted-foreground",
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
  return diffMs >= 0 ? `em ${spec}` : `há ${spec}`
}

function slaTitle(sla: SlaState, dueAt: string): string {
  if (sla === "encerrado") return SLA_LABELS.encerrado
  const verb = sla === "atrasado" ? "venceu" : "vence"
  return `${SLA_LABELS[sla]} — ${verb} ${relativeDue(dueAt)}`
}

const SLA_STYLES: Record<Exclude<SlaState, "encerrado">, string> = {
  no_prazo: "text-muted-foreground",
  // amber-700 tem 4,90:1 sobre o card claro e so 2,77:1 sobre o escuro; no
  // escuro o aviso sobe para amber-500 (6,52:1)
  vence_em_breve: "text-amber-700 dark:text-amber-500 motion-safe:animate-pulse",
  // --primary-text e nao --primary: como TEXTO o Paprika da 3,32:1 no claro e
  // 4,09:1 no escuro, os dois abaixo de AA (ver index.css)
  atrasado: "text-primary-text font-semibold motion-safe:animate-pulse",
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
