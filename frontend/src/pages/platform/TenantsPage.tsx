import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Building2, Link2, MoreHorizontal, Plus, SlidersHorizontal } from "lucide-react"
import { useState, type FormEvent } from "react"
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
import { fieldErrorProps } from "@/lib/field-error"
import {
  KNOWN_MODULES,
  createLink,
  createTenant,
  deleteLink,
  listLinks,
  listTenants,
  listUsers,
  setTenantModules,
  setTenantStatus,
  type Tenant,
  type TenantLink,
  type TenantStatus,
} from "@/lib/platform"

const ROLES: TenantLink["role"][] = ["admin", "supervisor", "atendente", "visualizador"]

const STATUSES: TenantStatus[] = ["ativa", "teste", "suspensa", "inativa"]

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

function CreateTenantForm({
  onSubmit,
  submitting,
}: {
  onSubmit: (values: { slug: string; name: string }) => void
  submitting: boolean
}) {
  const [slugError, setSlugError] = useState<string | null>(null)
  const [nameError, setNameError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const slug = String(form.get("slug")).trim()
    const name = String(form.get("name")).trim()

    const nextSlugError = slug ? null : "Informe o slug"
    const nextNameError = name ? null : "Informe o nome"
    setSlugError(nextSlugError)
    setNameError(nextNameError)
    if (nextSlugError || nextNameError) return

    onSubmit({ slug, name })
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="slug">Slug</Label>
        <Input
          id="slug"
          name="slug"
          className="font-mono"
          required
          {...fieldErrorProps("slug", slugError)}
        />
        <FieldError fieldId="slug" message={slugError} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="name">Nome</Label>
        <Input id="name" name="name" required {...fieldErrorProps("name", nameError)} />
        <FieldError fieldId="name" message={nameError} />
      </div>
      <Button type="submit" disabled={submitting} className="mt-1">
        Criar
      </Button>
    </form>
  )
}

