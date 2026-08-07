import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Check, Monitor, Moon, Sun, type LucideIcon } from "lucide-react"
import { useTheme } from "next-themes"
import { toast } from "sonner"

import { EmptyState } from "@/components/reporting/EmptyState"
import { Skeleton } from "@/components/reporting/Skeleton"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { ApiError } from "@/lib/api"
import {
  PREFERENCES_KEY,
  savePreferences,
  toNextTheme,
  usePreferences,
  type Preferences,
  type Theme,
} from "@/lib/preferences"
import { cn } from "@/lib/utils"

// Hex literal, e nao os tokens do tema: a amostra mostra como CADA tema fica,
// entao ela e a unica coisa da tela que nao pode acompanhar o tema ativo. Os
// valores tem que espelhar os tokens de index.css — a faixa de navegacao e
// sempre a superficie mais escura da tela, e no tema escuro isso significa um
// tom ABAIXO do Carbon Black, senao a navegacao encostaria na area de trabalho.
const NAV_LIGHT = "#252422"
const NAV_DARK = "#1b1a19"
const SURFACE_LIGHT = "#fffcf2"
const SURFACE_DARK = "#252422"
const LINE_LIGHT = "#ccc5b9"
const LINE_DARK = "#4a4640"
// --sidebar-border: o mesmo divisor que a navegacao real tem a direita. No tema
// escuro ele e obrigatorio na amostra pelo mesmo motivo que e obrigatorio na
// tela — #1b1a19 contra #252422 e 1,12:1, e sem a linha a faixa de navegacao
// desaparece dentro da area de trabalho.
const NAV_LINE_LIGHT = "#403d39"
const NAV_LINE_DARK = "#34312d"

const THEME_OPTIONS: { value: Theme; label: string; icon: LucideIcon }[] = [
  { value: "claro", label: "Claro", icon: Sun },
  { value: "escuro", label: "Escuro", icon: Moon },
  { value: "sistema", label: "Sistema", icon: Monitor },
]

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

/** Miniatura da propria interface — faixa de navegacao mais a area de trabalho —
 *  em vez de bolinha de radio: quem escolhe reconhece o produto no tema, sem
 *  depender da palavra. "Sistema" mostra as duas miniaturas lado a lado porque e
 *  literalmente o que ele faz: vale um ou o outro. Cada metade leva a propria
 *  faixa de navegacao, ja que a navegacao tambem muda de tom entre os temas. */
function ThemeSwatch({ theme }: { theme: Theme }) {
  const surfaces = theme === "sistema" ? [false, true] : [theme === "escuro"]
  return (
    <span aria-hidden="true" className="flex h-12 overflow-hidden rounded-sm border border-border">
      {surfaces.map((dark) => (
        <span key={dark ? "dark" : "light"} className="flex min-w-0 flex-1">
          <span
            className="w-1/5 shrink-0 border-r"
            style={{
              backgroundColor: dark ? NAV_DARK : NAV_LIGHT,
              borderRightColor: dark ? NAV_LINE_DARK : NAV_LINE_LIGHT,
            }}
          />
          <span
            className="flex min-w-0 flex-1 flex-col justify-center gap-1.5 px-2"
            style={{ backgroundColor: dark ? SURFACE_DARK : SURFACE_LIGHT }}
          >
            <span className="h-1" style={{ backgroundColor: dark ? LINE_DARK : LINE_LIGHT }} />
            <span className="h-1 w-2/3" style={{ backgroundColor: dark ? LINE_DARK : LINE_LIGHT }} />
          </span>
        </span>
      ))}
    </span>
  )
}

function ToggleRow({
  id,
  label,
  description,
  checked,
  onCheckedChange,
}: {
  id: string
  label: string
  description: string
  checked: boolean
  onCheckedChange: (value: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-6 px-4 py-3.5">
      <div className="min-w-0">
        <Label htmlFor={id} className="text-[13.5px]">
          {label}
        </Label>
        <p className="mt-1 text-[12.5px] text-muted-foreground">{description}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} className="mt-0.5" />
    </div>
  )
}

