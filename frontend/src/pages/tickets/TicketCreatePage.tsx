import { useQuery, useMutation } from "@tanstack/react-query"
import {
  ArrowLeft,
  CircleCheck,
  ClipboardList,
  Loader2,
  Plus,
  ShoppingBag,
  Trash2,
  User,
} from "lucide-react"
import { useState, type FormEvent } from "react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { AutocompleteField } from "@/components/tickets/AutocompleteField"
import { SupervisorSelect } from "@/components/tickets/SupervisorSelect"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { listCatalog, listCustomers, listProducts, lookupCep } from "@/lib/cadastros"
import { fieldErrorProps } from "@/lib/field-error"
import { formatCep, formatDocument, formatPhone, onlyDigits } from "@/lib/format"
import {
  canCreateTicket,
  createTicket,
  PRIORITY_LABELS,
  type TicketCreateInput,
  type TicketPriority,
} from "@/lib/tickets"
import { isValidEmail } from "@/lib/validation"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

type CustomerFieldValues = {
  name: string
  phone: string
  email: string
  cep: string
  street: string
  number: string
  complement: string
  neighborhood: string
  city: string
  state: string
}

const emptyCustomerFields: CustomerFieldValues = {
  name: "",
  phone: "",
  email: "",
  cep: "",
  street: "",
  number: "",
  complement: "",
  neighborhood: "",
  city: "",
  state: "",
}

type ItemRow = {
  key: string
  productId: string
  productQuery: string
  defectTypeId: string
  quantity: number
}

function newItemRow(): ItemRow {
  const key =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `item-${Date.now()}-${Math.random()}`
  return { key, productId: "", productQuery: "", defectTypeId: "", quantity: 1 }
}

const PRIORITY_OPTIONS: { value: TicketPriority; label: string }[] = [
  { value: "urgente", label: `${PRIORITY_LABELS.urgente} — 24h` },
  { value: "alta", label: `${PRIORITY_LABELS.alta} — 48h` },
  { value: "media", label: `${PRIORITY_LABELS.media} — 72h` },
  { value: "baixa", label: `${PRIORITY_LABELS.baixa} — 120h` },
]

