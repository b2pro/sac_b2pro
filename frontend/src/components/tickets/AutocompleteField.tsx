import { useQuery } from "@tanstack/react-query"
import { useEffect, useRef, useState, type KeyboardEvent } from "react"

import { Input } from "@/components/ui/input"
import { useDebounce } from "@/lib/useDebounce"
import { cn } from "@/lib/utils"

export type AutocompleteOption = { id: string; label: string; sublabel?: string }

export function AutocompleteField({
  id,
  placeholder,
  value,
  onValueChange,
  onSelect,
  fetchOptions,
  queryKey,
  disabled,
  "aria-invalid": ariaInvalid,
  "aria-describedby": ariaDescribedBy,
}: {
  id: string
  placeholder: string
  value: string
  onValueChange: (value: string) => void
  onSelect: (option: AutocompleteOption) => void
  fetchOptions: (search: string) => Promise<AutocompleteOption[]>
  queryKey: string
  disabled?: boolean
  "aria-invalid"?: boolean
  "aria-describedby"?: string
}) {
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const debouncedValue = useDebounce(value.trim())

  const { data: options = [], isFetching } = useQuery({
    queryKey: ["ticket-autocomplete", queryKey, debouncedValue],
    queryFn: () => fetchOptions(debouncedValue),
    enabled: debouncedValue.length > 0,
  })

  const safeHighlighted = Math.min(highlighted, Math.max(options.length - 1, 0))

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("pointerdown", onPointerDown)
    return () => document.removeEventListener("pointerdown", onPointerDown)
  }, [])

  function selectOption(option: AutocompleteOption) {
    onSelect(option)
    setOpen(false)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open || options.length === 0) return
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setHighlighted((h) => Math.min(h + 1, options.length - 1))
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      setHighlighted((h) => Math.max(h - 1, 0))
    } else if (event.key === "Enter") {
      event.preventDefault()
      selectOption(options[safeHighlighted])
    } else if (event.key === "Escape") {
      setOpen(false)
    }
  }

  const showDropdown = open && debouncedValue.length > 0

  return (
    <div ref={containerRef} className="relative">
      <Input
        id={id}
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        autoComplete="off"
        aria-invalid={ariaInvalid}
        aria-describedby={ariaDescribedBy}
        onChange={(e) => {
          onValueChange(e.target.value)
          setOpen(true)
          setHighlighted(0)
        }}
        onFocus={() => value.trim() && setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {showDropdown && (
        <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-border bg-popover shadow-md">
          {isFetching ? (
            <p className="px-3 py-2 text-sm text-muted-foreground">Buscando...</p>
          ) : options.length === 0 ? (
            <p className="px-3 py-2 text-sm text-muted-foreground">Nenhum resultado</p>
          ) : (
            options.map((option, index) => (
              <button
                key={option.id}
                type="button"
                onClick={() => selectOption(option)}
                onMouseEnter={() => setHighlighted(index)}
                className={cn(
                  "flex w-full flex-col items-start px-3 py-2 text-left text-sm",
                  index === safeHighlighted
                    ? "bg-accent text-accent-foreground"
                    : "text-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                <span>{option.label}</span>
                {option.sublabel && (
                  <span className="text-xs text-muted-foreground">{option.sublabel}</span>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
