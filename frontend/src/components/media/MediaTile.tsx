import { FileText, Image, Play, Video } from "lucide-react"

import { formatShortDateTime } from "@/lib/format"
import type { MediaItem } from "@/lib/reporting"

const KIND_ICONS = { imagem: Image, pdf: FileText, video: Video } as const

function fileExtension(filename: string): string {
  const dot = filename.lastIndexOf(".")
  return dot > 0 ? filename.slice(dot + 1).toUpperCase() : ""
}

/** Tile quadrado da galeria de midias. Sem preview, mostra um icone por tipo e
 *  a extensao do arquivo em tom neutro — nao pode parecer erro (nao e
 *  "preview falhou", e so um tipo sem thumbnail gerado, como PDF sempre e). */
export function MediaTile({
  item,
  onOpen,
}: {
  item: MediaItem
  onOpen: (item: MediaItem) => void
}) {
  const Icon = KIND_ICONS[item.kind]
  const showChip = item.preview_url !== null && item.kind !== "pdf"

  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      title={item.filename}
      aria-label={`Abrir anexo ${item.filename} do ticket #${item.ticket_number}`}
      className="w-full rounded-md text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      <div className="relative flex aspect-square items-center justify-center overflow-hidden rounded-md border border-border bg-muted hover:border-foreground">
        {item.preview_url ? (
          <img
            src={item.preview_url}
            alt={item.filename}
            loading="lazy"
            className="size-full object-cover"
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <Icon size={28} strokeWidth={1.5} />
            <span className="font-mono text-[10.5px] tracking-wider">
              {fileExtension(item.filename)}
            </span>
          </div>
        )}
        {item.preview_url && item.kind === "video" && (
          <span className="absolute inset-0 flex items-center justify-center">
            <span className="flex size-10 items-center justify-center rounded-full bg-accent-foreground/65">
              <Play
                size={18}
                strokeWidth={1.5}
                className="ml-0.5 fill-background text-background"
              />
            </span>
          </span>
        )}
        {showChip && (
          <span className="absolute right-1.5 bottom-1.5 flex size-[22px] items-center justify-center rounded-sm bg-accent-foreground/65 text-background">
            <Icon size={12} strokeWidth={1.5} />
          </span>
        )}
      </div>
      <div className="mt-1.5 flex justify-between gap-2 text-[11.5px]">
        <span className="truncate font-mono font-semibold text-primary">
          #{item.ticket_number}
        </span>
        <span className="shrink-0 font-mono text-muted-foreground">
          {formatShortDateTime(item.created_at)}
        </span>
      </div>
    </button>
  )
}
