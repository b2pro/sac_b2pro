import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ImageOff, Loader2, Package, Plus } from "lucide-react"
import { useState, type ChangeEvent, type FormEvent } from "react"
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
import { deleteProductPhoto, uploadProductPhoto } from "@/lib/attachments"
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
import { kindOf, MAX_UPLOAD_BYTES } from "@/lib/media"

const PHOTO_ACCEPT = "image/jpeg,image/png,image/webp"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

/** Validacao no client antes de pedir a intencao de upload: a foto de produto
 *  so aceita imagem, ao contrario dos anexos de ticket (que tambem aceitam
 *  PDF e video). Recusar aqui evita uma chamada ao servidor so para levar um
 *  400 de volta. */
function validarFotoProduto(arquivo: File): string | null {
  if (kindOf(arquivo) !== "imagem") return "a foto precisa ser uma imagem (JPEG, PNG ou WEBP)"
  if (arquivo.size > MAX_UPLOAD_BYTES) return "foto acima de 50 MB"
  return null
}

function ProductThumb({ product }: { product: Product }) {
  if (product.photo_url) {
    return (
      <img
        src={product.photo_url}
        alt=""
        className="size-8 rounded border border-border object-cover"
        loading="lazy"
      />
    )
  }
  return (
    <div className="flex size-8 items-center justify-center rounded border border-border bg-muted/40">
      <ImageOff size={16} strokeWidth={1.5} className="text-muted-foreground" />
    </div>
  )
}

export default function ProdutosPage() {
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)
  const [photoProgress, setPhotoProgress] = useState<number | null>(null)

  const role = session?.role ?? null
  const podeCriar = canCreateCadastros(role)
  const podeGerenciar = canManageCadastros(role)
  const columnCount = podeGerenciar ? 6 : 5

  const { data, isLoading } = useQuery({
    queryKey: ["produtos", search, page],
    queryFn: () => listProducts({ search: search || undefined, page, perPage: 20 }),
    // A foto e um objeto que existe no storage assim que confirmado, mas o
    // preview (o que aparece como photo_url) e gerado por um worker
    // assincrono — chega pronto pouco depois. So repetimos o fetch enquanto
    // existir alguma foto sem preview ainda; nada de polling constante.
    refetchInterval: (query) => {
      const produtos = query.state.data?.items
      return produtos?.some((p) => p.photo_key && !p.photo_url) ? 4000 : false
    },
  })

  // A edicao referencia o item selecionado na tabela; ao refazer a listagem
  // (por causa do polling de preview acima ou de qualquer invalidacao), este
  // valor traz o estado mais atual da foto para o dialog aberto, sem precisar
  // de um effect dedicado so para sincronizar isso.
  const editingLive: Product | null = editing
    ? (data?.items.find((p) => p.id === editing.id) ?? editing)
    : null

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

  const photoMutation = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) =>
      uploadProductPhoto(id, file, (percent) => setPhotoProgress(percent)),
    onSuccess: () => {
      setPhotoProgress(null)
      invalidate()
      toast.success("Foto enviada")
    },
    onError: (error) => {
      setPhotoProgress(null)
      toast.error(errorMessage(error))
    },
  })

  const deletePhotoMutation = useMutation({
    mutationFn: (id: string) => deleteProductPhoto(id),
    onSuccess: () => {
      invalidate()
      toast.success("Foto removida")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onPhotoSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ""
    if (!file || !editing) return
    const erro = validarFotoProduto(file)
    if (erro) {
      toast.error(erro)
      return
    }
    setPhotoProgress(0)
    photoMutation.mutate({ id: editing.id, file })
  }

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
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="foto-criar">Foto</Label>
                    <Input id="foto-criar" type="file" accept={PHOTO_ACCEPT} disabled />
                    <p className="text-xs text-muted-foreground">
                      Salve o produto para enviar a foto.
                    </p>
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
              <TableHead className="w-12">Foto</TableHead>
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
                  <TableCell>
                    <ProductThumb product={item} />
                  </TableCell>
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
          {editingLive && (
            <form onSubmit={onEdit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-name">Nome</Label>
                <Input id="edit-name" name="name" defaultValue={editingLive.name} required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-sku">SKU</Label>
                <Input
                  id="edit-sku"
                  name="sku"
                  defaultValue={editingLive.sku}
                  required
                  className="font-mono"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-segment">Segmento</Label>
                <Input
                  id="edit-segment"
                  name="segment"
                  defaultValue={editingLive.segment ?? ""}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-description">Descricao</Label>
                <Input
                  id="edit-description"
                  name="description"
                  defaultValue={editingLive.description ?? ""}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-foto">Foto</Label>
                <div className="flex items-center gap-3">
                  {editingLive.photo_url ? (
                    <img
                      src={editingLive.photo_url}
                      alt=""
                      className="size-16 shrink-0 rounded border border-border object-cover"
                    />
                  ) : editingLive.photo_key ? (
                    <div className="flex size-16 shrink-0 items-center justify-center rounded border border-border bg-muted/40">
                      <Loader2
                        size={16}
                        strokeWidth={1.5}
                        className="animate-spin text-muted-foreground"
                      />
                    </div>
                  ) : (
                    <div className="flex size-16 shrink-0 items-center justify-center rounded border border-border bg-muted/40">
                      <ImageOff size={16} strokeWidth={1.5} className="text-muted-foreground" />
                    </div>
                  )}
                  <div className="flex flex-1 flex-col gap-2">
                    <Input
                      id="edit-foto"
                      type="file"
                      accept={PHOTO_ACCEPT}
                      onChange={onPhotoSelected}
                      disabled={photoMutation.isPending}
                    />
                    {photoMutation.isPending ? (
                      <p className="text-xs text-muted-foreground">
                        Enviando... {photoProgress ?? 0}%
                      </p>
                    ) : editingLive.photo_key && !editingLive.photo_url ? (
                      <p className="text-xs text-muted-foreground">Gerando preview...</p>
                    ) : null}
                    {editingLive.photo_key && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={deletePhotoMutation.isPending}
                        onClick={() => deletePhotoMutation.mutate(editingLive.id)}
                      >
                        Remover foto
                      </Button>
                    )}
                  </div>
                </div>
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
