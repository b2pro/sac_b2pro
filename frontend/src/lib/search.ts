import { api } from "@/lib/api"
import type { TicketStatus } from "@/lib/tickets"

/** Espelho de TicketHitOut (backend). */
export type TicketHit = {
  id: string
  number: number
  status: TicketStatus
  customer_name: string | null
  brand_name: string | null
}

/** Espelho de CustomerHitOut (backend). */
export type CustomerHit = {
  id: string
  name: string
  document: string | null
}

/** Espelho de ProductHitOut (backend). */
export type ProductHit = {
  id: string
  name: string
  sku: string | null
}

/** Espelho de GlobalSearchOut: os grupos vem com no maximo 5 itens cada. */
export type SearchHits = {
  tickets: TicketHit[]
  clientes: CustomerHit[]
  produtos: ProductHit[]
}

/** Mesmo minimo do MIN_TERM_LENGTH do backend. O servidor devolve grupos
 *  vazios abaixo disso sem tocar o banco, e o cliente nem chega a pedir: a
 *  palette dispara a cada tecla, entao uma chamada por caractere de um termo
 *  que nunca traz resultado e trafego puro. */
export const MIN_SEARCH_LENGTH = 2

export function globalSearch(q: string): Promise<SearchHits> {
  return api<SearchHits>(`/busca?q=${encodeURIComponent(q)}`)
}
