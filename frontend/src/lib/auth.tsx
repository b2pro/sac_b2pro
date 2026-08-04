import { useQueryClient } from "@tanstack/react-query"
import { createContext, useCallback, useContext, useState, type ReactNode } from "react"

import {
  api,
  clearSession,
  loadSession,
  saveSession,
  type LoginResponse,
  type Session,
} from "@/lib/api"

type LoginInput = {
  email: string
  password: string
  tenantSlug: string
  remember: boolean
}

type AuthContextValue = {
  session: Session | null
  login: (input: LoginInput) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(loadSession)
  const queryClient = useQueryClient()

  const login = useCallback(async (input: LoginInput) => {
    const data = await api<LoginResponse>("/auth/login", {
      method: "POST",
      body: {
        email: input.email,
        password: input.password,
        tenant_slug: input.tenantSlug || null,
      },
    })
    const next: Session = {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      user: data.user,
      tenantSlug: data.tenant_slug,
      role: data.role,
    }
    saveSession(next, input.remember)
    setSession(next)
  }, [])

  const logout = useCallback(() => {
    clearSession()
    // As query keys nao levam o usuario, entao o cache sobreviveria ao logout e o
    // proximo login na mesma aba renderizaria dado do usuario anterior (contador
    // e titulos de notificacao, por exemplo) no intervalo entre o primeiro render
    // e o refetch. Limpar aqui e o que garante que nao ha vazamento entre contas.
    queryClient.clear()
    setSession(null)
  }, [queryClient])

  return <AuthContext.Provider value={{ session, login, logout }}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components -- hook e provider ficam juntos de proposito (contrato consumido por Task 16-18)
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth fora do AuthProvider")
  return ctx
}
