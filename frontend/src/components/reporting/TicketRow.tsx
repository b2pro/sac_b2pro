import type { KeyboardEvent, MouseEvent } from "react"
import { Link, useNavigate } from "react-router-dom"

import { PriorityBadge, SlaBadge, StatusBadge } from "@/components/tickets/badges"
import { formatShortDateTime } from "@/lib/format"
import { STATUS_ACCENT_VARS, type TicketListItem } from "@/lib/tickets"

export function TicketRow({
  item,
  showPriorityAndAttendant = false,
}: {
  item: TicketListItem
  showPriorityAndAttendant?: boolean
}) {
  const navigate = useNavigate()
  const to = `/tickets/${item.id}`

  // Mouse: clicar em qualquer lugar da linha navega. So nao intercepta
  // cliques que ja caem sobre o link (ou outro elemento interativo dentro
  // da linha), senao a navegacao dispara duas vezes.
  function onRowClick(event: MouseEvent<HTMLTableRowElement>) {
    if ((event.target as HTMLElement).closest("a, button, input, select, textarea")) {
      return
    }
    navigate(to)
  }

  // Teclado: o link nativo ja responde a Enter. Espaco nao ativa links por
  // padrao no navegador, entao tratamos aqui para preservar o atalho.
  function onLinkKeyDown(event: KeyboardEvent<HTMLAnchorElement>) {
    if (event.key === " ") {
      event.preventDefault()
      navigate(to)
    }
  }

  return (
    <tr
      title="Abrir detalhe do ticket"
      onClick={onRowClick}
      style={{ borderLeftColor: STATUS_ACCENT_VARS[item.status] }}
      className="cursor-pointer border-b border-border/60 border-l-[3px] hover:bg-muted has-[:focus-visible]:border-ring has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50"
    >
      <td>
        <Link
          to={to}
          onKeyDown={onLinkKeyDown}
          aria-label={`Abrir ticket numero ${item.number}`}
          className="block whitespace-nowrap px-2.5 py-2 pl-3.5 font-mono font-semibold text-primary-text outline-none"
        >
          #{item.number}
        </Link>
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
        {formatShortDateTime(item.last_activity_at)}
      </td>
    </tr>
  )
}
