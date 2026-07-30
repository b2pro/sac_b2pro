import { cn } from "@/lib/utils"

/** Cabecalho de coluna das tabelas de tickets (Dashboard e Relatorios). */
export function ThCell({
  align = "left",
  children,
}: {
  align?: "left" | "right"
  children: string
}) {
  return (
    <th
      className={cn(
        "border-b border-border px-2.5 py-2 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase",
        align === "left" ? "pl-3.5 text-left" : "pr-4 text-right",
      )}
    >
      {children}
    </th>
  )
}
