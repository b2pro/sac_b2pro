import type { KeyboardEvent } from "react"
import { useNavigate } from "react-router-dom"

import { PriorityBadge, SlaBadge, StatusBadge, STATUS_ACCENTS } from "@/components/tickets/badges"
import { cn } from "@/lib/utils"
import type { TicketListItem } from "@/lib/tickets"

function formatLastActivity(iso: string): string {
  const date = new Date(iso)
  const dd = String(date.getDate()).padStart(2, "0")
  const mm = String(date.getMonth() + 1).padStart(2, "0")
  const hh = String(date.getHours()).padStart(2, "0")
  const min = String(date.getMinutes()).padStart(2, "0")
  return `${dd}/${mm} ${hh}:${min}`
}

export function TicketRow({
  item,
  showPriorityAndAttendant = false,
}: {
  item: TicketListItem
  showPriorityAndAttendant?: boolean
}) {
  const navigate = useNavigate()

  function open() {
    navigate(`/tickets/${item.id}`)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTableRowElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      open()
    }
  }

  return (
    <tr
      role="link"
      tabIndex={0}
      title="Abrir detalhe do ticket"
      onClick={open}
      onKeyDown={onKeyDown}
      className={cn(
        "cursor-pointer border-b border-border/60 border-l-[3px] outline-none hover:bg-muted focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
        STATUS_ACCENTS[item.status],
      )}
    >
      <td className="whitespace-nowrap px-2.5 py-2 pl-3.5 font-mono font-semibold text-primary">
        #{item.number}
      </td>
      <td className="whitespace-nowrap px-2.5 py-2">{item.customer_name ?? "-"}</td>
      <td className="max-w-[220px] truncate px-2.5 py-2" title={item.first_product_name ?? "-"}>
        {item.first_product_name ?? "-"}
      </td>
      <td className="px-2.5 py-2">
        <StatusBadge status={item.status} />
      </td>
      {showPriorityAndAttendant && (
        <td className="px-2.5 py-2">
          <PriorityBadge priority={item.priority} />
        </td>
      )}
      <td className="px-2.5 py-2">
        <SlaBadge sla={item.sla} dueAt={item.due_at} />
      </td>
      {showPriorityAndAttendant && (
        <td className="whitespace-nowrap px-2.5 py-2 text-muted-foreground">
          {item.attendant_name ?? "-"}
        </td>
      )}
      <td className="whitespace-nowrap px-2.5 py-2 pr-4 text-right font-mono text-xs text-muted-foreground">
        {formatLastActivity(item.last_activity_at)}
      </td>
    </tr>
  )
}
