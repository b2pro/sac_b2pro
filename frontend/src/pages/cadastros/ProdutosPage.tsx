import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Package, Plus } from "lucide-react"
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
  createProduct,
  listProducts,
  setProductActive,
  updateProduct,
  type Product,
} from "@/lib/cadastros"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

export default function ProdutosPage() {
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)

  const role = session?.role ?? null
  const podeCriar = canCreateCadastros(role)
  const podeGerenciar = canManageCadastros(role)
  const columnCount = podeGerenciar ? 5 : 4

  const { data, isLoading } = useQuery({
    queryKey: ["produtos", search, page],
    queryFn: () => listProducts({ search: search || undefined, page, perPage: 20 }),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["produtos"] })

  const createMutation = useMutation({
    mutationFn: (input: { name: string; sku: string; segment?: string; description?: string }) =>
      createProduct({
        name: input.name,
        sku: input.sku,
        segment: input.segment || null,
        description: input.description || null,
      }),
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      toast.success("Produto criado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      name,
      sku,
      segment,
      description,
    }: {
      id: string
      name: string
      sku: string
      segment?: string
      description?: string
    }) =>
      updateProduct(id, {
        name,
        sku,
        segment: segment || null,
        description: description || null,
      }),
    onSuccess: () => {
      invalidate()
      setEditing(null)
      toast.success("Produto atualizado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const activeMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => setProductActive(id, active),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onSearchChange(value: string) {
    setSearch(value)
    setPage(1)
  }

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    createMutation.mutate({
      name: String(form.get("name")),
      sku: String(form.get("sku")),
      segment: String(form.get("segment")) || undefined,
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
      sku: String(form.get("sku")),
      segment: String(form.get("segment")) || undefined,
      description: String(form.get("description")) || undefined,
    })
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Package size={20} strokeWidth={1.5} className="text-muted-foreground" />
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Produtos</h1>
        </div>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Buscar por nome ou SKU"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
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
                  <DialogTitle>Novo produto</DialogTitle>
                </DialogHeader>
                <form onSubmit={onCreate} className="flex flex-col gap-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="name">Nome</Label>
                    <Input id="name" name="name" required />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="sku">SKU</Label>
                    <Input id="sku" name="sku" required className="font-mono" />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="segment">Segmento</Label>
                    <Input id="segment" name="segment" />
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
              <TableHead>SKU</TableHead>
              <TableHead>Segmento</TableHead>
              <TableHead>Status</TableHead>
              {podeGerenciar && <TableHead className="w-40 text-right">Acoes</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={columnCount} className="text-center text-muted-foreground">
                  Carregando produtos...
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
                  <TableCell className="font-mono">{item.sku}</TableCell>
                  <TableCell className="text-muted-foreground">{item.segment ?? ""}</TableCell>
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

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {data ? `${data.total} produto(s)` : ""}
        </span>
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

      <Dialog open={editing != null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar produto</DialogTitle>
          </DialogHeader>
          {editing && (
            <form onSubmit={onEdit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-name">Nome</Label>
                <Input id="edit-name" name="name" defaultValue={editing.name} required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-sku">SKU</Label>
                <Input
                  id="edit-sku"
                  name="sku"
                  defaultValue={editing.sku}
                  required
                  className="font-mono"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-segment">Segmento</Label>
                <Input id="edit-segment" name="segment" defaultValue={editing.segment ?? ""} />
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
