import type { TicketStatus } from "@/lib/tickets"

// Mesmas familias semanticas de STATUS_ACCENTS (components/tickets/badges.tsx),
// via CSS vars do Tailwind para nao hardcodar hex.
export const STATUS_CHART_FILL: Record<TicketStatus, string> = {
  aberto: "var(--color-sky-600)",
  aguardando_cliente: "var(--color-amber-500)",
  aguardando_analise: "var(--color-violet-500)",
  aprovado: "var(--color-emerald-600)",
  aguardando_envio_reverso: "var(--color-indigo-500)",
  produto_recebido: "var(--color-teal-600)",
  finalizado: "var(--color-emerald-700)",
  declinado: "var(--color-rose-600)",
  cancelado: "var(--color-zinc-400)",
}
