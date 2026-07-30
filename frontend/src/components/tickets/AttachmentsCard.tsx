import { useQuery } from "@tanstack/react-query"
import { FileText, ImageOff, Loader2, MoreVertical, Upload, Video, X } from "lucide-react"
import { useRef, useState, type DragEvent } from "react"
import { toast } from "sonner"

import { MediaLightbox, type LightboxItem } from "@/components/media/MediaLightbox"
import { useUploadQueue, validarArquivo } from "@/components/tickets/AttachmentsCard.upload"
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
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ApiError } from "@/lib/api"
import { attachmentUrl, deleteAttachment, listAttachments, type Attachment } from "@/lib/attachments"
import { useAuth } from "@/lib/auth"
import { ACCEPTED_MIME } from "@/lib/media"
import { canComment, canDecide, isClosed, type TicketStatus } from "@/lib/tickets"
import { cn } from "@/lib/utils"

const MAX_ATTACHMENTS = 10

const POLL_INTERVAL_MS = 4000
// Mesmo orcamento por item usado na foto de produto (POLL_BUDGET_MS em
// ProdutosPage): cobre o turnaround normal (segundos) e a janela de retry do
// worker de preview — backoff de 1+2+4+8 min entre as 5 tentativas antes de o
// job ser dado por esgotado (MAX_PREVIEW_ATTEMPTS=5 em sac.domain.attachments),
// cerca de 15 min no pior caso. Com o worker de pe o proprio status "falhou"
// encerra o polling; o orcamento e o que impede o repoll infinito a cada 4s
// (re-assinando uma URL por anexo em cada resposta) quando o worker esta parado
// e o "pendente" nunca resolve.
const POLL_BUDGET_MS = 20 * 60 * 1000

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function AttachmentPreview({
  attachment,
  previewEsgotado,
}: {
  attachment: Attachment
  previewEsgotado: boolean
}) {
  if (attachment.preview_status === "pronto" && attachment.preview_url) {
    return (
      <img
        src={attachment.preview_url}
        alt=""
        className="size-full object-cover"
        loading="lazy"
      />
    )
  }
  // Pendente alem do orcamento de espera: o polling parou, entao o spinner
  // giraria para sempre sem nenhuma chance de virar preview nesta visita.
  if (attachment.preview_status === "pendente" && previewEsgotado) {
    return (
      <span className="flex flex-col items-center gap-1 text-xs text-muted-foreground">
        <ImageOff size={20} strokeWidth={1.5} />
        preview indisponivel
      </span>
    )
  }
  if (attachment.preview_status === "pendente") {
    return (
      <span className="flex flex-col items-center gap-1 text-xs text-muted-foreground">
        <Loader2 size={20} strokeWidth={1.5} className="animate-spin" />
        gerando preview
      </span>
    )
  }
  if (attachment.preview_status === "falhou") {
    return (
      <span className="flex flex-col items-center gap-1 text-xs text-muted-foreground">
        <ImageOff size={20} strokeWidth={1.5} />
        preview falhou
      </span>
    )
  }
  if (attachment.kind === "video") {
    return <Video size={20} strokeWidth={1.5} className="text-muted-foreground" />
  }
  return <FileText size={20} strokeWidth={1.5} className="text-muted-foreground" />
}

