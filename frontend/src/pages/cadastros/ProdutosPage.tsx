import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ImageOff, Loader2, Package, Plus } from "lucide-react"
import { useRef, useState, type ChangeEvent, type FormEvent } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field-error"
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
import { fieldErrorProps } from "@/lib/field-error"
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

const UPLOAD_CANCELADO = "upload cancelado"

const POLL_INTERVAL_MS = 4000
// Cobre o turnaround normal (segundos, na pratica) e a janela de retry do
// worker de preview: backoff de 1+2+4+8 min entre as 5 tentativas antes do
// job ser dado por esgotado (MAX_PREVIEW_ATTEMPTS=5 em
// sac.domain.attachments) — cerca de 15 min no pior caso. 20 min da uma
// folga sem manter o polling indefinidamente quando o worker desiste.
const POLL_BUDGET_MS = 20 * 60 * 1000

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

function CreateProductForm({
  onSubmit,
  submitting,
}: {
  onSubmit: (values: { name: string; sku: string; segment?: string; description?: string }) => void
  submitting: boolean
}) {
  const [nameError, setNameError] = useState<string | null>(null)
  const [skuError, setSkuError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const name = String(form.get("name")).trim()
    const sku = String(form.get("sku")).trim()

    const nextNameError = name ? null : "Informe o nome"
    const nextSkuError = sku ? null : "Informe o SKU"
    setNameError(nextNameError)
    setSkuError(nextSkuError)
    if (nextNameError || nextSkuError) return

    onSubmit({
      name,
      sku,
      segment: String(form.get("segment")).trim() || undefined,
      description: String(form.get("description")).trim() || undefined,
    })
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="name">Nome</Label>
        <Input id="name" name="name" required {...fieldErrorProps("name", nameError)} />
        <FieldError fieldId="name" message={nameError} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="sku">SKU</Label>
        <Input
          id="sku"
          name="sku"
          required
          className="font-mono"
          {...fieldErrorProps("sku", skuError)}
        />
        <FieldError fieldId="sku" message={skuError} />
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
        <p className="text-xs text-muted-foreground">Salve o produto para enviar a foto.</p>
      </div>
      <Button type="submit" disabled={submitting} className="mt-1">
        Criar
      </Button>
    </form>
  )
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
  const [editNameError, setEditNameError] = useState<string | null>(null)
  const [editSkuError, setEditSkuError] = useState<string | null>(null)
  const [confirmingPhotoDelete, setConfirmingPhotoDelete] = useState<Product | null>(null)
  const [photoProgress, setPhotoProgress] = useState<{ id: string; percent: number } | null>(null)
  // Produtos cuja foto ficou pendente de preview alem do orcamento de polling
  // abaixo — o worker de preview esgotou as tentativas (ou esta demorando
  // demais) e nao ha, nesta fase, um campo de status de falha no produto
  // (diferente do anexo de ticket, que tem preview_status). Sem isso o dialog
  // de edicao ficaria com o spinner girando para sempre.
  const [previewTimedOut, setPreviewTimedOut] = useState<Set<string>>(() => new Set())
  const photoAbortRef = useRef<AbortController | null>(null)
  // Quando cada produto pendente foi visto pendente pela 1a vez, por id — nao
  // um unico relogio global. Um relogio global tratado por "o conjunto de ids
  // pendentes mudou" parece razoavel, mas quebra justamente o caso que mais
  // importa: reenviar a foto de um produto cujo preview anterior ja estourou
  // o orcamento nao muda o conjunto de ids pendentes (o produto ja estava
  // pendente, continua pendente), entao o novo envio herdaria o relogio
  // vencido e seria marcado como "esgotado" antes mesmo de comecar. Por
  // produto, resetar e so limpar a entrada dele no mapa (feito em
  // onPhotoSelected).
  const pollStartedAtRef = useRef<Map<string, number>>(new Map())

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
    // existir alguma foto sem preview ainda, e so ate o orcamento de tempo
    // acima, por produto: sem isso, um produto cujo worker desistiu (job
    // marcado como esgotado) seria repolled a cada 4s para sempre, enquanto a
    // pagina ficasse aberta.
    refetchInterval: (query) => {
      const produtos = query.state.data?.items ?? []
      const pendentes = produtos.filter((p) => p.photo_key && !p.photo_url)
      const idsPendentes = new Set(pendentes.map((p) => p.id))

      // limpa do mapa quem nao esta mais pendente (preview chegou, foto foi
      // removida, ou saiu da pagina/busca atual)
      for (const id of pollStartedAtRef.current.keys()) {
        if (!idsPendentes.has(id)) pollStartedAtRef.current.delete(id)
      }

      if (idsPendentes.size === 0) return false

      const agora = Date.now()
      const esgotadosAgora: string[] = []
      let algumDentroDoOrcamento = false
      for (const id of idsPendentes) {
        const inicio = pollStartedAtRef.current.get(id)
        if (inicio === undefined) {
          pollStartedAtRef.current.set(id, agora)
          algumDentroDoOrcamento = true
        } else if (agora - inicio < POLL_BUDGET_MS) {
          algumDentroDoOrcamento = true
        } else {
          esgotadosAgora.push(id)
        }
      }
      if (esgotadosAgora.length > 0) {
        setPreviewTimedOut((atual) => {
          if (esgotadosAgora.every((id) => atual.has(id))) return atual
          const proximo = new Set(atual)
          for (const id of esgotadosAgora) proximo.add(id)
          return proximo
        })
      }
      return algumDentroDoOrcamento ? POLL_INTERVAL_MS : false
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
    mutationFn: ({ id, file, signal }: { id: string; file: File; signal: AbortSignal }) =>
      uploadProductPhoto(id, file, (percent) => setPhotoProgress({ id, percent }), signal),
    onSuccess: () => {
      setPhotoProgress(null)
      photoAbortRef.current = null
      invalidate()
      toast.success("Foto enviada")
    },
    onError: (error) => {
      setPhotoProgress(null)
      photoAbortRef.current = null
      // Cancelamento deliberado (dialog fechado durante o upload): ver
      // onOpenChange do dialog de edicao. Nao e uma falha para avisar o
      // usuario, e o esperado quando ele sai da tela antes de terminar.
      if (error instanceof Error && error.message === UPLOAD_CANCELADO) return
      toast.error(errorMessage(error))
    },
  })

  const deletePhotoMutation = useMutation({
    mutationFn: (id: string) => deleteProductPhoto(id),
    onSuccess: (_data, id) => {
      // sem foto nao ha preview para esperar: limpa a marca de "preview
      // indisponivel" para que um envio futuro comece com o estado limpo.
      pollStartedAtRef.current.delete(id)
      setPreviewTimedOut((atual) => {
        if (!atual.has(id)) return atual
        const proximo = new Set(atual)
        proximo.delete(id)
        return proximo
      })
      invalidate()
      setConfirmingPhotoDelete(null)
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
    // Reenviar a foto de um produto cujo preview anterior tinha estourado o
    // orcamento de espera precisa comecar do zero: sem isso, o novo envio
    // herdaria o relogio vencido e o dialog mostraria "preview indisponivel"
    // antes mesmo do worker tentar de novo.
    pollStartedAtRef.current.delete(editing.id)
    setPreviewTimedOut((atual) => {
      if (!atual.has(editing.id)) return atual
      const proximo = new Set(atual)
      proximo.delete(editing.id)
      return proximo
    })

    const controller = new AbortController()
    photoAbortRef.current = controller
    setPhotoProgress({ id: editing.id, percent: 0 })
    photoMutation.mutate({ id: editing.id, file, signal: controller.signal })
  }

  function onConfirmarRemocaoFoto() {
    if (!confirmingPhotoDelete) return
    deletePhotoMutation.mutate(confirmingPhotoDelete.id)
  }

  /** Fecha o dialog de edicao. Um upload em andamento e abortado em vez de
   *  seguir "solto" em segundo plano: assim que o dialog fecha, nao ha mais
   *  nenhuma tela mostrando o progresso daquele envio, e deixa-lo terminar
   *  sozinho arriscaria exatamente a confusao de atribuicao entre produtos
   *  que motivou isolar esse estado por id (photoProgress, abaixo). */
  function onEditDialogOpenChange(open: boolean) {
    if (open) return
    if (photoMutation.isPending) photoAbortRef.current?.abort()
    setConfirmingPhotoDelete(null)
    setEditing(null)
  }

  function openEdit(product: Product) {
    setEditNameError(null)
    setEditSkuError(null)
    setEditing(product)
  }

  function onSearchChange(value: string) {
    setSearch(value)
    setPage(1)
  }

  function onCreate(values: { name: string; sku: string; segment?: string; description?: string }) {
    createMutation.mutate(values)
  }

  function onEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing) return
    const form = new FormData(event.currentTarget)
    const name = String(form.get("name")).trim()
    const sku = String(form.get("sku")).trim()

    const nextNameError = name ? null : "Informe o nome"
    const nextSkuError = sku ? null : "Informe o SKU"
    setEditNameError(nextNameError)
    setEditSkuError(nextSkuError)
    if (nextNameError || nextSkuError) return

    updateMutation.mutate({
      id: editing.id,
      name,
      sku,
      segment: String(form.get("segment")).trim() || undefined,
      description: String(form.get("description")).trim() || undefined,
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
                <CreateProductForm onSubmit={onCreate} submitting={createMutation.isPending} />
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
                        <Button variant="ghost" size="sm" onClick={() => openEdit(item)}>
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

      <Dialog open={editing != null} onOpenChange={onEditDialogOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar produto</DialogTitle>
          </DialogHeader>
          {editingLive && (
            <form onSubmit={onEdit} noValidate className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-name">Nome</Label>
                <Input
                  id="edit-name"
                  name="name"
                  defaultValue={editingLive.name}
                  required
                  {...fieldErrorProps("edit-name", editNameError)}
                />
                <FieldError fieldId="edit-name" message={editNameError} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-sku">SKU</Label>
                <Input
                  id="edit-sku"
                  name="sku"
                  defaultValue={editingLive.sku}
                  required
                  className="font-mono"
                  {...fieldErrorProps("edit-sku", editSkuError)}
                />
                <FieldError fieldId="edit-sku" message={editSkuError} />
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
                {(() => {
                  // photoMutation/deletePhotoMutation sao instancias unicas da
                  // pagina (um dialog por vez, mas o dialog pode fechar antes
                  // de a mutacao anterior terminar); .variables identifica de
                  // qual produto e o upload/exclusao em andamento, pra este
                  // dialog nunca mostrar o progresso de outro produto.
                  const enviandoEste =
                    photoMutation.isPending && photoProgress?.id === editingLive.id
                  const removendoEsta =
                    deletePhotoMutation.isPending &&
                    deletePhotoMutation.variables === editingLive.id
                  const semPreviewAinda = editingLive.photo_key && !editingLive.photo_url
                  const previewEmpacou = previewTimedOut.has(editingLive.id)
                  return (
                    <div className="flex items-center gap-3">
                      {editingLive.photo_url ? (
                        <img
                          src={editingLive.photo_url}
                          alt=""
                          className="size-16 shrink-0 rounded border border-border object-cover"
                        />
                      ) : semPreviewAinda && !previewEmpacou ? (
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
                          disabled={enviandoEste}
                        />
                        {enviandoEste ? (
                          <p className="text-xs text-muted-foreground">
                            Enviando... {photoProgress?.percent ?? 0}%
                          </p>
                        ) : semPreviewAinda ? (
                          <p className="text-xs text-muted-foreground">
                            {previewEmpacou ? "Preview indisponivel." : "Gerando preview..."}
                          </p>
                        ) : null}
                        {editingLive.photo_key && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={removendoEsta}
                            onClick={() => setConfirmingPhotoDelete(editingLive)}
                          >
                            Remover foto
                          </Button>
                        )}
                      </div>
                    </div>
                  )
                })()}
              </div>
              <Button type="submit" disabled={updateMutation.isPending} className="mt-1">
                Salvar
              </Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={confirmingPhotoDelete != null}
        onOpenChange={(open) => !open && setConfirmingPhotoDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remover foto</DialogTitle>
            <DialogDescription>
              {confirmingPhotoDelete
                ? `Remover a foto de "${confirmingPhotoDelete.name}"? O arquivo continua no armazenamento para fins de auditoria, mas deixa de aparecer no produto.`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmingPhotoDelete(null)}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={deletePhotoMutation.isPending}
              onClick={onConfirmarRemocaoFoto}
            >
              Remover
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
