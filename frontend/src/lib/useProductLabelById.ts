import { useEffect } from "react"

import { listProducts } from "@/lib/cadastros"

// Nao existe endpoint de produto por id no backend (so listagem, criacao,
// atualizacao e ativacao). A listagem aceita no maximo 100 itens por pagina
// (limite do backend); busca-se essa pagina e filtra-se pelo id no cliente.
const LOOKUP_PER_PAGE = 100

/**
 * Resolve o nome de um produto pelo id quando a tela e aberta com
 * `product_id` na URL mas ainda sem rotulo conhecido (ex.: link
 * compartilhado). So dispara enquanto nao houver rotulo (`hasLabel`), para
 * nao refazer a busca a cada render nem atropelar o rotulo que o usuario
 * acabou de escolher no autocomplete. Id inexistente ou requisicao com falha
 * simplesmente nao resolvem nada: quem chama degrada para o rotulo generico.
 *
 * `onResolved` deve ter identidade estavel entre renders (ex.: useCallback
 * com deps vazias) para nao refazer a busca sem necessidade.
 */
export function useProductLabelById(
  productId: string,
  hasLabel: boolean,
  onResolved: (name: string) => void,
): void {
  useEffect(() => {
    if (!productId || hasLabel) return
    let active = true
    listProducts({ perPage: LOOKUP_PER_PAGE })
      .then((page) => {
        if (!active) return
        const found = page.items.find((item) => item.id === productId)
        if (found) onResolved(found.name)
      })
      .catch(() => {
        // id invalido ou falha de rede: mantem o rotulo generico ja existente
      })
    return () => {
      active = false
    }
  }, [productId, hasLabel, onResolved])
}
