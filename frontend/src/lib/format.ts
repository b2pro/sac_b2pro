export function onlyDigits(value: string): string {
  return value.replace(/\D/g, "")
}

export function formatDocument(value: string): string {
  const digits = onlyDigits(value)
  if (digits.length === 11) {
    return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
  }
  if (digits.length === 14) {
    return digits.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5")
  }
  return value
}

export function formatPhone(value: string): string {
  const digits = onlyDigits(value)
  if (digits.length === 11) return digits.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3")
  if (digits.length === 10) return digits.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3")
  return value
}

export function formatCep(value: string): string {
  const digits = onlyDigits(value)
  if (digits.length === 8) return digits.replace(/(\d{5})(\d{3})/, "$1-$2")
  return value
}

export function formatDuration(hours: number | null): string {
  if (hours === null) return "—"
  const total = Math.round(hours)
  const d = Math.floor(total / 24)
  const h = total % 24
  if (d > 0) return h > 0 ? `${d}d ${h}h` : `${d}d`
  return `${h}h`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${Math.round(kb)} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

export function slaRemaining(dueAt: string): string {
  const diffHours = (new Date(dueAt).getTime() - Date.now()) / 3_600_000
  const sign = diffHours < 0 ? "-" : ""
  return sign + formatDuration(Math.abs(diffHours))
}
