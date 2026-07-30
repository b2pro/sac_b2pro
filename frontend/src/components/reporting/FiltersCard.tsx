import { ChevronDown, ChevronUp } from "lucide-react"
import { useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"

function readCollapsed(storageKey: string): boolean {
  try {
    return sessionStorage.getItem(storageKey) === "1"
  } catch {
    return false
  }
}

function writeCollapsed(storageKey: string, collapsed: boolean): void {
  try {
    sessionStorage.setItem(storageKey, collapsed ? "1" : "0")
  } catch {
    // sessionStorage indisponivel (modo privado etc.): estado fica so em memoria
  }
}

/**
 * Casca colapsavel reusada por filtros de Relatorios e Midias. Comeca aberta;
 * o estado recolhido persiste por sessao sob `storageKey` — e a ferramenta
 * principal da tela, esconder por padrao custaria mais cliques do que economiza.
 */
export function FiltersCard({
  children,
  footer,
  storageKey,
}: {
  children: ReactNode
  footer?: ReactNode
  storageKey: string
}) {
  const [collapsed, setCollapsed] = useState(() => readCollapsed(storageKey))

  function toggle() {
    setCollapsed((current) => {
      const next = !current
      writeCollapsed(storageKey, next)
      return next
    })
  }

  return (
    <section className="mb-4 rounded-md border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border p-3">
        <h2 className="text-[13.5px] font-semibold text-accent-foreground">Filtros</h2>
        <Button type="button" variant="ghost" size="sm" onClick={toggle} aria-expanded={!collapsed}>
          {collapsed ? "Expandir" : "Recolher"}
          {collapsed ? (
            <ChevronDown size={14} strokeWidth={1.5} />
          ) : (
            <ChevronUp size={14} strokeWidth={1.5} />
          )}
        </Button>
      </div>
      {!collapsed && (
        <>
          <div className="grid gap-3 p-4 [grid-template-columns:repeat(auto-fit,minmax(190px,1fr))]">
            {children}
          </div>
          {footer && <div className="flex justify-end gap-2 px-4 pb-4">{footer}</div>}
        </>
      )}
    </section>
  )
}