function AttachmentTile({
  attachment,
  podeExcluir,
  previewEsgotado,
  onOpen,
  onDownload,
  onRemove,
}: {
  attachment: Attachment
  podeExcluir: boolean
  previewEsgotado: boolean
  onOpen: () => void
  onDownload: () => void
  onRemove: () => void
}) {
  return (
    <div className="flex flex-col overflow-hidden rounded-md border border-border">
      <button
        type="button"
        onClick={onOpen}
        title={attachment.filename}
        className="flex aspect-square w-full items-center justify-center bg-muted/40"
      >
        <AttachmentPreview attachment={attachment} previewEsgotado={previewEsgotado} />
      </button>
      <div className="flex items-center gap-1 border-t border-border px-2 py-1.5">
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-foreground" title={attachment.filename}>
            {attachment.filename}
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            {formatSize(attachment.size_bytes)} · {attachment.author_name ?? "-"}
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Acoes do anexo ${attachment.filename}`}
            >
              <MoreVertical size={16} strokeWidth={1.5} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onDownload}>Baixar original</DropdownMenuItem>
            {podeExcluir && (
              <DropdownMenuItem variant="destructive" onClick={onRemove}>
                Remover
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}

export function AttachmentsCard({
  ticketId,
  status,
  onChanged,
}: {
  ticketId: string
  status: TicketStatus
  onChanged: () => void
}) {
  const { session } = useAuth()
  const role = session?.role ?? null
  const userId = session?.user.id ?? null
  const podeAnexar = canComment(role) && !isClosed(status)

  const [arrastando, setArrastando] = useState(false)
  const [removendo, setRemovendo] = useState<Attachment | null>(null)
  const [excluindo, setExcluindo] = useState(false)
  const [lightboxItem, setLightboxItem] = useState<LightboxItem | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  // Anexos cujo preview ficou pendente alem do orcamento de polling abaixo.
  const [previewEsgotado, setPreviewEsgotado] = useState<Set<string>>(() => new Set())
  // Quando cada anexo pendente foi visto pendente pela 1a vez, por id (nao um
  // relogio global): mesma escolha feita para a foto de produto, para que um
  // anexo novo nunca herde o relogio vencido de outro.
  const pollStartedAtRef = useRef<Map<string, number>>(new Map())

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["anexos", ticketId],
    queryFn: () => listAttachments(ticketId),
    // O preview de imagem e gerado por um worker assincrono: um anexo recem
    // enviado chega "pendente" e vira "pronto" pouco depois. So mantemos o
    // refetch periodico enquanto houver algum preview pendente — nada de
    // polling constante quando a lista ja estabilizou — e so ate o orcamento de
    // tempo acima, por anexo: com o worker parado o "pendente" nunca resolve e
    // sem o orcamento a pagina repollaria de 4 em 4 segundos para sempre.
    refetchInterval: (query) => {
      const pendentes = (query.state.data ?? []).filter((a) => a.preview_status === "pendente")
      const idsPendentes = new Set(pendentes.map((a) => a.id))

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
        setPreviewEsgotado((atual) => {
          if (esgotadosAgora.every((id) => atual.has(id))) return atual
          const proximo = new Set(atual)
          for (const id of esgotadosAgora) proximo.add(id)
          return proximo
        })
      }
      return algumDentroDoOrcamento ? POLL_INTERVAL_MS : false
    },
  })

  const { itens, enfileirar, cancelar, tentarNovamente, dispensar } = useUploadQueue(
    ticketId,
    () => {
      void refetch()
      onChanged()
    },
  )

  const anexos = data ?? []
  const emUso = anexos.length + itens.length
  const cheio = emUso >= MAX_ATTACHMENTS

  /** Mesma regra que DeleteAttachmentUseCase aplica no servidor: autor do anexo
   *  OU quem tem DECIDIR_TICKET (admin e supervisor, ver canDecide). Derivada
   *  dos mesmos insumos — autor do anexo e papel/usuario da sessao — para que
   *  as duas nao divirjam e ninguem veja "Remover" so para levar um 403. */
  const podeRemover = (attachment: Attachment) =>
    podeAnexar && (attachment.author_user_id === userId || canDecide(role))

  function processarArquivos(lista: FileList | File[]) {
    const arquivos = Array.from(lista)
    if (arquivos.length === 0) return
    // Validar tipo/tamanho antes de cortar pelo limite de vagas: um arquivo
    // invalido no meio do lote nao pode "roubar" a vaga de um arquivo valido
    // que vinha depois dele.
    const validos: File[] = []
    for (const arquivo of arquivos) {
      const erro = validarArquivo(arquivo)
      if (erro) {
        toast.error(erro)
      } else {
        validos.push(arquivo)
      }
    }
    const espaco = Math.max(0, MAX_ATTACHMENTS - emUso)
    const aceitar = validos.slice(0, espaco)
    const excedentes = validos.length - aceitar.length
    enfileirar(aceitar)
    if (excedentes > 0) {
      toast.error(`Limite de ${MAX_ATTACHMENTS} anexos por ticket atingido`)
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setArrastando(false)
    if (cheio) return
    processarArquivos(event.dataTransfer.files)
  }

  // Abre o visualizador compartilhado em vez de uma aba nova: mostra os
  // metadados na hora (vindos do proprio anexo) e busca a URL assinada em
  // paralelo — imagem usa a variante "medio" (o servidor cai para o original
  // se nao houver preview), PDF e video usam sempre o original.
  async function onOpen(attachment: Attachment) {
    setLightboxItem({
      kind: attachment.kind,
      filename: attachment.filename,
      contentType: attachment.content_type,
      sizeBytes: attachment.size_bytes,
      createdAt: attachment.created_at ?? new Date().toISOString(),
      url: null,
    })
    try {
      const variant = attachment.kind === "imagem" ? "medio" : "original"
      const { url } = await attachmentUrl(ticketId, attachment.id, variant)
      setLightboxItem((current) =>
        current && current.filename === attachment.filename ? { ...current, url } : current,
      )
    } catch (error) {
      toast.error(errorMessage(error))
      setLightboxItem(null)
    }
  }

  async function onDownloadOriginal(attachment: Attachment) {
    try {
      const { url } = await attachmentUrl(ticketId, attachment.id, "original")
      window.open(url, "_blank", "noopener")
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function confirmarRemocao() {
    if (!removendo) return
    setExcluindo(true)
    try {
      await deleteAttachment(ticketId, removendo.id)
      toast.success("Anexo removido")
      setRemovendo(null)
      await refetch()
      onChanged()
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setExcluindo(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle>Anexos</CardTitle>
        <span className="text-xs text-muted-foreground">
          {anexos.length}/{MAX_ATTACHMENTS}
        </span>
      </CardHeader>
      <CardContent className="space-y-4">
        {podeAnexar && (
          <div
            onDragOver={(event) => {
              event.preventDefault()
              if (!cheio) setArrastando(true)
            }}
            onDragLeave={() => setArrastando(false)}
            onDrop={onDrop}
            onClick={() => !cheio && inputRef.current?.click()}
            role="button"
            tabIndex={cheio ? -1 : 0}
            aria-disabled={cheio}
            onKeyDown={(event) => {
              if (!cheio && (event.key === "Enter" || event.key === " ")) {
                event.preventDefault()
                inputRef.current?.click()
              }
            }}
            className={cn(
              "flex flex-col items-center justify-center gap-1 rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground transition-colors",
              cheio ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:border-foreground/40",
              arrastando && !cheio && "border-foreground bg-muted/40",
            )}
          >
            <Upload size={20} strokeWidth={1.5} />
            {cheio ? (
              <span>Limite de {MAX_ATTACHMENTS} anexos atingido</span>
            ) : (
              <span>Arraste arquivos aqui ou clique para selecionar</span>
            )}
            <span className="text-xs">Imagens, PDF ou video — ate 50 MB cada</span>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPTED_MIME.join(",")}
              className="hidden"
              onChange={(event) => {
                if (event.target.files) processarArquivos(event.target.files)
                event.target.value = ""
              }}
            />
          </div>
        )}

        {itens.length > 0 && (
          <ul className="space-y-2">
            {itens.map((item) => (
              <li
                key={item.id}
                className="flex items-center gap-3 rounded-md border border-border px-3 py-2 text-sm"
              >
                <span className="min-w-0 flex-1 truncate" title={item.nome}>
                  {item.nome}
                </span>
                {item.status === "erro" ? (
                  <>
                    <span className="text-xs text-destructive">{item.erro}</span>
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      onClick={() => tentarNovamente(item.id)}
                    >
                      Tentar de novo
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => dispensar(item.id)}
                      aria-label={`Descartar ${item.nome}`}
                    >
                      <X size={16} strokeWidth={1.5} />
                    </Button>
                  </>
                ) : (
                  <>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {item.status === "aguardando" ? "na fila" : `${item.percent}%`}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => cancelar(item.id)}
                      aria-label={`Cancelar envio de ${item.nome}`}
                    >
                      <X size={16} strokeWidth={1.5} />
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Carregando...</p>
        ) : anexos.length === 0 && itens.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum anexo neste ticket.</p>
        ) : anexos.length > 0 ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {anexos.map((attachment) => (
              <AttachmentTile
                key={attachment.id}
                attachment={attachment}
                podeExcluir={podeRemover(attachment)}
                previewEsgotado={previewEsgotado.has(attachment.id)}
                onOpen={() => onOpen(attachment)}
                onDownload={() => onDownloadOriginal(attachment)}
                onRemove={() => setRemovendo(attachment)}
              />
            ))}
          </div>
        ) : null}
      </CardContent>

      <MediaLightbox
        item={lightboxItem}
        onClose={() => setLightboxItem(null)}
        showTicketLink={false}
      />

      <Dialog open={removendo != null} onOpenChange={(open) => !open && setRemovendo(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remover anexo</DialogTitle>
            <DialogDescription>
              {removendo
                ? `Remover "${removendo.filename}"? O arquivo continua no armazenamento para fins de auditoria, mas deixa de aparecer neste ticket.`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setRemovendo(null)}>
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={excluindo}
              onClick={confirmarRemocao}
            >
              Remover
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
