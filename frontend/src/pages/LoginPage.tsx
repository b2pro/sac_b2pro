import { LogIn, Loader2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [tenantSlug, setTenantSlug] = useState("")
  const [remember, setRemember] = useState(false)
  const [loading, setLoading] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    try {
      await login({ email, password, tenantSlug, remember })
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
            <CardDescription>Informe o slug da organizacao e suas credenciais.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="flex flex-col gap-5">
              <div className="flex flex-col gap-2">
                <Label htmlFor="tenant">Organizacao (slug)</Label>
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
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="password">Senha</Label>
                <Input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="remember"
                  checked={remember}
                  onCheckedChange={(checked) => setRemember(checked === true)}
                />
                <Label htmlFor="remember" className="font-normal text-muted-foreground">
                  Manter sessao neste dispositivo
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
