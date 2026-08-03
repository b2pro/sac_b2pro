import { Link } from "react-router-dom"

import { PriorityBadge, SlaBadge, StatusBadge, STATUS_ACCENTS } from "@/components/tickets/badges"
import { formatShortDate, formatShortDateTime } from "@/lib/format"
import type { TicketListItem, TicketStatus } from "@/lib/tickets"
import { cn } from "@/lib/utils"

// Mesma cor de STATUS_ACCENTS, so que reafirmada no hover: sem isso,
// hover:border-foreground (que precisa mudar as outras tres bordas para
// Charcoal Brown) tambem achata a lateral colorida, porque a variante :hover
// tem mais especificidade CSS que a classe base sempre ativa. As classes
// ficam escritas por extenso (nao geradas por template string) porque o
// scanner do Tailwind so enxerga literais de classe no codigo-fonte. Fica
// local ao componente (nao exportada) para nao criar mais um export de
// nao-componente em badges.tsx.
const STATUS_ACCENTS_HOVER: Record<TicketStatus, string> = {
  aberto: "hover:border-l-sky-600",
  aguardando_cliente: "hover:border-l-amber-500",
  aguardando_analise: "hover:border-l-violet-500",
  aprovado: "hover:border-l-emerald-600",
  aguardando_envio_reverso: "hover:border-l-indigo-500",
  produto_recebido: "hover:border-l-teal-600",
  finalizado: "hover:border-l-emerald-700",
  declinado: "hover:border-l-rose-600",
  cancelado: "hover:border-l-zinc-400",
}

export function TicketQueueCard({ item }: { item: TicketListItem }) {
  const openedDate = formatShortDate(item.opened_at)
  const lastActivity = formatShortDateTime(item.last_activity_at)

  return (
    <Link
      to={`/tickets/${item.id}`}
      className={cn(
        "block rounded-md border border-border border-l-[3px] bg-card px-4 py-3 hover:border-foreground",
        STATUS_ACCENTS[item.status],
        STATUS_ACCENTS_HOVER[item.status],
      )}
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <span
          className={cn("size-2 shrink-0 rounded-full", item.unread ? "bg-primary" : "bg-transparent")}
          role={item.unread ? "img" : undefined}
          title={item.unread ? "Atividade nao lida" : undefined}
          aria-label={item.unread ? "Atividade nao lida" : undefined}
        />
        <span className="font-mono text-[13.5px] font-semibold whitespace-nowrap text-primary">
          #{item.number}
        </span>
        <span
          className={cn(
            "whitespace-nowrap text-[13.5px] font-semibold",
            item.customer_name ? "text-accent-foreground" : "text-muted-foreground",
          )}
        >
          {item.customer_name ?? "Cliente nao informado"}
        </span>
        <StatusBadge status={item.status} />
        <PriorityBadge priority={item.priority} />
        <span className="ml-auto">
          <SlaBadge sla={item.sla} dueAt={item.due_at} />
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-2.5 text-[12.5px] text-muted-foreground">
        <span className="max-w-[340px] truncate" title={item.first_product_name ?? "Sem itens"}>
          {item.first_product_name ?? "Sem itens"}
        </span>
        <span>·</span>
        <span className="whitespace-nowrap">
          {item.items_count === 1 ? "1 item" : `${item.items_count} itens`}
        </span>
        <span>·</span>
        <span className="whitespace-nowrap">{item.attendant_name ?? "-"}</span>
        <span className="ml-auto font-mono text-[11.5px] whitespace-nowrap">
          aberto {openedDate} · atividade {lastActivity}
        </span>
      </div>
    </Link>
  )
}
