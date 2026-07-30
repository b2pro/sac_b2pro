import { Loader2 } from "lucide-react"
import { useEffect, useRef } from "react"

/** Sentinela de fim de grid observada por IntersectionObserver (rootMargin de
 *  400px para pre-carregar antes do usuario bater no fim de verdade). So
 *  dispara `onIntersect` quando `hasMore && !loading`: enquanto uma pagina
 *  esta em voo o proprio `loading=true` bloqueia o disparo, e quando
 *  `hasMore` vira false a sentinela para de observar de forma util (fica so
 *  a mensagem de fim de lista) — sem isso o observer re-disparando com o
 *  elemento parado na tela viraria requisicao em loop. */
export function InfiniteScrollSentinel({
  hasMore,
  loading,
  total,
  onIntersect,
}: {
  hasMore: boolean
  loading: boolean
  total: number
  onIntersect: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  // `onIntersect` costuma ser um closure novo a cada render de quem chama (ex.:
  // `() => fetchNextPage()` em MidiasPage). Se ele entrasse na dependencia do
  // efeito, qualquer re-render alheio a scroll (digitar num autocomplete,
  // trocar um select) recriaria o IntersectionObserver — e um `observe()` novo
  // dispara com o estado de intersecao atual do elemento, entao uma sentinela
  // parada dentro do rootMargin buscaria mais uma pagina sem o usuario ter
  // rolado nada. Guardar a versao mais recente numa ref mantem o ciclo de vida
  // do observer preso so ao que realmente importa: `hasMore`/`loading`.
  const onIntersectRef = useRef(onIntersect)
  useEffect(() => {
    onIntersectRef.current = onIntersect
  }, [onIntersect])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loading) onIntersectRef.current()
      },
      { rootMargin: "400px" },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasMore, loading])

  if (loading) {
    return (
      <div
        ref={ref}
        className="flex items-center justify-center gap-2.5 py-7 text-[12.5px] text-muted-foreground"
      >
        <Loader2 size={16} strokeWidth={1.5} className="animate-spin" />
        Carregando mais anexos...
      </div>
    )
  }

  if (!hasMore) {
    return (
      <div
        ref={ref}
        className="flex items-center justify-center gap-3 py-7 text-[12.5px] text-muted-foreground"
      >
        <span className="h-px w-12 shrink-0 bg-border" aria-hidden />
        Fim da lista — <span className="font-mono">{total}</span> anexos
        <span className="h-px w-12 shrink-0 bg-border" aria-hidden />
      </div>
    )
  }

  return <div ref={ref} aria-hidden className="h-px" />
}
