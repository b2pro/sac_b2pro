import { cn } from "@/lib/utils"

/** Placeholder de carregamento generico (retangulo pulsante). Compartilhado
 *  pelas telas de Dashboard, Relatorios e Midias. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("rounded-md bg-muted motion-safe:animate-pulse", className)} />
}
