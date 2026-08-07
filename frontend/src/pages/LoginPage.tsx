import { LogIn, Loader2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { FieldError } from "@/components/ui/field-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { fieldErrorProps } from "@/lib/field-error"
import { isValidEmail } from "@/lib/validation"

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [tenantSlug, setTenantSlug] = useState("")
  const [remember, setRemember] = useState(false)
  const [loading, setLoading] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | null>(null)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmedEmail = email.trim()
    const nextEmailError = !trimmedEmail
      ? "Informe o email"
      : !isValidEmail(trimmedEmail)
        ? "Informe um email válido, com @ e domínio (ex.: nome@empresa.com)"
        : null
    const nextPasswordError = !password ? "Informe a senha" : null
    setEmailError(nextEmailError)
    setPasswordError(nextPasswordError)
    if (nextEmailError || nextPasswordError) return

    setLoading(true)
    try {
      await login({ email: trimmedEmail, password, tenantSlug, remember })
      navigate("/")
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "erro inesperado ao entrar"
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="flex w-full max-w-sm flex-col items-center gap-8">
        <div className="flex flex-col items-center gap-1 text-center">
          <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Sistema interno de atendimento
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">SAC-B2PRO</h1>
        </div>

        <Card className="w-full rounded-md border-border shadow-none">
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-foreground">Entrar</CardTitle>
            <CardDescription>Informe o slug da organização e suas credenciais.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
              <div className="flex flex-col gap-2">
                <Label htmlFor="tenant">Organização (slug)</Label>
                <Input
                  id="tenant"
                  className="font-mono"
                  value={tenantSlug}
                  onChange={(e) => setTenantSlug(e.target.value)}
                  placeholder="vazio para o painel da plataforma"
                  autoComplete="organization"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value)
                    if (emailError) setEmailError(null)
                  }}
                  autoComplete="username"
                  {...fieldErrorProps("email", emailError)}
                />
                <FieldError fieldId="email" message={emailError} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="password">Senha</Label>
                <Input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    if (passwordError) setPasswordError(null)
                  }}
                  autoComplete="current-password"
                  {...fieldErrorProps("password", passwordError)}
                />
                <FieldError fieldId="password" message={passwordError} />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="remember"
                  checked={remember}
                  onCheckedChange={(checked) => setRemember(checked === true)}
                />
                <Label htmlFor="remember" className="font-normal text-muted-foreground">
                  Manter sessão neste dispositivo
                </Label>
              </div>
              <Button type="submit" disabled={loading} className="mt-1">
                {loading ? (
                  <>
                    <Loader2 size={20} strokeWidth={1.5} className="animate-spin" />
                    Entrando...
                  </>
                ) : (
                  <>
                    <LogIn size={20} strokeWidth={1.5} />
                    Entrar
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  )
}
