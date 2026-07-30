import { X } from "lucide-react"

export function ActiveFilterChips({
  chips,
  onRemove,
}: {
  chips: { key: string; label: string }[]
  onRemove: (key: string) => void
}) {
  if (chips.length === 0) return null

  return (
    <div className="mb-5 flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground">Filtros ativos:</span>
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          title="Remover filtro"
          aria-label={`Remover filtro ${chip.label}`}
          onClick={() => onRemove(chip.key)}
          className="flex h-[26px] items-center gap-1.5 rounded-md border border-border bg-muted pr-1.5 pl-2.5 text-xs whitespace-nowrap text-foreground hover:border-foreground"
        >
          {chip.label}
          <X size={13} strokeWidth={1.5} className="text-muted-foreground" aria-hidden />
        </button>
      ))}
    </div>
  )
}
