import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Building2, MoreHorizontal, Plus, SlidersHorizontal } from "lucide-react"
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
import {
  KNOWN_MODULES,
  createTenant,
  listTenants,
  setTenantModules,
  setTenantStatus,
  type Tenant,
  type TenantStatus,
} from "@/lib/platform"

const STATUSES: TenantStatus[] = ["ativa", "teste", "suspensa", "inativa"]

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

export default function TenantsPage() {
  const queryClient = useQueryClient()
  const { data: tenants, isLoading } = useQuery({ queryKey: ["tenants"], queryFn: listTenants })
  const [createOpen, setCreateOpen] = useState(false)
  const [modulesTenant, setModulesTenant] = useState<Tenant | null>(null)

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

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    createMutation.mutate({
      slug: String(form.get("slug")),
      name: String(form.get("name")),
    })
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
            <form onSubmit={onCreate} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="slug">Slug</Label>
                <Input id="slug" name="slug" className="font-mono" required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="name">Nome</Label>
                <Input id="name" name="name" required />
              </div>
              <Button type="submit" disabled={createMutation.isPending} className="mt-1">
                Criar
              </Button>
            </form>
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
              <TableHead>Modulos</TableHead>
              <TableHead className="w-16 text-right">Acoes</TableHead>
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
                  Nenhum tenant cadastrado.
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
                          <span className="sr-only">Acoes de {tenant.name}</span>
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
                          Modulos
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
            <DialogTitle>Modulos de {modulesTenant?.name}</DialogTitle>
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
