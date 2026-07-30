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

/** dd/mm hh:mm, sem virgula (o que toLocaleString com dateStyle/timeStyle
 *  produziria em pt-BR). Usado pelo tile e pelo lightbox de midias e pela
 *  coluna "ultima atividade" das tabelas de tickets. */
export function formatShortDateTime(iso: string): string {
  const date = new Date(iso)
  const dd = String(date.getDate()).padStart(2, "0")
  const mm = String(date.getMonth() + 1).padStart(2, "0")
  const hh = String(date.getHours()).padStart(2, "0")
  const min = String(date.getMinutes()).padStart(2, "0")
  return `${dd}/${mm} ${hh}:${min}`
}

// a API filtra por "< ate" (exclusivo), entao o dia final escolhido no input
// de data precisa entrar inteiro: guardamos o dia seguinte a meia-noite UTC.
// Usado por Relatorios e Midias, cujos filtros de periodo seguem a mesma
// convencao.
export function isoStart(dateInput: string): string {
  return new Date(`${dateInput}T00:00:00Z`).toISOString()
}

export function isoEndExclusive(dateInput: string): string {
  const date = new Date(`${dateInput}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + 1)
  return date.toISOString()
}

export function isoToDateInput(iso: string): string {
  return iso.slice(0, 10)
}

export function isValidIso(value: string): boolean {
  return !Number.isNaN(new Date(value).getTime())
}

// "ate" invalido (URL editada a mao) e tratado como ausente: nao vai para a
// API e nao quebra o input de data com um Invalid Date.
export function isoEndExclusiveToDateInput(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  date.setUTCDate(date.getUTCDate() - 1)
  return date.toISOString().slice(0, 10)
}
