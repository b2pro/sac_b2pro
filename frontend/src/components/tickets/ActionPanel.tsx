import { useMutation, useQuery } from "@tanstack/react-query"
import { CircleCheck, Loader2, MoreVertical, Trash2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"

import { AttendantSelect } from "@/components/tickets/AttendantSelect"
import { StatusTrail } from "@/components/tickets/StatusTrail"
import { SupervisorSelect } from "@/components/tickets/SupervisorSelect"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { FieldError } from "@/components/ui/field-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { listCatalog, listCustomers } from "@/lib/cadastros"
import { fieldErrorProps } from "@/lib/field-error"
import { formatDocument, onlyDigits } from "@/lib/format"
import {
  approveTicket,
  cancelTicket,
  canComment,
  canDecide,
  canEditTicket,
  canOperate,
  declineTicket,
  deleteReverse,
  finalizeTicket,
  holdTicket,
  isClosed,
  markUnread,
  PRIORITY_LABELS,
  primaryActionFor,
  receiveProduct,
  registerReverse,
  reopenTicket,
  resumeTicket,
  setWarranty,
  submitTicket,
  updateTicket,
  type ReverseCode,
  type TicketDetail,
  type TicketPriority,
  type TicketUpdateInput,
} from "@/lib/tickets"

type DialogKind =
  | "aprovar"
  | "declinar"
  | "cancelar"
  | "finalizar"
  | "reverso"
  | "garantia"
  | "editar"
  | null

const CHANNEL_NONE = "nenhum"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

function formatDateTime(value: string | null): string {
  return value
    ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })
    : "-"
}