export default function TicketCreatePage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const role = session?.role ?? null
  const podeCriar = canCreateTicket(role)

  const [document, setDocument] = useState("")
  const [linkedCustomerId, setLinkedCustomerId] = useState<string | null>(null)
  const [matchedDocument, setMatchedDocument] = useState<string | null>(null)
  const [customerFields, setCustomerFields] = useState<CustomerFieldValues>(emptyCustomerFields)
  const [customerEmailError, setCustomerEmailError] = useState<string | null>(null)
  const [customerLookupLoading, setCustomerLookupLoading] = useState(false)
  const [cepLoading, setCepLoading] = useState(false)

  const [brandId, setBrandId] = useState("")
  const [brandError, setBrandError] = useState(false)
  const [priority, setPriority] = useState<TicketPriority>("media")
  const [channelId, setChannelId] = useState("")
  const [channelQuery, setChannelQuery] = useState("")
  const [orderCode, setOrderCode] = useState("")
  const [purchaseDate, setPurchaseDate] = useState("")
  const [deliveryDate, setDeliveryDate] = useState("")
  const [description, setDescription] = useState("")
  const [supervisorId, setSupervisorId] = useState<string | null>(null)
  const [items, setItems] = useState<ItemRow[]>([])

  const { data: brands } = useQuery({
    queryKey: ["marcas"],
    queryFn: () => listCatalog("marcas"),
  })

  const { data: defectTypes } = useQuery({
    queryKey: ["defeitos"],
    queryFn: () => listCatalog("defeitos"),
  })

  const createMutation = useMutation({
    mutationFn: (input: TicketCreateInput) => createTicket(input),
    onSuccess: (ticket) => {
      toast.success("Ticket criado")
      navigate(`/tickets/${ticket.id}`)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  async function lookupCustomer(digits: string) {
    setCustomerLookupLoading(true)
    try {
      const result = await listCustomers({ search: digits })
      const match = result.items.find((customer) => customer.document === digits)
      if (match) {
        setLinkedCustomerId(match.id)
        setMatchedDocument(digits)
        setCustomerFields({
          name: match.name,
          phone: match.phone ? formatPhone(match.phone) : "",
          email: match.email ?? "",
          cep: match.cep ? formatCep(match.cep) : "",
          street: match.street ?? "",
          number: match.number ?? "",
          complement: match.complement ?? "",
          neighborhood: match.neighborhood ?? "",
          city: match.city ?? "",
          state: match.state ?? "",
        })
      } else {
        if (linkedCustomerId) setCustomerFields(emptyCustomerFields)
        setLinkedCustomerId(null)
        setMatchedDocument(null)
      }
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setCustomerLookupLoading(false)
    }
  }

  function onDocumentChange(rawValue: string) {
    const digits = onlyDigits(rawValue)
    setDocument(digits)
    if (matchedDocument && digits !== matchedDocument) {
      // documento diverge do cliente vinculado: derruba o vinculo/banner antes de
      // qualquer novo lookup, para nao submeter dados de outro cliente.
      setLinkedCustomerId(null)
      setMatchedDocument(null)
    }
    if (digits.length === 11 || digits.length === 14) {
      void lookupCustomer(digits)
    }
  }

  function setCustomerField(key: keyof CustomerFieldValues, value: string) {
    setCustomerFields((current) => ({ ...current, [key]: value }))
  }

  async function lookupAddress(digits: string) {
    setCepLoading(true)
    try {
      const address = await lookupCep(digits)
      setCustomerFields((current) => ({
        ...current,
        cep: formatCep(digits),
        street: address.street || current.street,
        neighborhood: address.neighborhood || current.neighborhood,
        city: address.city || current.city,
        state: address.state || current.state,
      }))
    } catch {
      toast.message("CEP não localizado, preencha o endereço manualmente")
    } finally {
      setCepLoading(false)
    }
  }

  function onCepChange(value: string) {
    const formatted = formatCep(value)
    setCustomerField("cep", formatted)
    const digits = onlyDigits(value)
    if (digits.length === 8) {
      void lookupAddress(digits)
    }
  }

  function addItem() {
    setItems((current) => [...current, newItemRow()])
  }

  function removeItem(key: string) {
    setItems((current) => current.filter((item) => item.key !== key))
  }

  function updateItem(key: string, patch: Partial<ItemRow>) {
    setItems((current) =>
      current.map((item) => (item.key === key ? { ...item, ...patch } : item)),
    )
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    let hasError = false
    if (!brandId) {
      setBrandError(true)
      hasError = true
    } else {
      setBrandError(false)
    }

    const trimmedEmail = customerFields.email.trim()
    if (trimmedEmail && !isValidEmail(trimmedEmail)) {
      setCustomerEmailError("Informe um email válido, com @ e domínio (ex.: nome@empresa.com)")
      hasError = true
    } else {
      setCustomerEmailError(null)
    }

    if (hasError) return

    const validItems = items.filter((item) => item.productId && item.defectTypeId)
    const discarded = items.length - validItems.length
    if (discarded > 0) {
      toast.message(
        discarded === 1
          ? "1 item sem produto ou defeito foi descartado"
          : `${discarded} itens sem produto ou defeito foram descartados`,
      )
    }

    if (channelQuery.trim() && !channelId) {
      toast.message(
        "Canal não selecionado — escolha uma sugestão da lista; o ticket será criado sem canal.",
      )
    }

    const orNull = (value: string) => (value.trim() ? value.trim() : null)

    const payload: TicketCreateInput = {
      brand_id: brandId,
      priority,
      customer: document
        ? {
            name: customerFields.name.trim(),
            document,
            phone: customerFields.phone.trim() ? onlyDigits(customerFields.phone) : null,
            email: orNull(customerFields.email),
            cep: customerFields.cep.trim() ? onlyDigits(customerFields.cep) : null,
            street: orNull(customerFields.street),
            number: orNull(customerFields.number),
            complement: orNull(customerFields.complement),
            neighborhood: orNull(customerFields.neighborhood),
            city: orNull(customerFields.city),
            state: orNull(customerFields.state),
          }
        : undefined,
      purchase_channel_id: channelId || undefined,
      order_code: orderCode.trim() || undefined,
      purchase_date: purchaseDate || undefined,
      delivery_date: deliveryDate || undefined,
      description: description.trim() || undefined,
      supervisor_user_id: supervisorId,
      items:
        validItems.length > 0
          ? validItems.map((item) => ({
              product_id: item.productId,
              defect_type_id: item.defectTypeId,
              quantity: item.quantity,
            }))
          : undefined,
    }

    createMutation.mutate(payload)
  }

  if (!podeCriar) {
    return (
      <div className="space-y-4">
        <Link
          to="/tickets"
          className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={16} strokeWidth={1.5} />
          Voltar para tickets
        </Link>
        <p className="text-sm text-muted-foreground">
          Você não tem permissão para criar tickets.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <div className="space-y-2">
        <Link
          to="/tickets"
          className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={16} strokeWidth={1.5} />
          Voltar para tickets
        </Link>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Novo ticket</h1>
        <p className="text-sm text-muted-foreground">
          Você pode salvar parcialmente e completar depois; o envio para análise exige cliente,
          item e descrição.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <User size={20} strokeWidth={1.5} className="text-muted-foreground" />
            Cliente
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {linkedCustomerId && (
            <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-foreground">
              <CircleCheck size={16} strokeWidth={1.5} className="shrink-0 text-muted-foreground" />
              Cliente já cadastrado — dados carregados; alterações atualizam o cadastro.
            </div>
          )}

          <div className="flex flex-col gap-2 sm:w-1/2">
            <Label htmlFor="documento" className="flex items-center gap-2">
              CPF/CNPJ
              {customerLookupLoading && (
                <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
                  <Loader2 size={16} strokeWidth={1.5} className="animate-spin" />
                  buscando
                </span>
              )}
            </Label>
            <Input
              id="documento"
              value={formatDocument(document)}
              onChange={(e) => onDocumentChange(e.target.value)}
              className="font-mono"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="cliente-nome">Nome</Label>
            <Input
              id="cliente-nome"
              value={customerFields.name}
              onChange={(e) => setCustomerField("name", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="cliente-telefone">Telefone</Label>
              <Input
                id="cliente-telefone"
                value={customerFields.phone}
                onChange={(e) => setCustomerField("phone", formatPhone(e.target.value))}
                className="font-mono"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="cliente-email">Email</Label>
              <Input
                id="cliente-email"
                type="email"
                value={customerFields.email}
                onChange={(e) => {
                  setCustomerField("email", e.target.value)
                  if (customerEmailError) setCustomerEmailError(null)
                }}
                {...fieldErrorProps("cliente-email", customerEmailError)}
              />
              <FieldError fieldId="cliente-email" message={customerEmailError} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="cliente-cep" className="flex items-center gap-2">
                CEP
                {cepLoading && (
                  <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
                    <Loader2 size={16} strokeWidth={1.5} className="animate-spin" />
                    buscando
                  </span>
                )}
              </Label>
              <Input
                id="cliente-cep"
                value={customerFields.cep}
                onChange={(e) => onCepChange(e.target.value)}
                className="font-mono"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="cliente-numero">Número</Label>
              <Input
                id="cliente-numero"
                value={customerFields.number}
                onChange={(e) => setCustomerField("number", e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="cliente-rua">Rua</Label>
            <Input
              id="cliente-rua"
              value={customerFields.street}
              onChange={(e) => setCustomerField("street", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="cliente-complemento">Complemento</Label>
              <Input
                id="cliente-complemento"
                value={customerFields.complement}
                onChange={(e) => setCustomerField("complement", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="cliente-bairro">Bairro</Label>
              <Input
                id="cliente-bairro"
                value={customerFields.neighborhood}
                onChange={(e) => setCustomerField("neighborhood", e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="cliente-cidade">Cidade</Label>
              <Input
                id="cliente-cidade"
                value={customerFields.city}
                onChange={(e) => setCustomerField("city", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="cliente-uf">UF</Label>
              <Input
                id="cliente-uf"
                value={customerFields.state}
                onChange={(e) => setCustomerField("state", e.target.value.toUpperCase())}
                maxLength={2}
                className="uppercase"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShoppingBag size={20} strokeWidth={1.5} className="text-muted-foreground" />
            Compra
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-2 sm:w-1/2">
            <Label htmlFor="canal">Canal de compra</Label>
            <AutocompleteField
              id="canal"
              placeholder="Buscar canal de compra"
              value={channelQuery}
              onValueChange={(value) => {
                setChannelQuery(value)
                setChannelId("")
              }}
              onSelect={(option) => {
                setChannelId(option.id)
                setChannelQuery(option.label)
              }}
              queryKey="canais"
              fetchOptions={async (search) => {
                const results = await listCatalog("canais", { search })
                return results.map((item) => ({ id: item.id, label: item.name }))
              }}
            />
          </div>

          <div className="flex flex-col gap-2 sm:w-1/2">
            <Label htmlFor="pedido">Pedido</Label>
            <Input
              id="pedido"
              value={orderCode}
              onChange={(e) => setOrderCode(e.target.value)}
              className="font-mono"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="data-compra">Data da compra</Label>
              <Input
                id="data-compra"
                type="date"
                value={purchaseDate}
                onChange={(e) => setPurchaseDate(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="data-entrega">Data de entrega</Label>
              <Input
                id="data-entrega"
                type="date"
                value={deliveryDate}
                onChange={(e) => setDeliveryDate(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ClipboardList size={20} strokeWidth={1.5} className="text-muted-foreground" />
            Caso
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="marca">Marca</Label>
              <Select
                value={brandId}
                onValueChange={(value) => {
                  setBrandId(value)
                  setBrandError(false)
                }}
              >
                <SelectTrigger
                  id="marca"
                  className="w-full"
                  aria-invalid={brandError}
                  aria-describedby={brandError ? "marca-error" : undefined}
                >
                  <SelectValue placeholder="Selecione a marca" />
                </SelectTrigger>
                <SelectContent>
                  {(brands ?? []).map((brand) => (
                    <SelectItem key={brand.id} value={brand.id}>
                      {brand.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {brandError && (
                <p id="marca-error" className="text-xs text-destructive">
                  Selecione a marca
                </p>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="prioridade">Prioridade</Label>
              <Select
                value={priority}
                onValueChange={(value) => setPriority(value as TicketPriority)}
              >
                <SelectTrigger id="prioridade" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITY_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="descricao">Descrição</Label>
            <Textarea
              id="descricao"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Descreva o defeito relatado pelo cliente"
            />
          </div>

          <div className="flex flex-col gap-2 sm:w-1/2">
            <Label htmlFor="supervisor">Supervisor</Label>
            <SupervisorSelect id="supervisor" value={supervisorId} onChange={setSupervisorId} />
          </div>

          <div className="space-y-3 border-t border-border pt-4">
            <p className="text-sm font-medium text-foreground">Itens</p>
            {items.length === 0 && (
              <p className="text-sm text-muted-foreground">Nenhum item adicionado.</p>
            )}
            <div className="space-y-3">
              {items.map((item) => (
                <div
                  key={item.key}
                  className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_6rem_auto] sm:items-start"
                >
                  <AutocompleteField
                    id={`item-produto-${item.key}`}
                    placeholder="Buscar produto por nome ou SKU"
                    value={item.productQuery}
                    onValueChange={(value) =>
                      updateItem(item.key, { productQuery: value, productId: "" })
                    }
                    onSelect={(option) =>
                      updateItem(item.key, { productId: option.id, productQuery: option.label })
                    }
                    queryKey={`produto-${item.key}`}
                    fetchOptions={async (search) => {
                      const page = await listProducts({ search, perPage: 10 })
                      return page.items.map((product) => ({
                        id: product.id,
                        label: product.name,
                        sublabel: product.sku,
                      }))
                    }}
                  />

                  <Select
                    value={item.defectTypeId}
                    onValueChange={(value) => updateItem(item.key, { defectTypeId: value })}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Defeito" />
                    </SelectTrigger>
                    <SelectContent>
                      {(defectTypes ?? []).map((defect) => (
                        <SelectItem key={defect.id} value={defect.id}>
                          {defect.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Input
                    type="number"
                    min={1}
                    value={item.quantity}
                    onChange={(e) =>
                      updateItem(item.key, { quantity: Math.max(1, Number(e.target.value) || 1) })
                    }
                  />

                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeItem(item.key)}
                    aria-label="Remover item"
                  >
                    <Trash2 size={16} strokeWidth={1.5} />
                  </Button>
                </div>
              ))}
            </div>
            <Button type="button" variant="outline" onClick={addItem}>
              <Plus size={16} strokeWidth={1.5} />
              Adicionar item
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => navigate("/tickets")}>
          Cancelar
        </Button>
        <Button type="submit" disabled={createMutation.isPending}>
          {createMutation.isPending && (
            <Loader2 size={20} strokeWidth={1.5} className="animate-spin" />
          )}
          Criar ticket
        </Button>
      </div>
    </form>
  )
}