export default function PreferenciasPage() {
  const queryClient = useQueryClient()
  const { setTheme } = useTheme()
  const { preferences, isLoading, isLoadingError } = usePreferences()

  const mutation = useMutation({
    // Uma gravacao por vez. Os tres controles compartilham esta mutation, e sem
    // serializar dois cliques rapidos viram dois PUT concorrentes: o `previous`
    // do primeiro fica mais velho que o valor que o segundo talvez ja tenha
    // confirmado, e o rollback do primeiro apagaria justamente o que o servidor
    // aceitou. Com escopo, o segundo espera o primeiro terminar — ordem de
    // clique = ordem de ida = ordem de volta —, entao nenhum snapshot pode ser
    // velho em relacao a um valor confirmado e o estado final e sempre o do
    // ultimo clique. O `onMutate` roda no clique mesmo com a mutation em espera
    // na fila, entao o controle continua respondendo na hora.
    scope: { id: "preferencias" },
    mutationFn: savePreferences,
    // Otimista: o controle marcado e o tema respondem no clique, sem esperar a
    // rede.
    onMutate: (next) => {
      const previous = queryClient.getQueryData<Preferences>(PREFERENCES_KEY)
      queryClient.setQueryData<Preferences>(PREFERENCES_KEY, next)
      return { previous }
    },
    // Grava o que o servidor devolveu, e nao so confia no otimismo: quando uma
    // gravacao falha e a seguinte da fila da certo, o rollback da primeira ja
    // desfez o otimismo da segunda, e e esta linha que devolve a tela ao valor
    // que o servidor passou a ter. So e seguro por causa do `scope`: sem
    // serializar, resposta atrasada de um PUT antigo sobrescreveria um mais novo.
    onSuccess: (saved) => {
      queryClient.setQueryData<Preferences>(PREFERENCES_KEY, saved)
      toast.success("Preferências salvas")
    },
    onError: (error, _next, context) => {
      toast.error(errorMessage(error))
      // Desfaz o otimismo com o valor guardado no `onMutate`, e nao com uma
      // reconsulta: o que derruba o PUT (servidor fora, rede caida, sessao
      // expirada) derruba o GET seguinte tambem, e ai a tela ficaria mostrando
      // para sempre algo que o servidor nunca aceitou. Restaurar o cache
      // reverte de tabela: o radio volta, o NotificationBell volta a ler os
      // valores gravados e o `useApplyThemePreference` reaplica o tema anterior
      // — o que reescreve tambem o localStorage do next-themes, senao o proximo
      // reload abriria num tema que o servidor nao tem.
      if (context?.previous) {
        queryClient.setQueryData<Preferences>(PREFERENCES_KEY, context.previous)
      }
      // Depois de reverter, reconsulta por garantia (a gravacao pode ter
      // chegado e so a resposta ter se perdido). Se falhar, o cache revertido
      // continua valendo — a reconsulta e o reforco, nao o rollback.
      void queryClient.invalidateQueries({ queryKey: PREFERENCES_KEY })
    },
  })

  function update(patch: Partial<Preferences>) {
    mutation.mutate({ ...preferences, ...patch })
  }

  function onThemeChange(theme: Theme) {
    // Aplica antes de gravar: a troca de tema E o feedback do clique. Se o PUT
    // falhar, quem desfaz e o `onError` restaurando o cache — nao ha um
    // `setTheme` de volta aqui de proposito, para o tema ter um dono so
    // (`useApplyThemePreference`) e nao dois escritores discordando.
    setTheme(toNextTheme(theme))
    update({ theme })
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-accent-foreground">Preferências</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Valem para a sua conta em qualquer navegador que você usar
        </p>
      </div>

      {isLoading && (
        <div className="space-y-6">
          <Skeleton className="h-[176px]" />
          <Skeleton className="h-[184px]" />
        </div>
      )}

      {/* `isLoadingError`, nao `isError`: so troca a tela pela mensagem quando a
          primeira carga falhou. Reconsulta que falha com dado bom em cache
          mantem o formulario no ar — o toast de erro do PUT ja avisou. */}
      {isLoadingError && (
        <EmptyState
          title="Não foi possível carregar as preferências"
          description="Recarregue a página para tentar de novo."
        />
      )}

      {!isLoading && !isLoadingError && (
        <div className="space-y-6">
          <section className="rounded-md border border-border bg-card">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-[13.5px] font-semibold text-accent-foreground">Tema</h2>
              <p className="mt-0.5 text-[12.5px] text-muted-foreground">
                Sistema acompanha o tema do seu sistema operacional.
              </p>
            </div>
            <fieldset className="p-4">
              <legend className="sr-only">Tema da interface</legend>
              <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
                {THEME_OPTIONS.map((option) => {
                  const selected = preferences.theme === option.value
                  return (
                    <label
                      key={option.value}
                      className={cn(
                        "relative flex cursor-pointer flex-col gap-2.5 rounded-md border p-3 transition-colors",
                        "hover:border-foreground",
                        "has-[:focus-visible]:border-ring has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50",
                        selected ? "border-foreground bg-secondary" : "border-border",
                      )}
                    >
                      {/* Radio nativo (o teclado navega com as setas de graca),
                          invisivel e por cima do cartao inteiro: o alvo do
                          clique e o proprio controle, e nao a label em volta. */}
                      <input
                        type="radio"
                        name="tema"
                        value={option.value}
                        checked={selected}
                        onChange={() => onThemeChange(option.value)}
                        className="absolute inset-0 cursor-pointer appearance-none rounded-md opacity-0"
                      />
                      <ThemeSwatch theme={option.value} />
                      <span className="flex items-center gap-1.5 text-[13px] font-medium">
                        <option.icon size={16} strokeWidth={1.5} />
                        {option.label}
                        {selected && <Check size={16} strokeWidth={1.5} className="ml-auto" />}
                      </span>
                    </label>
                  )
                })}
              </div>
            </fieldset>
          </section>

          <section className="rounded-md border border-border bg-card">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-[13.5px] font-semibold text-accent-foreground">Notificações</h2>
              <p className="mt-0.5 text-[12.5px] text-muted-foreground">
                Como avisar quando algo acontece nos seus tickets.
              </p>
            </div>
            <div className="divide-y divide-border">
              <ToggleRow
                id="pref-notify-toast"
                label="Aviso na tela"
                description="Mostra um cartão no canto quando chega uma notificação."
                checked={preferences.notify_toast}
                onCheckedChange={(value) => update({ notify_toast: value })}
              />
              <ToggleRow
                id="pref-notify-sound"
                label="Som"
                description="Toca um bipe curto quando chega uma notificação."
                checked={preferences.notify_sound}
                onCheckedChange={(value) => update({ notify_sound: value })}
              />
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
