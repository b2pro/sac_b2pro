import { useQuery } from "@tanstack/react-query"
import { FileText, ImageOff, Loader2, MoreVertical, Upload, Video, X } from "lucide-react"
import { useRef, useState, type DragEvent } from "react"
import { toast } from "sonner"

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
import { canComment, isClosed, type TicketStatus } from "@/lib/tickets"
import { cn } from "@/lib/utils"

const MAX_ATTACHMENTS = 10

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function AttachmentPreview({ attachment }: { attachment: Attachment }) {
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
  onOpen,
  onDownload,
  onRemove,
}: {
  attachment: Attachment
  podeExcluir: boolean
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
        <AttachmentPreview attachment={attachment} />
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
              aria-label={`Mais acoes de ${attachment.filename}`}
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
  const podeAnexar = canComment(role) && !isClosed(status)

  const [arrastando, setArrastando] = useState(false)
  const [removendo, setRemovendo] = useState<Attachment | null>(null)
  const [excluindo, setExcluindo] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["anexos", ticketId],
    queryFn: () => listAttachments(ticketId),
    // O preview de imagem e gerado por um worker assincrono: um anexo recem
    // enviado chega "pendente" e vira "pronto" pouco depois. So mantemos o
    // refetch periodico enquanto houver algum preview pendente — nada de
    // polling constante quando a lista ja estabilizou.
    refetchInterval: (query) => {
      const anexos = query.state.data
      return anexos?.some((a) => a.preview_status === "pendente") ? 4000 : false
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

  async function onOpen(attachment: Attachment) {
    try {
      const { url } = await attachmentUrl(ticketId, attachment.id, "medio")
      window.open(url, "_blank", "noopener")
    } catch (error) {
      toast.error(errorMessage(error))
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
                podeExcluir={podeAnexar}
                onOpen={() => onOpen(attachment)}
                onDownload={() => onDownloadOriginal(attachment)}
                onRemove={() => setRemovendo(attachment)}
              />
            ))}
          </div>
        ) : null}
      </CardContent>

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
