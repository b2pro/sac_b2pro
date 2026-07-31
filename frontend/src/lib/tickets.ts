import { api } from "@/lib/api"
import type { Customer, CustomerInput, Page } from "@/lib/cadastros"

export type TicketStatus =
  | "aberto"
  | "aguardando_cliente"
  | "aguardando_analise"
  | "aprovado"
  | "aguardando_envio_reverso"
  | "produto_recebido"
  | "finalizado"
  | "declinado"
  | "cancelado"

export type TicketPriority = "baixa" | "media" | "alta" | "urgente"
export type SlaState = "no_prazo" | "vence_em_breve" | "atrasado" | "encerrado"

export const STATUS_LABELS: Record<TicketStatus, string> = {
  aberto: "Aberto",
  aguardando_cliente: "Aguardando cliente",
  aguardando_analise: "Aguardando analise",
  aprovado: "Aprovado",
  aguardando_envio_reverso: "Aguardando envio reverso",
  produto_recebido: "Produto recebido",
  finalizado: "Finalizado",
  declinado: "Declinado",
  cancelado: "Cancelado",
}

export const PRIORITY_LABELS: Record<TicketPriority, string> = {
  baixa: "Baixa",
  media: "Media",
  alta: "Alta",
  urgente: "Urgente",
}

export const SLA_LABELS: Record<SlaState, string> = {
  no_prazo: "No prazo",
  vence_em_breve: "Vence em breve",
  atrasado: "Atrasado",
  encerrado: "Encerrado",
}

export const MAIN_FLOW: TicketStatus[] = [
  "aberto",
  "aguardando_analise",
  "aprovado",
  "aguardando_envio_reverso",
  "produto_recebido",
  "finalizado",
]

const CLOSED: TicketStatus[] = ["finalizado", "declinado", "cancelado"]

export const isClosed = (status: TicketStatus) => CLOSED.includes(status)

export type Ticket = {
  id: string
  number: number
  status: TicketStatus
  priority: TicketPriority
  sla: SlaState
  brand_id: string
  customer_id: string | null
  attendant_user_id: string
  supervisor_user_id: string | null
  purchase_channel_id: string | null
  order_code: string | null
  purchase_date: string | null
  delivery_date: string | null
  description: string | null
  decision_notes: string | null
  final_notes: string | null
  solution_type_id: string | null
  warranty_order_code: string | null
  warranty_tracking_code: string | null
  opened_at: string
  submitted_at: string | null
  approved_at: string | null
  declined_at: string | null
  closed_at: string | null
  last_activity_at: string
  due_at: string
}

export type TicketListItem = {
  id: string
  number: number
  status: TicketStatus
  priority: TicketPriority
  sla: SlaState
  due_at: string
  customer_name: string | null
  first_product_name: string | null
  items_count: number
  attendant_name: string | null
  opened_at: string
  last_activity_at: string
  unread: boolean
}

export type TicketItemView = {
  id: string
  product_id: string
  product_name: string
  defect_type_id: string
  defect_type_name: string
  quantity: number
}

export type TicketComment = {
  id: string
  author_user_id: string
  author_name: string | null
  body: string
  reply_to_id: string | null
  created_at: string | null
}

export type TimelineEvent = {
  id: string
  type: string
  title: string
  old_value: string | null
  new_value: string | null
  author_user_id: string | null
  author_name: string | null
  created_at: string | null
}

export type ReverseCode = {
  id: string
  code: string
  author_user_id: string | null
  author_name: string | null
  created_at: string | null
}

export type TicketDetail = {
  ticket: Ticket
  customer: Customer | null
  attendant_name: string | null
  supervisor_name: string | null
  items: TicketItemView[]
  comments: TicketComment[]
  timeline: TimelineEvent[]
  reverses: ReverseCode[]
}

export type TicketItemInput = {
  product_id: string
  defect_type_id: string
  quantity: number
}

export type TicketCreateInput = {
  brand_id: string
  priority: TicketPriority
  customer?: CustomerInput | null
  customer_id?: string | null
  supervisor_user_id?: string | null
  purchase_channel_id?: string | null
  order_code?: string | null
  purchase_date?: string | null
  delivery_date?: string | null
  description?: string | null
  items?: TicketItemInput[]
}

export type TicketUpdateInput = Omit<TicketCreateInput, "customer" | "items">

export type ListTicketsParams = {
  status?: TicketStatus
  brandId?: string
  customer?: string
  customerId?: string
  productId?: string
  orderCode?: string
  priority?: TicketPriority
  overdue?: boolean
  q?: string
  atendenteId?: string
  unread?: boolean
  page?: number
  perPage?: number
  sort?: string
  order?: "asc" | "desc"
}

export type TicketCounters = {
  todos: number
  ativos: number
  abertos: number
  aguardando_analise: number
  atrasados: number
  nao_lidos: number
  meus: number
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== false) search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ""
}

export const listTickets = (params: ListTicketsParams = {}) =>
  api<Page<TicketListItem>>(
    `/tickets${query({
      status: params.status,
      brand_id: params.brandId,
      customer: params.customer,
      customer_id: params.customerId,
      product_id: params.productId,
      order_code: params.orderCode,
      priority: params.priority,
      overdue: params.overdue,
      q: params.q,
      atendente_id: params.atendenteId,
      unread: params.unread,
      page: params.page,
      per_page: params.perPage,
      sort: params.sort,
      order: params.order,
    })}`,
  )

export const getTicket = (id: string) => api<TicketDetail>(`/tickets/${id}`)