export default function TenantsPage() {
  const queryClient = useQueryClient()
  const { data: tenants, isLoading } = useQuery({ queryKey: ["tenants"], queryFn: listTenants })
  const [createOpen, setCreateOpen] = useState(false)
  const [modulesTenant, setModulesTenant] = useState<Tenant | null>(null)
  const [linksTenant, setLinksTenant] = useState<Tenant | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["tenants"] })

  const createMutation = useMutation({
    mutationFn: createTenant,
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      toast.success("Tenant criado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: TenantStatus }) =>
      setTenantStatus(id, status),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  const modulesMutation = useMutation({
    mutationFn: ({ id, modules }: { id: string; modules: Record<string, boolean> }) =>
      setTenantModules(id, modules),
    onSuccess: () => {
      invalidate()
      setModulesTenant(null)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onCreate(values: { slug: string; name: string }) {
    createMutation.mutate(values)
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Building2 size={20} strokeWidth={1.5} className="text-muted-foreground" />
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Tenants</h1>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus size={20} strokeWidth={1.5} />
              Novo tenant
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo tenant</DialogTitle>
            </DialogHeader>
            <CreateTenantForm onSubmit={onCreate} submitting={createMutation.isPending} />
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Slug</TableHead>
              <TableHead>Nome</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Módulos</TableHead>
              <TableHead className="w-16 text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Carregando tenants...
                </TableCell>
              </TableRow>
            ) : (tenants ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Nenhum tenant cadastrado
                </TableCell>
              </TableRow>
            ) : (
              (tenants ?? []).map((tenant) => (
                <TableRow key={tenant.id}>
                  <TableCell className="font-mono text-sm">{tenant.slug}</TableCell>
                  <TableCell>{tenant.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{tenant.status}</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {Object.entries(tenant.modules)
                      .filter(([, on]) => on)
                      .map(([name]) => name)
                      .join(", ") || "nenhum"}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm">
                          <MoreHorizontal size={16} strokeWidth={1.5} />
                          <span className="sr-only">Ações de {tenant.name}</span>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {STATUSES.filter((s) => s !== tenant.status).map((status) => (
                          <DropdownMenuItem
                            key={status}
                            onSelect={() => statusMutation.mutate({ id: tenant.id, status })}
                          >
                            Marcar como {status}
                          </DropdownMenuItem>
                        ))}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onSelect={() => setModulesTenant(tenant)}>
                          <SlidersHorizontal size={16} strokeWidth={1.5} />
                          Módulos
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => setLinksTenant(tenant)}>
                          <Link2 size={16} strokeWidth={1.5} />
                          Vínculos
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={modulesTenant != null} onOpenChange={(open) => !open && setModulesTenant(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Módulos de {modulesTenant?.name}</DialogTitle>
          </DialogHeader>
          {modulesTenant && (
            <ModulesForm
              tenant={modulesTenant}
              pending={modulesMutation.isPending}
              onSave={(modules) => modulesMutation.mutate({ id: modulesTenant.id, modules })}
            />
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={linksTenant != null} onOpenChange={(open) => !open && setLinksTenant(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Vínculos de {linksTenant?.name}</DialogTitle>
          </DialogHeader>
          {linksTenant && <LinksDialogContent tenant={linksTenant} />}
        </DialogContent>
      </Dialog>
    </section>
  )
}

function ModulesForm({
  tenant,
  pending,
  onSave,
}: {
  tenant: Tenant
  pending: boolean
  onSave: (modules: Record<string, boolean>) => void
}) {
  const [modules, setModules] = useState<Record<string, boolean>>(() => ({
    ...Object.fromEntries(KNOWN_MODULES.map((name) => [name, false])),
    ...tenant.modules,
  }))

  return (
    <div className="flex flex-col gap-1">
      {Object.entries(modules).map(([name, enabled]) => (
        <div
          key={name}
          className="flex items-center justify-between border-b border-border py-2.5 last:border-0"
        >
          <span className="font-mono text-sm text-foreground">{name}</span>
          <Switch
            checked={enabled}
            onCheckedChange={(checked) => setModules({ ...modules, [name]: checked })}
          />
        </div>
      ))}
      <Button onClick={() => onSave(modules)} disabled={pending} className="mt-3">
        Salvar
      </Button>
    </div>
  )
}

function LinksDialogContent({ tenant }: { tenant: Tenant }) {
  const queryClient = useQueryClient()
  const { data: links, isLoading } = useQuery({
    queryKey: ["links", tenant.id],
    queryFn: () => listLinks(tenant.id),
  })
  const { data: users } = useQuery({ queryKey: ["platform-users"], queryFn: listUsers })
  const [userId, setUserId] = useState("")
  const [role, setRole] = useState<TenantLink["role"]>("atendente")

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["links", tenant.id] })

  const addMutation = useMutation({
    mutationFn: () => createLink(tenant.id, { user_id: userId, role }),
    onSuccess: () => {
      invalidate()
      setUserId("")
      setRole("atendente")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
  const removeMutation = useMutation({
    mutationFn: (linkUserId: string) => deleteLink(tenant.id, linkUserId),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  const emailById = new Map((users ?? []).map((u) => [u.id, u.email]))

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-1">
        {isLoading ? (
          <li className="text-sm text-muted-foreground">Carregando vínculos...</li>
        ) : (links ?? []).length === 0 ? (
          <li className="text-sm text-muted-foreground">Nenhum vínculo para este tenant</li>
        ) : (
          (links ?? []).map((link) => (
            <li
              key={link.user_id}
              className="flex items-center justify-between border-b border-border py-2.5 last:border-0"
            >
              <span className="font-mono text-sm text-foreground">
                {emailById.get(link.user_id) ?? link.user_id}
              </span>
              <span className="flex items-center gap-3">
                <Badge variant="outline">{link.role}</Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeMutation.mutate(link.user_id)}
                >
                  Remover
                </Button>
              </span>
            </li>
          ))
        )}
      </ul>
      <div className="flex items-end gap-2">
        <div className="flex flex-1 flex-col gap-2">
          <Label>Usuário</Label>
          <Select value={userId} onValueChange={setUserId}>
            <SelectTrigger>
              <SelectValue placeholder="selecione" />
            </SelectTrigger>
            <SelectContent>
              {(users ?? []).map((u) => (
                <SelectItem key={u.id} value={u.id} className="font-mono">
                  {u.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-2">
          <Label>Papel</Label>
          <Select value={role} onValueChange={(v) => setRole(v as TenantLink["role"])}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={() => addMutation.mutate()} disabled={!userId || addMutation.isPending}>
          Vincular
        </Button>
      </div>
    </div>
  )
}
