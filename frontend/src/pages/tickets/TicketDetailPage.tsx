import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Reply, X } from "lucide-react"
import { useState, type FormEvent, type KeyboardEvent } from "react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { ActionPanel, ReversesCard } from "@/components/tickets/ActionPanel"
import { AttachmentsCard } from "@/components/tickets/AttachmentsCard"
import { PriorityBadge, SlaBadge, StatusBadge } from "@/components/tickets/badges"
import { ItemsCard } from "@/components/tickets/ItemsCard"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { listCatalog } from "@/lib/cadastros"
import { formatDocument, formatPhone } from "@/lib/format"
import {
  addComment,
  canComment,
  getTicket,
  isClosed,
  STATUS_LABELS,
  type TicketComment,
  type TicketStatus,
} from "@/lib/tickets"
import { cn } from "@/lib/utils"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

function formatDateOnly(value: string | null): string {
  if (!value) return "-"
  const [year, month, day] = value.slice(0, 10).split("-")
  return `${day}/${month}/${year}`
}

function formatDateTime(value: string | null): string {
  return value
    ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })
    : "-"
}

function statusOrRaw(value: string | null): string {
  if (!value) return ""
  return value in STATUS_LABELS ? STATUS_LABELS[value as TicketStatus] : value
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max)}...` : value
}

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const [commentBody, setCommentBody] = useState("")
  const [replyTo, setReplyTo] = useState<TicketComment | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["ticket", id],
    queryFn: () => getTicket(id!),
    enabled: Boolean(id),
  })

  const { data: brands } = useQuery({
    queryKey: ["marcas"],
    queryFn: () => listCatalog("marcas"),
  })

  const { data: channels } = useQuery({
    queryKey: ["canais"],
    queryFn: () => listCatalog("canais"),
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["ticket", id] })
    void queryClient.invalidateQueries({ queryKey: ["tickets"] })
  }

  const commentMutation = useMutation({
    mutationFn: (input: { body: string; replyToId?: string }) =>
      addComment(id!, input.body, input.replyToId),
    onSuccess: () => {
      setCommentBody("")
      setReplyTo(null)
      invalidate()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-20 animate-pulse rounded-md bg-muted" />
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-32 animate-pulse rounded-md bg-muted" />
            ))}
          </div>
          <div className="space-y-6">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-32 animate-pulse rounded-md bg-muted" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (!data) {
    return <p className="text-sm text-muted-foreground">Ticket nao encontrado.</p>
  }

  const { ticket, customer, attendant_name, supervisor_name, comments, timeline } = data

  const commentsById = new Map(comments.map((c) => [c.id, c]))
  const sortedTimeline = [...timeline].sort((a, b) => {
    const dateA = a.created_at ? new Date(a.created_at).getTime() : 0
    const dateB = b.created_at ? new Date(b.created_at).getTime() : 0
    return dateB - dateA
  })
  const brandName = brands?.find((b) => b.id === ticket.brand_id)?.name
  const channelName = channels?.find((c) => c.id === ticket.purchase_channel_id)?.name
  const closed = isClosed(ticket.status)
  const role = session?.role ?? null
  const isOwner = ticket.attendant_user_id === session?.user.id
  const commentsAllowed = canComment(role)
  const readOnlyReason = closed
    ? "Ticket encerrado — chat somente leitura."
    : !commentsAllowed
      ? "Somente leitura."
      : null

  function onSubmitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = commentBody.trim()
    if (!body) return
    commentMutation.mutate({ body, replyToId: replyTo?.id })
  }

  function onTextareaKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          to="/tickets"
          className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={16} strokeWidth={1.5} />
          Voltar para tickets
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-2xl font-semibold text-primary">#{ticket.number}</h1>
          <StatusBadge status={ticket.status} />
          <PriorityBadge priority={ticket.priority} />
          <SlaBadge sla={ticket.sla} dueAt={ticket.due_at} />
        </div>
        <p className="text-sm text-muted-foreground">
          {brandName ?? "Marca nao identificada"} · Aberto em {formatDateTime(ticket.opened_at)}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Informacoes gerais</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <div>
                  <dt className="text-muted-foreground">Atendente</dt>
                  <dd className="text-foreground">{attendant_name ?? "-"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Supervisor</dt>
                  <dd className="text-foreground">{supervisor_name ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Prioridade</dt>
                  <dd>
                    <PriorityBadge priority={ticket.priority} />
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Abertura</dt>
                  <dd className="text-foreground">{formatDateTime(ticket.opened_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Prazo SLA</dt>
                  <dd className="font-mono text-foreground">{formatDateTime(ticket.due_at)}</dd>
                </div>
              </dl>
              <div className="border-t border-border pt-4">
                <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                  Descricao
                </p>
                <p className="mt-1 text-sm whitespace-pre-wrap text-foreground">
                  {ticket.description || "-"}
                </p>
              </div>
              {ticket.decision_notes && (
                <div className="border-t border-border pt-4">
                  <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Notas de decisao
                  </p>
                  <p className="mt-1 text-sm whitespace-pre-wrap text-foreground">
                    {ticket.decision_notes}
                  </p>
                </div>
              )}
              {ticket.final_notes && (
                <div className="border-t border-border pt-4">
                  <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Notas finais
                  </p>
                  <p className="mt-1 text-sm whitespace-pre-wrap text-foreground">
                    {ticket.final_notes}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Cliente</CardTitle>
            </CardHeader>
            <CardContent>
              {customer ? (
                <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                  <div className="col-span-2">
                    <dt className="text-muted-foreground">Nome</dt>
                    <dd className="text-foreground">{customer.name}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Documento</dt>
                    <dd className="font-mono text-foreground">
                      {formatDocument(customer.document)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Telefone</dt>
                    <dd className="font-mono text-foreground">
                      {customer.phone ? formatPhone(customer.phone) : "-"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Email</dt>
                    <dd className="text-foreground">{customer.email ?? "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Cidade/UF</dt>
                    <dd className="text-foreground">
                      {customer.city && customer.state
                        ? `${customer.city}/${customer.state}`
                        : (customer.city ?? customer.state ?? "-")}
                    </dd>
                  </div>
                  <div className="col-span-2">
                    <Link
                      to={`/tickets?customer_id=${customer.id}`}
                      className="text-sm text-primary hover:underline"
                    >
                      Ver historico
                    </Link>
                  </div>
                </dl>
              ) : (
                <p className="text-sm text-muted-foreground">Nenhum cliente vinculado.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Compra</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <div>
                  <dt className="text-muted-foreground">Canal</dt>
                  <dd className="text-foreground">{channelName ?? "-"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Pedido</dt>
                  <dd className="font-mono text-foreground">{ticket.order_code ?? "-"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Data da compra</dt>
                  <dd className="text-foreground">{formatDateOnly(ticket.purchase_date)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Data de entrega</dt>
                  <dd className="text-foreground">{formatDateOnly(ticket.delivery_date)}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <ItemsCard detail={data} role={role} isOwner={isOwner} onChanged={invalidate} />

          <AttachmentsCard ticketId={ticket.id} status={ticket.status} onChanged={invalidate} />

          <Card>
            <CardHeader>
              <CardTitle>Comentarios internos</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {comments.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum comentario ainda.</p>
              ) : (
                <div className="flex flex-col gap-4">
                  {comments.map((comment) => {
                    const mine = comment.author_user_id === session?.user.id
                    const repliedTo = comment.reply_to_id
                      ? commentsById.get(comment.reply_to_id)
                      : undefined
                    return (
                      <div
                        key={comment.id}
                        className={cn("flex flex-col gap-1", mine ? "items-end" : "items-start")}
                      >
                        <div
                          className={cn(
                            "max-w-[80%] rounded-md border px-3 py-2 text-sm",
                            mine
                              // no escuro a mesma tinta a 5% desaparece sobre o
                              // card: a bolha propria precisa de mais Paprika
                              // para continuar distinguivel da do colega
                              ? "border-primary/30 bg-primary/5 dark:border-primary/40 dark:bg-primary/15"
                              : "border-border bg-muted/40",
                          )}
                        >
                          {repliedTo && (
                            <div className="mb-1.5 rounded border-l-2 border-border bg-background/70 px-2 py-1 text-xs text-muted-foreground">
                              <span className="font-medium">
                                {repliedTo.author_name ?? "Atendente"}
                              </span>
                              : {truncate(repliedTo.body, 80)}
                            </div>
                          )}
                          <p className="whitespace-pre-wrap text-foreground">{comment.body}</p>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span>{comment.author_name ?? "Atendente"}</span>
                          <span>{formatDateTime(comment.created_at)}</span>
                          {!closed && commentsAllowed && (
                            <button
                              type="button"
                              onClick={() => setReplyTo(comment)}
                              className="inline-flex items-center gap-1 hover:text-foreground"
                            >
                              <Reply size={16} strokeWidth={1.5} />
                              Responder
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              {readOnlyReason ? (
                <p className="border-t border-border pt-4 text-sm text-muted-foreground">
                  {readOnlyReason}
                </p>
              ) : (
                <form onSubmit={onSubmitComment} className="flex flex-col gap-2 border-t border-border pt-4">
                  {replyTo && (
                    <div className="flex items-center justify-between gap-2 rounded border-l-2 border-primary/40 bg-muted/40 px-2 py-1.5 text-xs text-muted-foreground">
                      <span>
                        Respondendo a{" "}
                        <span className="font-medium">{replyTo.author_name ?? "Atendente"}</span>:{" "}
                        {truncate(replyTo.body, 80)}
                      </span>
                      <button
                        type="button"
                        onClick={() => setReplyTo(null)}
                        className="shrink-0 text-muted-foreground hover:text-foreground"
                        aria-label="Cancelar resposta"
                      >
                        <X size={16} strokeWidth={1.5} />
                      </button>
                    </div>
                  )}
                  <Textarea
                    value={commentBody}
                    onChange={(e) => setCommentBody(e.target.value)}
                    onKeyDown={onTextareaKeyDown}
                    placeholder="Escreva um comentario interno..."
                    rows={3}
                  />
                  <Button
                    type="submit"
                    className="self-end"
                    disabled={commentMutation.isPending || !commentBody.trim()}
                  >
                    Enviar
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <ActionPanel detail={data} onChanged={invalidate} />

          <ReversesCard detail={data} onChanged={invalidate} />

          <Card>
            <CardHeader>
              <CardTitle>Garantia</CardTitle>
            </CardHeader>
            <CardContent>
              {ticket.warranty_order_code || ticket.warranty_tracking_code ? (
                <dl className="space-y-2 text-sm">
                  {ticket.warranty_order_code && (
                    <div>
                      <dt className="text-muted-foreground">Pedido</dt>
                      <dd className="font-mono text-foreground">{ticket.warranty_order_code}</dd>
                    </div>
                  )}
                  {ticket.warranty_tracking_code && (
                    <div>
                      <dt className="text-muted-foreground">Rastreio</dt>
                      <dd className="font-mono text-foreground">
                        {ticket.warranty_tracking_code}
                      </dd>
                    </div>
                  )}
                </dl>
              ) : (
                <p className="text-sm text-muted-foreground">Nao registrada.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              {sortedTimeline.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum evento registrado.</p>
              ) : (
                <div className="relative">
                  <div
                    className="absolute top-1.5 bottom-1.5 left-[5px] w-px bg-border"
                    aria-hidden
                  />
                  <ol className="list-none space-y-5">
                    {sortedTimeline.map((event) => (
                      <li key={event.id} className="flex gap-3">
                        <span className="relative z-10 mt-1 size-2.5 shrink-0 rounded-full bg-foreground" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-foreground">{event.title}</p>
                          {(event.old_value || event.new_value) && (
                            <p className="text-xs text-muted-foreground">
                              {statusOrRaw(event.old_value)} → {statusOrRaw(event.new_value)}
                            </p>
                          )}
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {event.author_name ?? "Sistema"} · {formatDateTime(event.created_at)}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
