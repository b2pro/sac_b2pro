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
// entao ela e a unica coisa da tela que nao pode acompanhar o tema ativo. A
// faixa de navegacao e escura nos dois temas (o sidebar e Carbon Black sempre),
// so a area de trabalho troca.
const NAV = "#252422"
const SURFACE_LIGHT = "#fffcf2"
const SURFACE_DARK = "#2e2c29"
const LINE_LIGHT = "#ccc5b9"
const LINE_DARK = "#403d39"

const THEME_OPTIONS: { value: Theme; label: string; icon: LucideIcon }[] = [
  { value: "claro", label: "Claro", icon: Sun },
  { value: "escuro", label: "Escuro", icon: Moon },
  { value: "sistema", label: "Sistema", icon: Monitor },
]

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

/** Miniatura da propria interface — faixa de navegacao escura mais a area de
 *  trabalho — em vez de bolinha de radio: quem escolhe reconhece o produto no
 *  tema, sem depender da palavra. "Sistema" parte a area de trabalho ao meio
 *  porque e literalmente o que ele faz: vale um ou o outro. */
function ThemeSwatch({ theme }: { theme: Theme }) {
  const surfaces = theme === "sistema" ? [false, true] : [theme === "escuro"]
  return (
    <span aria-hidden="true" className="flex h-12 overflow-hidden rounded-sm border border-border">
      <span className="w-1/5 shrink-0" style={{ backgroundColor: NAV }} />
      {surfaces.map((dark) => (
        <span
          key={dark ? "dark" : "light"}
          className="flex flex-1 flex-col justify-center gap-1.5 px-2"
          style={{ backgroundColor: dark ? SURFACE_DARK : SURFACE_LIGHT }}
        >
          <span className="h-1" style={{ backgroundColor: dark ? LINE_DARK : LINE_LIGHT }} />
          <span className="h-1 w-2/3" style={{ backgroundColor: dark ? LINE_DARK : LINE_LIGHT }} />
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
  const { preferences, isLoading, isError } = usePreferences()

  const mutation = useMutation({
    mutationFn: savePreferences,
    // Otimista: o controle marcado e o tema respondem no clique, sem esperar a
    // rede. O corpo do PUT ja leva os tres campos e a resposta e ele de volta,
    // entao nao ha o que reconciliar no sucesso.
    onMutate: (next) => {
      queryClient.setQueryData<Preferences>(PREFERENCES_KEY, next)
    },
    onSuccess: () => toast.success("Preferencias salvas"),
    onError: (error) => {
      toast.error(errorMessage(error))
      // A tela mentiria se continuasse mostrando o que nao foi gravado.
      // Recarregar do servidor desfaz o otimismo, inclusive no tema:
      // `useApplyThemePreference` reaplica o valor que voltou.
      void queryClient.invalidateQueries({ queryKey: PREFERENCES_KEY })
    },
  })

  function update(patch: Partial<Preferences>) {
    mutation.mutate({ ...preferences, ...patch })
  }

  function onThemeChange(theme: Theme) {
    // Aplica antes de gravar: a troca de tema E o feedback do clique.
    setTheme(toNextTheme(theme))
    update({ theme })
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-accent-foreground">Preferencias</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Valem para a sua conta em qualquer navegador que voce usar
        </p>
      </div>

      {isLoading && (
        <div className="space-y-6">
          <Skeleton className="h-[176px]" />
          <Skeleton className="h-[184px]" />
        </div>
      )}

      {isError && (
        <EmptyState
          title="Nao foi possivel carregar as preferencias"
          description="Recarregue a pagina para tentar de novo."
        />
      )}

      {!isLoading && !isError && (
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
              <h2 className="text-[13.5px] font-semibold text-accent-foreground">Notificacoes</h2>
              <p className="mt-0.5 text-[12.5px] text-muted-foreground">
                Como avisar quando algo acontece nos seus tickets.
              </p>
            </div>
            <div className="divide-y divide-border">
              <ToggleRow
                id="pref-notify-toast"
                label="Aviso na tela"
                description="Mostra um cartao no canto quando chega uma notificacao."
                checked={preferences.notify_toast}
                onCheckedChange={(value) => update({ notify_toast: value })}
              />
              <ToggleRow
                id="pref-notify-sound"
                label="Som"
                description="Toca um bipe curto quando chega uma notificacao."
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