export const getTicketCounters = () => api<TicketCounters>("/tickets/contadores")

export const createTicket = (input: TicketCreateInput) =>
  api<Ticket>("/tickets", { method: "POST", body: input })

export const updateTicket = (id: string, input: TicketUpdateInput) =>
  api<Ticket>(`/tickets/${id}`, { method: "PUT", body: input })

export const addTicketItem = (ticketId: string, input: TicketItemInput) =>
  api<TicketItemView>(`/tickets/${ticketId}/itens`, { method: "POST", body: input })

export const updateTicketItem = (ticketId: string, itemId: string, input: TicketItemInput) =>
  api<TicketItemView>(`/tickets/${ticketId}/itens/${itemId}`, { method: "PUT", body: input })

export const removeTicketItem = (ticketId: string, itemId: string) =>
  api<void>(`/tickets/${ticketId}/itens/${itemId}`, { method: "DELETE" })

export const submitTicket = (id: string) =>
  api<Ticket>(`/tickets/${id}/enviar-analise`, { method: "POST" })

export const approveTicket = (id: string, notes?: string) =>
  api<Ticket>(`/tickets/${id}/aprovar`, { method: "POST", body: { notes: notes ?? null } })

export const declineTicket = (id: string, reason: string) =>
  api<Ticket>(`/tickets/${id}/declinar`, { method: "POST", body: { reason } })

export const cancelTicket = (id: string, reason?: string) =>
  api<Ticket>(`/tickets/${id}/cancelar`, { method: "POST", body: { reason: reason ?? null } })

export const holdTicket = (id: string) =>
  api<Ticket>(`/tickets/${id}/aguardar-cliente`, { method: "POST" })

export const resumeTicket = (id: string) =>
  api<Ticket>(`/tickets/${id}/retomar`, { method: "POST" })

export const reopenTicket = (id: string) =>
  api<Ticket>(`/tickets/${id}/reabrir`, { method: "POST" })

export const receiveProduct = (id: string) =>
  api<Ticket>(`/tickets/${id}/produto-recebido`, { method: "POST" })

export const finalizeTicket = (id: string, solutionTypeId: string, notes?: string) =>
  api<Ticket>(`/tickets/${id}/finalizar`, {
    method: "POST",
    body: { solution_type_id: solutionTypeId, notes: notes ?? null },
  })

export const registerReverse = (id: string, code: string) =>
  api<ReverseCode>(`/tickets/${id}/reversos`, { method: "POST", body: { code } })

export const deleteReverse = (id: string, reverseId: string) =>
  api<void>(`/tickets/${id}/reversos/${reverseId}`, { method: "DELETE" })

export const setWarranty = (id: string, orderCode: string, trackingCode?: string) =>
  api<Ticket>(`/tickets/${id}/garantia`, {
    method: "PUT",
    body: { order_code: orderCode, tracking_code: trackingCode ?? null },
  })

export const addComment = (id: string, body: string, replyToId?: string) =>
  api<TicketComment>(`/tickets/${id}/comentarios`, {
    method: "POST",
    body: { body, reply_to_id: replyToId ?? null },
  })

export const markUnread = (id: string) =>
  api<void>(`/tickets/${id}/nao-lido`, { method: "POST" })

export const canCreateTicket = (role: string | null) =>
  role !== null && role !== "visualizador"

export const canDecide = (role: string | null) => role === "admin" || role === "supervisor"

export const canOperate = (role: string | null, isOwner: boolean) =>
  role === "admin" || role === "supervisor" || (role === "atendente" && isOwner)

export const canEditTicket = (
  role: string | null,
  isOwner: boolean,
  status: TicketStatus,
) => {
  if (status !== "aberto" && status !== "aguardando_cliente") return false
  if (role === "admin" || role === "supervisor") return true
  return role === "atendente" && isOwner
}

export const canComment = (role: string | null) =>
  role !== null && role !== "visualizador"

export type TicketAction =
  | "enviar_analise"
  | "aprovar"
  | "declinar"
  | "cancelar"
  | "aguardar_cliente"
  | "retomar"
  | "registrar_reverso"
  | "produto_recebido"
  | "finalizar"
  | "reabrir"

export type PrimaryAction = { action: TicketAction; label: string } | null

export function primaryActionFor(
  ticket: Pick<Ticket, "status" | "attendant_user_id">,
  role: string | null,
  userId: string | undefined,
): PrimaryAction {
  const owner = ticket.attendant_user_id === userId
  switch (ticket.status) {
    case "aberto":
      return canEditTicket(role, owner, ticket.status) || canOperate(role, owner)
        ? { action: "enviar_analise", label: "Enviar para analise" }
        : null
    case "aguardando_cliente":
      return canEditTicket(role, owner, ticket.status)
        ? { action: "retomar", label: "Retomar atendimento" }
        : null
    case "aguardando_analise":
      return canDecide(role) ? { action: "aprovar", label: "Aprovar" } : null
    case "aprovado":
      return canOperate(role, owner)
        ? { action: "registrar_reverso", label: "Registrar reverso" }
        : null
    case "aguardando_envio_reverso":
      return canOperate(role, owner)
        ? { action: "produto_recebido", label: "Produto recebido" }
        : null
    case "produto_recebido":
      return canOperate(role, owner) ? { action: "finalizar", label: "Finalizar" } : null
    case "finalizado":
    case "declinado":
    case "cancelado":
      return canDecide(role) ? { action: "reabrir", label: "Reabrir" } : null
  }
}
