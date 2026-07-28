import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Plus, Users } from "lucide-react"
import {
  useState,
  type Dispatch,
  type FocusEvent,
  type FormEvent,
  type SetStateAction,
} from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import {
  canCreateCadastros,
  canManageCadastros,
  createCustomer,
  listCustomers,
  lookupCep,
  setCustomerActive,
  updateCustomer,
  type Customer,
  type CustomerInput,
} from "@/lib/cadastros"
import { formatCep, formatDocument, formatPhone, onlyDigits } from "@/lib/format"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

function cityState(customer: Customer): string {
  if (customer.city && customer.state) return `${customer.city}/${customer.state}`
  return customer.city ?? customer.state ?? ""
}

type ClienteFormValues = {
  name: string
  document: string
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

const emptyForm: ClienteFormValues = {
  name: "",
  document: "",
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

function fromCustomer(customer: Customer | null): ClienteFormValues {
  if (!customer) return emptyForm
  return {
    name: customer.name,
    document: formatDocument(customer.document),
    phone: customer.phone ? formatPhone(customer.phone) : "",
    email: customer.email ?? "",
    cep: customer.cep ? formatCep(customer.cep) : "",
    street: customer.street ?? "",
    number: customer.number ?? "",
    complement: customer.complement ?? "",
    neighborhood: customer.neighborhood ?? "",
    city: customer.city ?? "",
    state: customer.state ?? "",
  }
}

function toCustomerInput(values: ClienteFormValues): CustomerInput {
  const orNull = (value: string) => (value.trim() ? value.trim() : null)
  return {
    name: values.name.trim(),
    document: onlyDigits(values.document),
    phone: values.phone.trim() ? onlyDigits(values.phone) : null,
    email: orNull(values.email),
    cep: values.cep.trim() ? onlyDigits(values.cep) : null,
    street: orNull(values.street),
    number: orNull(values.number),
    complement: orNull(values.complement),
    neighborhood: orNull(values.neighborhood),
    city: orNull(values.city),
    state: orNull(values.state),
  }
}

function ClienteForm({
  idPrefix,
  values,
  onChange,
  onSubmit,
  submitLabel,
  submitting,
}: {
  idPrefix: string
  values: ClienteFormValues
  onChange: Dispatch<SetStateAction<ClienteFormValues>>
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  submitLabel: string
  submitting: boolean
}) {
  const [cepLoading, setCepLoading] = useState(false)

  function fieldId(key: keyof ClienteFormValues): string {
    return `${idPrefix}-${key}`
  }

  function setField(key: keyof ClienteFormValues, value: string) {
    onChange((current) => ({ ...current, [key]: value }))
  }

  async function onCepBlur(event: FocusEvent<HTMLInputElement>) {
    const digits = onlyDigits(event.target.value)
    if (digits.length !== 8) return
    setCepLoading(true)
    try {
      const address = await lookupCep(digits)
      onChange((current) => ({
        ...current,
        cep: formatCep(digits),
        street: address.street || current.street,
        neighborhood: address.neighborhood || current.neighborhood,
        city: address.city || current.city,
        state: address.state || current.state,
      }))
    } catch {
      toast.message("CEP nao localizado, preencha o endereco manualmente")
    } finally {
      setCepLoading(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor={fieldId("name")}>Nome</Label>
        <Input
          id={fieldId("name")}
          name="name"
          value={values.name}
          onChange={(e) => setField("name", e.target.value)}
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId("document")}>Documento</Label>
          <Input
            id={fieldId("document")}
            name="document"
            value={values.document}
            onChange={(e) => setField("document", formatDocument(e.target.value))}
            required
            className="font-mono"
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId("phone")}>Telefone</Label>
          <Input
            id={fieldId("phone")}
            name="phone"
            value={values.phone}
            onChange={(e) => setField("phone", formatPhone(e.target.value))}
            className="font-mono"
          />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor={fieldId("email")}>Email</Label>
        <Input
          id={fieldId("email")}
          name="email"
          type="email"
          value={values.email}
          onChange={(e) => setField("email", e.target.value)}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId("cep")} className="flex items-center gap-2">
            CEP
            {cepLoading && (
              <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
                <Loader2 size={16} strokeWidth={1.5} className="animate-spin" />
                buscando
              </span>
            )}
          </Label>
          <Input
            id={fieldId("cep")}
            name="cep"
            value={values.cep}
            onChange={(e) => setField("cep", formatCep(e.target.value))}
            onBlur={onCepBlur}
            className="font-mono"
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId("number")}>Numero</Label>
          <Input
            id={fieldId("number")}
            name="number"
            value={values.number}
            onChange={(e) => setField("number", e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor={fieldId("street")}>Rua</Label>
        <Input
          id={fieldId("street")}
          name="street"
          value={values.street}
          onChange={(e) => setField("street", e.target.value)}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId("complement")}>Complemento</Label>
          <Input
            id={fieldId("complement")}
            name="complement"
            value={values.complement}
            onChange={(e) => setField("complement", e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId("neighborhood")}>Bairro</Label>
          <Input
            id={fieldId("neighborhood")}
            name="neighborhood"
            value={values.neighborhood}
            onChange={(e) => setField("neighborhood", e.target.value)}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId("city")}>Cidade</Label>
          <Input
            id={fieldId("city")}
            name="city"
            value={values.city}
            onChange={(e) => setField("city", e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId("state")}>UF</Label>
          <Input
            id={fieldId("state")}
            name="state"
            value={values.state}
            onChange={(e) => setField("state", e.target.value.toUpperCase())}
            maxLength={2}
            className="uppercase"
          />
        </div>
      </div>

      <Button type="submit" disabled={submitting} className="mt-1">
        {submitting && <Loader2 size={20} strokeWidth={1.5} className="animate-spin" />}
        {submitLabel}
      </Button>
    </form>
  )
}

export default function ClientesPage() {
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState<ClienteFormValues>(emptyForm)
  const [editing, setEditing] = useState<Customer | null>(null)
  const [editForm, setEditForm] = useState<ClienteFormValues>(emptyForm)

  const role = session?.role ?? null
  const podeCriar = canCreateCadastros(role)
  const podeGerenciar = canManageCadastros(role)
  const columnCount = podeGerenciar ? 6 : 5

  const { data, isLoading } = useQuery({
    queryKey: ["clientes", search, page],
    queryFn: () => listCustomers({ search: search || undefined, page, perPage: 20 }),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["clientes"] })

  const createMutation = useMutation({
    mutationFn: (input: CustomerInput) => createCustomer(input),
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      setCreateForm(emptyForm)
      toast.success("Cliente criado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, input }: { id: string; input: CustomerInput }) => updateCustomer(id, input),
    onSuccess: () => {
      invalidate()
      setEditing(null)
      toast.success("Cliente atualizado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const activeMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => setCustomerActive(id, active),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onSearchChange(value: string) {
    setSearch(value)
    setPage(1)
  }

  function onCreateOpenChange(open: boolean) {
    setCreateOpen(open)
    if (!open) setCreateForm(emptyForm)
  }

  function onEditingChange(customer: Customer | null) {
    setEditing(customer)
    setEditForm(fromCustomer(customer))
  }

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    createMutation.mutate(toCustomerInput(createForm))
  }

  function onEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing) return
    updateMutation.mutate({ id: editing.id, input: toCustomerInput(editForm) })
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Users size={20} strokeWidth={1.5} className="text-muted-foreground" />
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Clientes</h1>
        </div>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Buscar por nome ou documento"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-64"
          />
          {podeCriar && (
            <Dialog open={createOpen} onOpenChange={onCreateOpenChange}>
              <DialogTrigger asChild>
                <Button>
                  <Plus size={20} strokeWidth={1.5} />
                  Novo
                </Button>
              </DialogTrigger>
              <DialogContent className="max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>Novo cliente</DialogTitle>
                </DialogHeader>
                <ClienteForm
                  idPrefix="create"
                  values={createForm}
                  onChange={setCreateForm}
                  onSubmit={onCreate}
                  submitLabel="Criar"
                  submitting={createMutation.isPending}
                />
              </DialogContent>
            </Dialog>
          )}
        </div>
      </div>

      <div className="rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Documento</TableHead>
              <TableHead>Telefone</TableHead>
              <TableHead>Cidade/UF</TableHead>
              <TableHead>Status</TableHead>
              {podeGerenciar && <TableHead className="w-40 text-right">Acoes</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={columnCount} className="text-center text-muted-foreground">
                  Carregando clientes...
                </TableCell>
              </TableRow>
            ) : (data?.items ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={columnCount} className="text-center text-muted-foreground">
                  Nenhum registro para este filtro
                </TableCell>
              </TableRow>
            ) : (
              (data?.items ?? []).map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.name}</TableCell>
                  <TableCell className="font-mono">{formatDocument(item.document)}</TableCell>
                  <TableCell className="font-mono">
                    {item.phone ? formatPhone(item.phone) : ""}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{cityState(item)}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{item.active ? "ativo" : "inativo"}</Badge>
                  </TableCell>
                  {podeGerenciar && (
                    <TableCell>
                      <div className="flex items-center justify-end gap-3">
                        <Switch
                          checked={item.active}
                          onCheckedChange={(checked) =>
                            activeMutation.mutate({ id: item.id, active: checked })
                          }
                        />
                        <Button variant="ghost" size="sm" onClick={() => onEditingChange(item)}>
                          Editar
                        </Button>
                      </div>
                    </TableCell>
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{data ? `${data.total} cliente(s)` : ""}</span>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Anterior
          </Button>
          <span>
            Pagina {page} de {data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={!data || page >= Math.ceil(data.total / data.per_page)}
            onClick={() => setPage((p) => p + 1)}
          >
            Proxima
          </Button>
        </div>
      </div>

      <Dialog open={editing != null} onOpenChange={(open) => !open && onEditingChange(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Editar cliente</DialogTitle>
          </DialogHeader>
          {editing && (
            <ClienteForm
              idPrefix="edit"
              values={editForm}
              onChange={setEditForm}
              onSubmit={onEdit}
              submitLabel="Salvar"
              submitting={updateMutation.isPending}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
