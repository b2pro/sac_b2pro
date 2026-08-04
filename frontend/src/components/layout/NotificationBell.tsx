import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Bell,
  CheckCheck,
  GitCommitHorizontal,
  MessageSquareText,
  UserPlus,
  type LucideIcon,
} from "lucide-react"
import { useCallback, useEffect, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ApiError } from "@/lib/api"
import { formatShortDateTime } from "@/lib/format"
import {
  fetchCounter,
  fetchNotifications,
  markRead,
  playNotificationBeep,
  startNotificationStream,
  type NotificationItem,
  type NotificationType,
} from "@/lib/notifications"
import { cn } from "@/lib/utils"

// Preferencias do usuario chegam na Task 14 (`usePreferences`): trocar este
// objeto pelo hook mantem o resto do componente igual. Default local: toast
// ligado (o aviso e o motivo do recurso), som desligado (barulho sem o usuario
// ter pedido incomoda em sala compartilhada).
const preferences: { notifyToast: boolean; notifySound: boolean } = {
  notifyToast: true,
  notifySound: false,
}

// O icone diz o TIPO do aviso; a barra lateral esquerda diz lido/nao lido.
// Cada elemento com um trabalho so.
const TYPE_ICONS: Record<NotificationType, LucideIcon> = {
  atribuicao: UserPlus,
  transicao: GitCommitHorizontal,
  // MessageSquareText e nao MessageSquare: a bolha vazia em 16px passa por
  // checkbox e convida a clicar para "marcar" a linha
  comentario: MessageSquareText,
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

function unreadLabel(count: number): string {
  return count === 1 ? "1 notificacao nao lida" : `${count} notificacoes nao lidas`
}

export function NotificationBell() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  // `undefined` = nenhuma consulta concluida ainda; `null` = consultou e a lista
  // esta vazia. A distincao importa: sem ela, a primeira notificacao de quem
  // nunca recebeu nenhuma seria tratada como "carga inicial" e nao avisaria.
  const lastSeenIdRef = useRef<string | null | undefined>(undefined)

  const { data: counter } = useQuery({
    queryKey: ["notificacoes-contador"],
    queryFn: fetchCounter,
  })
  const { data, isLoading, isError } = useQuery({
    queryKey: ["notificacoes"],
    queryFn: () => fetchNotifications(),
  })

  const unread = counter?.nao_lidas ?? 0
  const items = data?.items ?? []

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["notificacoes"] })
    void queryClient.invalidateQueries({ queryKey: ["notificacoes-contador"] })
  }, [queryClient])

  useEffect(() => {
    // O evento do stream nao carrega conteudo — e so sinal para reconsultar.
    return startNotificationStream(refresh)
  }, [refresh])

  useEffect(() => {
    if (!data) return
    const newest = data.items[0] ?? null
    const lastSeenId = lastSeenIdRef.current
    lastSeenIdRef.current = newest?.id ?? null
    // Avisa so quando a mais recente MUDA de identidade: a primeira carga da
    // sessao apenas registra (nada de anunciar o que o usuario ja viu) e uma
    // reconsulta por reconexao do stream nao repete o aviso, porque o topo da
    // lista continua o mesmo.
    if (lastSeenId === undefined) return
    if (!newest || newest.id === lastSeenId) return
    if (newest.read_at !== null) return
    if (preferences.notifyToast) {
      toast(newest.title, { description: newest.snippet ?? undefined })
    }
    if (preferences.notifySound) playNotificationBeep()
  }, [data])

  const markMutation = useMutation({
    mutationFn: markRead,
    onSuccess: refresh,
    onError: (error) => toast.error(errorMessage(error)),
  })

  function openNotification(item: NotificationItem) {
    if (item.read_at === null) markMutation.mutate([item.id])
    navigate(`/tickets/${item.ticket_id}`)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Notificacoes" className="relative">
          <Bell size={20} strokeWidth={1.5} />
          <span aria-live="polite" className="pointer-events-none absolute -top-0.5 -right-0.5">
            {unread > 0 ? (
              <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-[3px] bg-primary px-1 font-mono text-[10px] leading-none font-medium tabular-nums text-primary-foreground ring-1 ring-background">
                <span aria-hidden="true">{unread > 99 ? "99+" : unread}</span>
                <span className="sr-only">{unreadLabel(unread)}</span>
              </span>
            ) : null}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[22rem] p-0">
        <DropdownMenuLabel className="border-b border-border px-3 py-2">
          Notificacoes
        </DropdownMenuLabel>
        <div className="max-h-80 overflow-y-auto">
          {isLoading ? (
            <p className="px-3 py-6 text-sm text-muted-foreground">Carregando notificacoes...</p>
          ) : null}
          {isError ? (
            <p className="px-3 py-6 text-sm text-destructive">
              Nao foi possivel carregar as notificacoes.
            </p>
          ) : null}
          {!isLoading && !isError && items.length === 0 ? (
            <div className="px-3 py-6">
              <p className="text-sm">Sem notificacoes.</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Atribuicao, mudanca de status e comentario nos seus tickets aparecem aqui.
              </p>
            </div>
          ) : null}
          {items.map((item) => {
            const Icon = TYPE_ICONS[item.type]
            const isUnread = item.read_at === null
            return (
              <DropdownMenuItem
                key={item.id}
                onSelect={() => openNotification(item)}
                className={cn(
                  // borda esquerda de 3px como nos cards da fila: da pra varrer
                  // o que ainda nao foi lido pela lateral, sem ler texto
                  "cursor-pointer items-start gap-2.5 rounded-none border-l-[3px] px-3 py-2.5",
                  isUnread ? "border-l-foreground bg-secondary/60" : "border-l-transparent",
                )}
              >
                <Icon size={16} strokeWidth={1.5} className="mt-0.5" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{item.title}</span>
                  {item.snippet ? (
                    <span className="block truncate text-xs text-muted-foreground">
                      {item.snippet}
                    </span>
                  ) : null}
                  <span className="mt-1 block font-mono text-[11px] text-muted-foreground">
                    #{item.ticket_number} · {formatShortDateTime(item.created_at)}
                  </span>
                </span>
              </DropdownMenuItem>
            )
          })}
        </div>
        {unread > 0 ? (
          <DropdownMenuItem
            onSelect={() => markMutation.mutate(null)}
            disabled={markMutation.isPending}
            className="cursor-pointer justify-center rounded-none border-t border-border px-3 py-2 text-xs"
          >
            <CheckCheck size={16} strokeWidth={1.5} />
            Marcar todas como lidas
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
