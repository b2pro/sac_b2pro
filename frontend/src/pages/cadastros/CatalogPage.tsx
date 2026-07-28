import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ClipboardCheck, Plus, Store, Tags, Wrench } from "lucide-react"
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
  createCatalogItem,
  listCatalog,
  setCatalogItemActive,
  updateCatalogItem,
  type CatalogItem,
  type CatalogPath,
} from "@/lib/cadastros"

const PATH_ICON: Record<CatalogPath, typeof Tags> = {
  marcas: Tags,
  defeitos: Wrench,
  solucoes: ClipboardCheck,
  canais: Store,
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

export default function CatalogPage({ title, path }: { title: string; path: CatalogPath }) {
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<CatalogItem | null>(null)

  const role = session?.role ?? null
  const podeCriar = canCreateCadastros(role)
  const podeGerenciar = canManageCadastros(role)
  const columnCount = podeGerenciar ? 4 : 3
  const Icon = PATH_ICON[path]

  const { data: items, isLoading } = useQuery({
    queryKey: ["catalog", path, search],
    queryFn: () => listCatalog(path, { search: search || undefined }),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["catalog", path] })

  const createMutation = useMutation({
    mutationFn: (input: { name: string; description?: string }) =>
      createCatalogItem(path, input),
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      toast.success("Registro criado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, name, description }: { id: string; name: string; description?: string }) =>
      updateCatalogItem(path, id, { name, description }),
    onSuccess: () => {
      invalidate()
      setEditing(null)
      toast.success("Registro atualizado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const activeMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      setCatalogItemActive(path, id, active),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    createMutation.mutate({
      name: String(form.get("name")),
      description: String(form.get("description")) || undefined,
    })
  }

  function onEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing) return
    const form = new FormData(event.currentTarget)
    updateMutation.mutate({
      id: editing.id,
      name: String(form.get("name")),
      description: String(form.get("description")) || undefined,
    })
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Icon size={20} strokeWidth={1.5} className="text-muted-foreground" />
          <h1 className="text-lg font-semibold tracking-tight text-foreground">{title}</h1>
        </div>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Buscar por nome"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-64"
          />
          {podeCriar && (
            <Dialog open={createOpen} onOpenChange={setCreateOpen}>
              <DialogTrigger asChild>
                <Button>
                  <Plus size={20} strokeWidth={1.5} />
                  Novo
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Novo registro</DialogTitle>
                </DialogHeader>
                <form onSubmit={onCreate} className="flex flex-col gap-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="name">Nome</Label>
                    <Input id="name" name="name" required />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="description">Descricao</Label>
                    <Input id="description" name="description" />
                  </div>
                  <Button type="submit" disabled={createMutation.isPending} className="mt-1">
                    Criar
                  </Button>
                </form>
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
              <TableHead>Descricao</TableHead>
              <TableHead>Status</TableHead>
              {podeGerenciar && <TableHead className="w-40 text-right">Acoes</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={columnCount} className="text-center text-muted-foreground">
                  Carregando {title.toLowerCase()}...
                </TableCell>
              </TableRow>
            ) : (items ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={columnCount} className="text-center text-muted-foreground">
                  Nenhum registro para este filtro
                </TableCell>
              </TableRow>
            ) : (
              (items ?? []).map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {item.description ?? ""}
                  </TableCell>
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
                        <Button variant="ghost" size="sm" onClick={() => setEditing(item)}>
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

      <Dialog open={editing != null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar registro</DialogTitle>
          </DialogHeader>
          {editing && (
            <form onSubmit={onEdit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-name">Nome</Label>
                <Input id="edit-name" name="name" defaultValue={editing.name} required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-description">Descricao</Label>
                <Input
                  id="edit-description"
                  name="description"
                  defaultValue={editing.description ?? ""}
                />
              </div>
              <Button type="submit" disabled={updateMutation.isPending} className="mt-1">
                Salvar
              </Button>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
