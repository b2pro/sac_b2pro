import { useQuery } from "@tanstack/react-query"
import { useTheme } from "next-themes"
import { useEffect } from "react"

import { api } from "@/lib/api"

export type Theme = "claro" | "escuro" | "sistema"

/** Espelho de PreferencesOut (backend). */
export type Preferences = {
  theme: Theme
  notify_toast: boolean
  notify_sound: boolean
}

export const PREFERENCES_KEY = ["preferencias"] as const

/** Os mesmos defaults do backend, que devolve estes valores sem gravar linha
 *  para quem nunca salvou nada. Repetidos aqui so para cobrir a janela antes da
 *  primeira resposta, e nenhum consumidor precisar tratar `undefined`.
 *  Constante de modulo de proposito — ver `usePreferences`. */
const DEFAULT_PREFERENCES: Preferences = {
  theme: "sistema",
  notify_toast: true,
  notify_sound: false,
}

/** Preferencia muda por acao explicita do usuario, nunca sozinha, e vale para
 *  toda a sessao: sem staleTime cada tela nova refaria a chamada. */
const STALE_TIME_MS = 30 * 60 * 1_000

export function fetchPreferences(): Promise<Preferences> {
  return api<Preferences>("/preferencias")
}

export function savePreferences(preferences: Preferences): Promise<Preferences> {
  return api<Preferences>("/preferencias", { method: "PUT", body: preferences })
}

/** O valor trafega em portugues (dominio e API); o next-themes so entende
 *  light/dark/system. A traducao fica aqui e em nenhum outro lugar. */
export function toNextTheme(theme: Theme): "light" | "dark" | "system" {
  if (theme === "claro") return "light"
  if (theme === "escuro") return "dark"
  return "system"
}

/** Uma definicao so, compartilhada pelos dois hooks abaixo — mesma chave, uma
 *  requisicao. */
const preferencesQuery = {
  queryKey: PREFERENCES_KEY,
  queryFn: fetchPreferences,
  staleTime: STALE_TIME_MS,
}

/** Preferencias do usuario logado, com os defaults enquanto a query nao
 *  resolve.
 *
 *  A REFERENCIA de `preferences` e estavel entre renders — o react-query
 *  preserva a identidade de `data` enquanto o conteudo nao muda e
 *  `DEFAULT_PREFERENCES` e constante de modulo. Isso e requisito, nao detalhe:
 *  o NotificationBell le estas preferencias dentro de um efeito, entao um
 *  objeto novo a cada render faria o efeito rodar em todo render. Por isso o
 *  objeto nao pode ser montado aqui: `{ ...data }` ou um remapeamento de nomes
 *  (`{ notifyToast: ... }`) quebraria a garantia.
 *
 *  Expoe `isLoadingError` e nao `isError` de proposito: `isError` tambem fica
 *  verdadeiro quando uma REconsulta falha com dado bom ainda em cache, e quem
 *  usasse isso para trocar a tela por uma mensagem de erro apagaria um
 *  formulario que continua valido. `isLoadingError` so e verdadeiro quando a
 *  primeira carga falhou, ou seja, quando de fato nao ha o que mostrar.
 *  `isLoading` ja tem esse cuidado nativo (nao liga em refetch de fundo). */
export function usePreferences(): {
  preferences: Preferences
  isLoading: boolean
  isLoadingError: boolean
} {
  const { data, isLoading, isLoadingError } = useQuery(preferencesQuery)
  return { preferences: data ?? DEFAULT_PREFERENCES, isLoading, isLoadingError }
}

/** Aplica no next-themes o tema que veio do servidor. Montado uma vez no
 *  AppShell.
 *
 *  A ordem importa: o next-themes le o localStorage no primeiro render e pinta
 *  a tela antes de qualquer resposta de rede (e por isso que nao ha flash), e o
 *  valor do servidor chega depois. Quando chega, ele vence — a preferencia
 *  acompanha o usuario e o localStorage e so o cache deste navegador, entao
 *  quem escolheu tema escuro em outra maquina cai no escuro aqui tambem.
 *
 *  O efeito espera `data`: aplicar o default antes da resposta sobrescreveria o
 *  cache local com "system" e piscaria a tela de quem escolheu tema fixo.
 *
 *  Nao ha laco. `setTheme` mexe no estado do next-themes, nunca na query, e o
 *  proprio `setTheme` troca de identidade a cada mudanca de tema (e um
 *  useCallback com o tema na lista de dependencias) — o efeito roda mais uma
 *  vez por isso, chama `setTheme` com o valor que ja esta valendo e o React
 *  descarta o setState igual. Para no segundo passo. */
export function useApplyThemePreference(): void {
  const { data } = useQuery(preferencesQuery)
  const { setTheme } = useTheme()
  const nextTheme = data ? toNextTheme(data.theme) : null

  useEffect(() => {
    if (nextTheme === null) return
    setTheme(nextTheme)
  }, [nextTheme, setTheme])
}
