import { Link } from "react-router-dom"

import { PriorityBadge, SlaBadge, StatusBadge } from "@/components/tickets/badges"
import { formatShortDate, formatShortDateTime } from "@/lib/format"
import { STATUS_ACCENT_VARS, type TicketListItem } from "@/lib/tickets"
import { cn } from "@/lib/utils"

export function TicketQueueCard({ item }: { item: TicketListItem }) {
  const openedDate = formatShortDate(item.opened_at)
  const lastActivity = formatShortDateTime(item.last_activity_at)

  return (
    <Link
      to={`/tickets/${item.id}`}
      // A cor da trilha vai em estilo inline (e nao em classe) porque assim ela
      // sobrevive ao hover: `hover:border-foreground` precisa mudar as outras
      // tres bordas e, como classe, venceria a lateral colorida por
      // especificidade. Estilo inline vence os dois.
      style={{ borderLeftColor: STATUS_ACCENT_VARS[item.status] }}
      className="block rounded-md border border-border border-l-[3px] bg-card px-4 py-3 hover:border-foreground"
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <span
          className={cn("size-2 shrink-0 rounded-full", item.unread ? "bg-primary" : "bg-transparent")}
          role={item.unread ? "img" : undefined}
          title={item.unread ? "Atividade nao lida" : undefined}
          aria-label={item.unread ? "Atividade nao lida" : undefined}
        />
        <span className="font-mono text-[13.5px] font-semibold whitespace-nowrap text-primary-text">
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
