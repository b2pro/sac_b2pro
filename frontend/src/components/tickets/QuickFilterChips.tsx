import type { TicketCounters } from "@/lib/tickets"
import { cn } from "@/lib/utils"

export type QuickFilterKey =
  | "todos"
  | "abertos"
  | "aguardando_analise"
  | "atrasados"
  | "nao_lidos"
  | "meus"

const CHIPS: { key: QuickFilterKey; label: string; counterKey: keyof TicketCounters }[] = [
  { key: "todos", label: "Todos", counterKey: "todos" },
  { key: "abertos", label: "Abertos", counterKey: "abertos" },
  { key: "aguardando_analise", label: "Aguardando analise", counterKey: "aguardando_analise" },
  { key: "atrasados", label: "Atrasados", counterKey: "atrasados" },
  { key: "nao_lidos", label: "Nao lidos", counterKey: "nao_lidos" },
  { key: "meus", label: "Meus tickets", counterKey: "meus" },
]

export function QuickFilterChips({
  counters,
  active,
  onSelect,
}: {
  counters: TicketCounters | undefined
  active: QuickFilterKey | null
  onSelect: (key: QuickFilterKey) => void
}) {
  return (
    <div className="mb-5 flex flex-wrap gap-1.5">
      {CHIPS.map((chip) => {
        const isActive = chip.key === active
        const isAlert = chip.key === "atrasados"
        const count = counters?.[chip.counterKey]
        return (
          <button
            key={chip.key}
            type="button"
            aria-pressed={isActive}
            onClick={() => onSelect(chip.key)}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-md border px-2.5 text-xs hover:border-foreground",
              isActive
                ? "border-accent-foreground bg-accent-foreground font-semibold text-background"
                : isAlert
                  ? "border-border bg-card font-semibold text-primary"
                  : "border-border bg-card text-foreground",
            )}
          >
            {chip.label}
            {count !== undefined && (
              <span
                className={cn(
                  "font-mono text-[11px]",
                  isActive ? "text-border" : isAlert ? "text-primary" : "text-muted-foreground",
                )}
              >
                {count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
