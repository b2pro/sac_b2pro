import { Link } from "react-router-dom"

import { PriorityBadge, SlaBadge, StatusBadge, STATUS_ACCENTS } from "@/components/tickets/badges"
import { formatShortDateTime } from "@/lib/format"
import type { TicketListItem } from "@/lib/tickets"
import { cn } from "@/lib/utils"

export function TicketQueueCard({ item }: { item: TicketListItem }) {
  const openedDate = formatShortDateTime(item.opened_at).split(" ")[0]
  const lastActivity = formatShortDateTime(item.last_activity_at)

  return (
    <Link
      to={`/tickets/${item.id}`}
      className={cn(
        "block rounded-md border border-border border-l-[3px] bg-card px-4 py-3 hover:border-foreground",
        STATUS_ACCENTS[item.status],
      )}
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <span
          className={cn("size-2 shrink-0 rounded-full", item.unread ? "bg-primary" : "bg-transparent")}
          title={item.unread ? "Atividade nao lida" : undefined}
          aria-label={item.unread ? "Atividade nao lida" : undefined}
        />
        <span className="font-mono text-[13.5px] font-semibold text-primary">#{item.number}</span>
        <span
          className={cn(
            "text-[13.5px] font-semibold",
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
        <span>{item.items_count === 1 ? "1 item" : `${item.items_count} itens`}</span>
        <span>·</span>
        <span>{item.attendant_name ?? "-"}</span>
        <span className="ml-auto font-mono text-[11.5px]">
          aberto {openedDate} · atividade {lastActivity}
        </span>
      </div>
    </Link>
  )
}
