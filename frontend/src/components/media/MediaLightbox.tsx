import { ArrowUpRight, FileText, Loader2, X } from "lucide-react"
import { Dialog as DialogPrimitive } from "radix-ui"
import { Link } from "react-router-dom"

import { formatBytes, formatShortDateTime } from "@/lib/format"

export type LightboxItem = {
  kind: "imagem" | "pdf" | "video"
  filename: string
  contentType: string
  sizeBytes: number
  createdAt: string
  /** presigned da variante a exibir; null enquanto a URL ainda esta sendo buscada. */
  url: string | null
  ticketId?: string
  ticketNumber?: number
}

const KIND_LABELS: Record<LightboxItem["kind"], string> = {
  imagem: "Imagem",
  pdf: "PDF",
  video: "Vídeo",
}

function MediaPane({ item }: { item: LightboxItem }) {
  if (!item.url) {
    return <Loader2 size={28} strokeWidth={1.5} className="animate-spin text-muted-foreground" />
  }
  if (item.kind === "imagem") {
    return <img src={item.url} alt={item.filename} className="size-full object-contain" />
  }
  if (item.kind === "video") {
    return (
      <video src={item.url} controls className="size-full object-contain">
        <track kind="captions" />
      </video>
    )
  }
  return (
    <div className="flex flex-col items-center gap-3 text-muted-foreground">
      <FileText size={44} strokeWidth={1.5} />
      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-[13px] font-semibold text-primary-text hover:underline"
      >
        Abrir PDF em nova aba
      </a>
    </div>
  )
}

/** Visualizador de anexo compartilhado entre a galeria de midias e o detalhe do
 *  ticket: imagem ampliada, player de video ou link de PDF, mais um painel
 *  lateral com metadados. `showTicketLink=false` no detalhe do ticket, onde o
 *  usuario ja esta na tela do ticket em questao. */
export function MediaLightbox({
  item,
  onClose,
  showTicketLink = false,
}: {
  item: LightboxItem | null
  onClose: () => void
  showTicketLink?: boolean
}) {
  return (
    <DialogPrimitive.Root open={item != null} onOpenChange={(open) => !open && onClose()}>
      <DialogPrimitive.Portal>
        {/* Escurecedor preto translucido, e nao um token do tema: --accent-foreground
            inverte no tema escuro e a cortina virava um veu quase branco por cima
            do app. Mesma familia do overlay do Dialog (bg-black/50), so mais densa
            porque aqui o assunto e a midia. */}
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content className="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-4rem)] w-[calc(100%-4rem)] max-w-[920px] -translate-x-1/2 -translate-y-1/2 flex-wrap overflow-hidden rounded-md border border-border bg-card outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95">
          {item && (
            <>
              <DialogPrimitive.Title className="sr-only">{item.filename}</DialogPrimitive.Title>
              <DialogPrimitive.Description className="sr-only">
                Visualizacao do anexo com detalhes e link do ticket
              </DialogPrimitive.Description>

              <div className="flex min-h-[380px] min-w-0 flex-[1_1_420px] items-center justify-center bg-muted">
                <MediaPane item={item} />
              </div>

              <div className="flex max-w-[300px] flex-[1_1_260px] flex-col gap-3.5 border-l border-border p-5">
                <div className="flex items-start justify-between gap-2.5">
                  <h3 className="m-0 text-sm font-semibold break-all text-accent-foreground">
                    {item.filename}
                  </h3>
                  <button
                    type="button"
                    onClick={onClose}
                    title="Fechar"
                    aria-label="Fechar"
                    className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    <X size={16} strokeWidth={1.5} />
                  </button>
                </div>

                <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-3.5 gap-y-1.5 text-[12.5px]">
                  <dt className="text-muted-foreground">Tipo</dt>
                  <dd className="m-0">{KIND_LABELS[item.kind]}</dd>
                  <dt className="text-muted-foreground">Tamanho</dt>
                  <dd className="m-0 font-mono">{formatBytes(item.sizeBytes)}</dd>
                  <dt className="text-muted-foreground">Enviado em</dt>
                  <dd className="m-0 font-mono">{formatShortDateTime(item.createdAt)}</dd>
                  <dt className="text-muted-foreground">Formato</dt>
                  <dd className="m-0 font-mono">{item.contentType}</dd>
                </dl>

                {showTicketLink && item.ticketId && item.ticketNumber !== undefined && (
                  <Link
                    to={`/tickets/${item.ticketId}`}
                    className="mt-auto inline-flex items-center gap-1.5 text-[13px] font-semibold text-primary-text hover:underline"
                  >
                    Ver ticket <span className="font-mono">#{item.ticketNumber}</span>
                    <ArrowUpRight size={14} strokeWidth={1.5} />
                  </Link>
                )}
              </div>
            </>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