export function ActionPanel({
  detail,
  onChanged,
}: {
  detail: TicketDetail
  onChanged: () => void
}) {
  const { session } = useAuth()
  const role = session?.role ?? null
  const userId = session?.user.id
  const { ticket } = detail
  const owner = ticket.attendant_user_id === userId
  const closed = isClosed(ticket.status)
  const primary = primaryActionFor(ticket, role, userId)

  const [dialog, setDialog] = useState<DialogKind>(null)
  const [notes, setNotes] = useState("")
  const [declineReason, setDeclineReason] = useState("")
  const [declineReasonError, setDeclineReasonError] = useState<string | null>(null)
  const [cancelReason, setCancelReason] = useState("")
  const [reverseCode, setReverseCode] = useState("")
  const [reverseCodeError, setReverseCodeError] = useState<string | null>(null)
  const [solutionTypeId, setSolutionTypeId] = useState("")
  const [solutionTypeError, setSolutionTypeError] = useState<string | null>(null)
  const [finalNotes, setFinalNotes] = useState("")
  const [warrantyOrderCode, setWarrantyOrderCode] = useState("")
  const [warrantyOrderCodeError, setWarrantyOrderCodeError] = useState<string | null>(null)
  const [warrantyTracking, setWarrantyTracking] = useState("")
  const [editBrandId, setEditBrandId] = useState(ticket.brand_id)
  const [editChannelId, setEditChannelId] = useState(ticket.purchase_channel_id ?? CHANNEL_NONE)
  const [editPriority, setEditPriority] = useState<TicketPriority>(ticket.priority)
  const [editOrderCode, setEditOrderCode] = useState(ticket.order_code ?? "")
  const [editPurchaseDate, setEditPurchaseDate] = useState(ticket.purchase_date?.slice(0, 10) ?? "")
  const [editDeliveryDate, setEditDeliveryDate] = useState(ticket.delivery_date?.slice(0, 10) ?? "")
  const [editDescription, setEditDescription] = useState(ticket.description ?? "")
  const [editSupervisorId, setEditSupervisorId] = useState<string | null>(
    ticket.supervisor_user_id ?? null,
  )
  const [editAttendantId, setEditAttendantId] = useState(ticket.attendant_user_id)
  const [editDocument, setEditDocument] = useState("")
  const [editCustomerId, setEditCustomerId] = useState<string | null>(ticket.customer_id)
  const [editCustomerName, setEditCustomerName] = useState<string | null>(
    detail.customer?.name ?? null,
  )
  const [customerLookupLoading, setCustomerLookupLoading] = useState(false)
  const [customerNotFound, setCustomerNotFound] = useState(false)

  const { data: brands } = useQuery({
    queryKey: ["marcas"],
    queryFn: () => listCatalog("marcas"),
    enabled: dialog === "editar",
  })
  const { data: channels } = useQuery({
    queryKey: ["canais"],
    queryFn: () => listCatalog("canais"),
    enabled: dialog === "editar",
  })
  const { data: solutions } = useQuery({
    queryKey: ["solucoes"],
    queryFn: () => listCatalog("solucoes"),
    enabled: dialog === "finalizar",
  })

  function openDialog(kind: DialogKind) {
    if (kind === "aprovar") setNotes("")
    if (kind === "declinar") {
      setDeclineReason("")
      setDeclineReasonError(null)
    }
    if (kind === "cancelar") setCancelReason("")
    if (kind === "reverso") {
      setReverseCode("")
      setReverseCodeError(null)
    }
    if (kind === "finalizar") {
      setSolutionTypeId("")
      setSolutionTypeError(null)
      setFinalNotes("")
    }
    if (kind === "garantia") {
      setWarrantyOrderCode(ticket.warranty_order_code ?? "")
      setWarrantyOrderCodeError(null)
      setWarrantyTracking(ticket.warranty_tracking_code ?? "")
    }
    if (kind === "editar") {
      setEditBrandId(ticket.brand_id)
      setEditChannelId(ticket.purchase_channel_id ?? CHANNEL_NONE)
      setEditPriority(ticket.priority)
      setEditOrderCode(ticket.order_code ?? "")
      setEditPurchaseDate(ticket.purchase_date?.slice(0, 10) ?? "")
      setEditDeliveryDate(ticket.delivery_date?.slice(0, 10) ?? "")
      setEditDescription(ticket.description ?? "")
      setEditSupervisorId(ticket.supervisor_user_id ?? null)
      setEditAttendantId(ticket.attendant_user_id)
      setEditDocument("")
      setEditCustomerId(ticket.customer_id)
      setEditCustomerName(detail.customer?.name ?? null)
      setCustomerNotFound(false)
    }
    setDialog(kind)
  }

  function closeDialog() {
    setDialog(null)
  }

  async function lookupEditCustomer(digits: string) {
    setCustomerLookupLoading(true)
    try {
      const result = await listCustomers({ search: digits })
      const match = result.items.find((customer) => customer.document === digits)
      if (match) {
        setEditCustomerId(match.id)
        setEditCustomerName(match.name)
        setCustomerNotFound(false)
      } else {
        setCustomerNotFound(true)
      }
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setCustomerLookupLoading(false)
    }
  }

  function onEditDocumentChange(rawValue: string) {
    const digits = onlyDigits(rawValue)
    setEditDocument(digits)
    setCustomerNotFound(false)
    if (digits.length === 11 || digits.length === 14) {
      void lookupEditCustomer(digits)
    }
  }

  const onImmediateSuccess = (message: string) => () => {
    toast.success(message)
    onChanged()
  }
  const onDialogSuccess = (message: string) => () => {
    toast.success(message)
    closeDialog()
    onChanged()
  }
  const onMutationError = (error: unknown) => toast.error(errorMessage(error))

  const submitMutation = useMutation({
    mutationFn: () => submitTicket(ticket.id),
    onSuccess: onImmediateSuccess("Enviado para análise"),
    onError: onMutationError,
  })
  const resumeMutation = useMutation({
    mutationFn: () => resumeTicket(ticket.id),
    onSuccess: onImmediateSuccess("Atendimento retomado"),
    onError: onMutationError,
  })
  const receiveMutation = useMutation({
    mutationFn: () => receiveProduct(ticket.id),
    onSuccess: onImmediateSuccess("Produto recebido"),
    onError: onMutationError,
  })
  const reopenMutation = useMutation({
    mutationFn: () => reopenTicket(ticket.id),
    onSuccess: onImmediateSuccess("Ticket reaberto"),
    onError: onMutationError,
  })
  const holdMutation = useMutation({
    mutationFn: () => holdTicket(ticket.id),
    onSuccess: onImmediateSuccess("Aguardando retorno do cliente"),
    onError: onMutationError,
  })
  const markUnreadMutation = useMutation({
    mutationFn: () => markUnread(ticket.id),
    // Sem onChanged() de proposito: refazer o GET do detalhe marca o ticket como
    // lido novamente no servidor, anulando a acao. A lista recarrega ao voltar.
    onSuccess: () => toast.success("Marcado como não lido"),
    onError: onMutationError,
  })

  const approveMutation = useMutation({
    mutationFn: () => approveTicket(ticket.id, notes.trim() || undefined),
    onSuccess: onDialogSuccess("Ticket aprovado"),
    onError: onMutationError,
  })
  const declineMutation = useMutation({
    mutationFn: () => declineTicket(ticket.id, declineReason.trim()),
    onSuccess: onDialogSuccess("Ticket declinado"),
    onError: onMutationError,
  })
  const cancelMutation = useMutation({
    mutationFn: () => cancelTicket(ticket.id, cancelReason.trim() || undefined),
    onSuccess: onDialogSuccess("Ticket cancelado"),
    onError: onMutationError,
  })
  const reverseMutation = useMutation({
    mutationFn: () => registerReverse(ticket.id, reverseCode.trim()),
    onSuccess: onDialogSuccess("Reverso registrado"),
    onError: onMutationError,
  })
  const finalizeMutation = useMutation({
    mutationFn: () => finalizeTicket(ticket.id, solutionTypeId, finalNotes.trim() || undefined),
    onSuccess: onDialogSuccess("Ticket finalizado"),
    onError: onMutationError,
  })
  const warrantyMutation = useMutation({
    mutationFn: () =>
      setWarranty(ticket.id, warrantyOrderCode.trim(), warrantyTracking.trim() || undefined),
    onSuccess: onDialogSuccess("Garantia registrada"),
    onError: onMutationError,
  })
  const editMutation = useMutation({
    mutationFn: () => {
      const input: TicketUpdateInput = {
        brand_id: editBrandId,
        priority: editPriority,
        customer_id: editCustomerId,
        supervisor_user_id: editSupervisorId,
        attendant_user_id: editAttendantId,
        purchase_channel_id: editChannelId === CHANNEL_NONE ? null : editChannelId,
        order_code: editOrderCode.trim() || null,
        purchase_date: editPurchaseDate || null,
        delivery_date: editDeliveryDate || null,
        description: editDescription.trim() || null,
      }
      return updateTicket(ticket.id, input)
    },
    onSuccess: onDialogSuccess("Dados atualizados"),
    onError: onMutationError,
  })

  const immediateBusy =
    submitMutation.isPending ||
    resumeMutation.isPending ||
    receiveMutation.isPending ||
    reopenMutation.isPending

  function onPrimaryClick() {
    if (!primary) return
    switch (primary.action) {
      case "enviar_analise":
        submitMutation.mutate()
        break
      case "retomar":
        resumeMutation.mutate()
        break
      case "produto_recebido":
        receiveMutation.mutate()
        break
      case "reabrir":
        reopenMutation.mutate()
        break
      case "registrar_reverso":
        openDialog("reverso")
        break
      case "finalizar":
        openDialog("finalizar")
        break
      case "aprovar":
        openDialog("aprovar")
        break
      default:
        break
    }
  }

  function onSubmitDeclinar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!declineReason.trim()) {
      setDeclineReasonError("Informe o motivo do declínio")
      return
    }
    setDeclineReasonError(null)
    declineMutation.mutate()
  }

  function onSubmitFinalizar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!solutionTypeId) {
      setSolutionTypeError("Selecione a solução aplicada")
      return
    }
    setSolutionTypeError(null)
    finalizeMutation.mutate()
  }

  function onSubmitReverso(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!reverseCode.trim()) {
      setReverseCodeError("Informe o código reverso")
      return
    }
    setReverseCodeError(null)
    reverseMutation.mutate()
  }

  function onSubmitGarantia(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!warrantyOrderCode.trim()) {
      setWarrantyOrderCodeError("Informe o código do pedido de garantia")
      return
    }
    setWarrantyOrderCodeError(null)
    warrantyMutation.mutate()
  }

  const showHold = ticket.status === "aberto" && canEditTicket(role, owner, ticket.status)
  const showFinalizeDirect = ticket.status === "aprovado" && canOperate(role, owner)
  const showWarranty = !closed && canOperate(role, owner)
  const showEdit = canEditTicket(role, owner, ticket.status)
  const showCancel = !closed && canDecide(role)
  const showMarkUnread = canComment(role)
  const hasMenu =
    showHold || showFinalizeDirect || showWarranty || showEdit || showCancel || showMarkUnread

  function renderActionArea() {
    if (ticket.status === "aguardando_analise") {
      if (!canDecide(role)) {
        return <p className="text-sm text-muted-foreground">Aguardando decisão do supervisor.</p>
      }
      return (
        <div className="flex gap-2">
          <Button className="flex-1" onClick={() => openDialog("aprovar")}>
            Aprovar
          </Button>
          <Button variant="outline" className="flex-1" onClick={() => openDialog("declinar")}>
            Declinar
          </Button>
        </div>
      )
    }
    if (!primary) return null
    return (
      <Button className="w-full" disabled={immediateBusy} onClick={onPrimaryClick}>
        {immediateBusy && <Loader2 size={20} strokeWidth={1.5} className="animate-spin" />}
        {primary.label}
      </Button>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle>Status</CardTitle>
        {hasMenu && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Mais ações do ticket">
                <MoreVertical size={20} strokeWidth={1.5} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {showHold && (
                <DropdownMenuItem
                  disabled={holdMutation.isPending}
                  onClick={() => holdMutation.mutate()}
                >
                  Aguardar cliente
                </DropdownMenuItem>
              )}
              {showFinalizeDirect && (
                <DropdownMenuItem onClick={() => openDialog("finalizar")}>
                  Finalizar direto
                </DropdownMenuItem>
              )}
              {showWarranty && (
                <DropdownMenuItem onClick={() => openDialog("garantia")}>
                  Registrar garantia
                </DropdownMenuItem>
              )}
              {showEdit && (
                <DropdownMenuItem onClick={() => openDialog("editar")}>
                  Editar dados
                </DropdownMenuItem>
              )}
              {(showCancel || showMarkUnread) &&
                (showHold || showFinalizeDirect || showWarranty || showEdit) && (
                  <DropdownMenuSeparator />
                )}
              {showCancel && (
                <DropdownMenuItem variant="destructive" onClick={() => openDialog("cancelar")}>
                  Cancelar ticket
                </DropdownMenuItem>
              )}
              {showMarkUnread && (
                <DropdownMenuItem
                  disabled={markUnreadMutation.isPending}
                  onClick={() => markUnreadMutation.mutate()}
                >
                  Marcar como não lido
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <StatusTrail status={ticket.status} sla={ticket.sla} />
        {renderActionArea()}
      </CardContent>

      <Dialog open={dialog === "aprovar"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Aprovar ticket</DialogTitle>
            <DialogDescription>
              Notas são opcionais e ficam registradas no histórico.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              approveMutation.mutate()
            }}
            noValidate
            className="flex flex-col gap-4"
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="aprovar-notes">Notas (opcional)</Label>
              <Textarea
                id="aprovar-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancelar
              </Button>
              <Button type="submit" disabled={approveMutation.isPending}>
                Confirmar
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog === "declinar"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Declinar ticket</DialogTitle>
            <DialogDescription>Informe o motivo da recusa.</DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmitDeclinar} noValidate className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="declinar-reason">Motivo</Label>
              <Textarea
                id="declinar-reason"
                value={declineReason}
                onChange={(e) => {
                  setDeclineReason(e.target.value)
                  if (declineReasonError && e.target.value.trim()) setDeclineReasonError(null)
                }}
                rows={3}
                required
                {...fieldErrorProps("declinar-reason", declineReasonError)}
              />
              <FieldError fieldId="declinar-reason" message={declineReasonError} />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancelar
              </Button>
              <Button type="submit" variant="destructive" disabled={declineMutation.isPending}>
                Declinar
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog === "cancelar"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar ticket</DialogTitle>
            <DialogDescription>
              Esta ação encerra o ticket e não pode ser desfeita. Informe um motivo, se desejar.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              cancelMutation.mutate()
            }}
            noValidate
            className="flex flex-col gap-4"
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="cancelar-reason">Motivo (opcional)</Label>
              <Textarea
                id="cancelar-reason"
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                rows={3}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Voltar
              </Button>
              <Button type="submit" variant="destructive" disabled={cancelMutation.isPending}>
                Cancelar ticket
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog === "finalizar"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Finalizar ticket</DialogTitle>
            <DialogDescription>Selecione a solução aplicada.</DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmitFinalizar} noValidate className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="finalizar-solucao">Solução</Label>
              <Select
                value={solutionTypeId}
                onValueChange={(value) => {
                  setSolutionTypeId(value)
                  setSolutionTypeError(null)
                }}
              >
                <SelectTrigger
                  id="finalizar-solucao"
                  className="w-full"
                  {...fieldErrorProps("finalizar-solucao", solutionTypeError)}
                >
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  {(solutions ?? []).map((solution) => (
                    <SelectItem key={solution.id} value={solution.id}>
                      {solution.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldError fieldId="finalizar-solucao" message={solutionTypeError} />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="finalizar-notes">Notas (opcional)</Label>
              <Textarea
                id="finalizar-notes"
                value={finalNotes}
                onChange={(e) => setFinalNotes(e.target.value)}
                rows={3}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancelar
              </Button>
              <Button type="submit" disabled={finalizeMutation.isPending}>
                Finalizar
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog === "reverso"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar reverso</DialogTitle>
            <DialogDescription>Informe o código de rastreio do envio reverso.</DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmitReverso} noValidate className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="reverso-code">Código</Label>
              <Input
                id="reverso-code"
                className="font-mono"
                value={reverseCode}
                onChange={(e) => {
                  setReverseCode(e.target.value)
                  if (reverseCodeError && e.target.value.trim()) setReverseCodeError(null)
                }}
                required
                {...fieldErrorProps("reverso-code", reverseCodeError)}
              />
              <FieldError fieldId="reverso-code" message={reverseCodeError} />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancelar
              </Button>
              <Button type="submit" disabled={reverseMutation.isPending}>
                Registrar
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog === "garantia"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar garantia</DialogTitle>
            <DialogDescription>Pedido de garantia junto ao fabricante.</DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmitGarantia} noValidate className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="garantia-order">Pedido</Label>
              <Input
                id="garantia-order"
                className="font-mono"
                value={warrantyOrderCode}
                onChange={(e) => {
                  setWarrantyOrderCode(e.target.value)
                  if (warrantyOrderCodeError && e.target.value.trim()) setWarrantyOrderCodeError(null)
                }}
                required
                {...fieldErrorProps("garantia-order", warrantyOrderCodeError)}
              />
              <FieldError fieldId="garantia-order" message={warrantyOrderCodeError} />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="garantia-tracking">Rastreio (opcional)</Label>
              <Input
                id="garantia-tracking"
                className="font-mono"
                value={warrantyTracking}
                onChange={(e) => setWarrantyTracking(e.target.value)}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancelar
              </Button>
              <Button type="submit" disabled={warrantyMutation.isPending}>
                Registrar
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog === "editar"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Editar dados do ticket</DialogTitle>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              editMutation.mutate()
            }}
            noValidate
            className="flex flex-col gap-4"
          >
            <div className="flex flex-col gap-2 border-b border-border pb-4">
              <Label htmlFor="editar-documento" className="flex items-center gap-2">
                CPF/CNPJ do cliente
                {customerLookupLoading && (
                  <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
                    <Loader2 size={16} strokeWidth={1.5} className="animate-spin" />
                    buscando
                  </span>
                )}
              </Label>
              <Input
                id="editar-documento"
                placeholder="Digite para vincular outro cliente"
                value={formatDocument(editDocument)}
                onChange={(e) => onEditDocumentChange(e.target.value)}
                className="font-mono"
              />
              {customerNotFound ? (
                <p className="text-xs text-muted-foreground">
                  Cliente não encontrado —{" "}
                  <Link to="/cadastros/clientes" className="text-primary-text hover:underline">
                    cadastre em Cadastros &gt; Clientes
                  </Link>
                  . O vínculo atual foi mantido.
                </p>
              ) : (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <CircleCheck size={16} strokeWidth={1.5} className="shrink-0" />
                  Cliente vinculado: {editCustomerName ?? "nenhum"}
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="editar-marca">Marca</Label>
                <Select value={editBrandId} onValueChange={setEditBrandId}>
                  <SelectTrigger id="editar-marca" className="w-full">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {(brands ?? []).map((brand) => (
                      <SelectItem key={brand.id} value={brand.id}>
                        {brand.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="editar-canal">Canal</Label>
                <Select value={editChannelId} onValueChange={setEditChannelId}>
                  <SelectTrigger id="editar-canal" className="w-full">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={CHANNEL_NONE}>Não informado</SelectItem>
                    {(channels ?? []).map((channel) => (
                      <SelectItem key={channel.id} value={channel.id}>
                        {channel.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="editar-prioridade">Prioridade</Label>
                <Select
                  value={editPriority}
                  onValueChange={(value) => setEditPriority(value as TicketPriority)}
                >
                  <SelectTrigger id="editar-prioridade" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="editar-pedido">Pedido</Label>
                <Input
                  id="editar-pedido"
                  className="font-mono"
                  value={editOrderCode}
                  onChange={(e) => setEditOrderCode(e.target.value)}
                />
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="editar-supervisor">Supervisor</Label>
              <SupervisorSelect
                id="editar-supervisor"
                value={editSupervisorId}
                onChange={setEditSupervisorId}
              />
            </div>

            {canDecide(role) && (
              <div className="flex flex-col gap-2">
                <Label htmlFor="editar-atendente">Atendente responsável</Label>
                <AttendantSelect
                  id="editar-atendente"
                  value={editAttendantId}
                  currentName={detail.attendant_name}
                  onChange={setEditAttendantId}
                />
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="editar-compra">Data da compra</Label>
                <Input
                  id="editar-compra"
                  type="date"
                  value={editPurchaseDate}
                  onChange={(e) => setEditPurchaseDate(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="editar-entrega">Data de entrega</Label>
                <Input
                  id="editar-entrega"
                  type="date"
                  value={editDeliveryDate}
                  onChange={(e) => setEditDeliveryDate(e.target.value)}
                />
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="editar-descricao">Descrição</Label>
              <Textarea
                id="editar-descricao"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                rows={4}
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancelar
              </Button>
              <Button type="submit" disabled={editMutation.isPending}>
                Salvar
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

export function ReversesCard({
  detail,
  onChanged,
}: {
  detail: TicketDetail
  onChanged: () => void
}) {
  const { session } = useAuth()
  const role = session?.role ?? null
  const userId = session?.user.id
  const { ticket, reverses } = detail
  const owner = ticket.attendant_user_id === userId
  const canRemove =
    canOperate(role, owner) &&
    (ticket.status === "aguardando_envio_reverso" || ticket.status === "produto_recebido")

  const [toRemove, setToRemove] = useState<ReverseCode | null>(null)

  const removeMutation = useMutation({
    mutationFn: (reverseId: string) => deleteReverse(ticket.id, reverseId),
    onSuccess: () => {
      toast.success("Reverso removido")
      setToRemove(null)
      onChanged()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Reversos</CardTitle>
      </CardHeader>
      <CardContent>
        {reverses.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum código reverso.</p>
        ) : (
          <ul className="space-y-3 text-sm">
            {reverses.map((reverse) => (
              <li key={reverse.id} className="flex items-start justify-between gap-2">
                <div className="flex flex-col">
                  <span className="font-mono text-foreground">{reverse.code}</span>
                  <span className="text-xs text-muted-foreground">
                    {reverse.author_name ?? "-"} · {formatDateTime(reverse.created_at)}
                  </span>
                </div>
                {canRemove && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setToRemove(reverse)}
                    aria-label={`Remover reverso ${reverse.code}`}
                  >
                    <Trash2 size={16} strokeWidth={1.5} />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      <Dialog open={toRemove != null} onOpenChange={(open) => !open && setToRemove(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remover reverso</DialogTitle>
            <DialogDescription>
              {toRemove
                ? `Remover o código ${toRemove.code}? Esta ação não pode ser desfeita.`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setToRemove(null)}>
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={removeMutation.isPending}
              onClick={() => toRemove && removeMutation.mutate(toRemove.id)}
            >
              Remover
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
