export type SessionUser = {
  id: string
  name: string
  email: string
  is_super_admin: boolean
  active: boolean
}

export type Session = {
  accessToken: string
  refreshToken: string
  user: SessionUser
  tenantSlug: string | null
  role: string | null
}

export type LoginResponse = {
  access_token: string
  refresh_token: string
  token_type: string
  user: SessionUser
  tenant_slug: string | null
  role: string | null
}

const KEY = "sac.session"

export function loadSession(): Session | null {
  const raw = sessionStorage.getItem(KEY) ?? localStorage.getItem(KEY)
  return raw ? (JSON.parse(raw) as Session) : null
}

export function saveSession(session: Session, remember: boolean): void {
  clearSession()
  const target = remember ? localStorage : sessionStorage
  target.setItem(KEY, JSON.stringify(session))
}

export function clearSession(): void {
  localStorage.removeItem(KEY)
  sessionStorage.removeItem(KEY)
}

export class ApiError extends Error {
  status: number
  code: string
  details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as { code?: string; message?: string; details?: unknown }
    return new ApiError(res.status, body.code ?? "erro", body.message ?? res.statusText, body.details)
  } catch {
    return new ApiError(res.status, "erro", res.statusText)
  }
}

async function tryRefresh(): Promise<Session | null> {
  const current = loadSession()
  if (!current) return null
  const res = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: current.refreshToken }),
  })
  if (!res.ok) {
    clearSession()
    return null
  }
  const data = (await res.json()) as LoginResponse
  const remember = localStorage.getItem(KEY) != null
  const next: Session = {
    ...current,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
  }
  saveSession(next, remember)
  return next
}

/** Faz a chamada com o access token atual e, se a API responder 401, tenta
 *  renovar a sessao uma vez e repete — a mesma logica de refresh-and-retry
 *  usada por toda chamada autenticada, aqui compartilhada entre `api` (json)
 *  e `apiRaw` (Response crua, para respostas binarias como o CSV e para o
 *  stream SSE de notificacoes, que precisa do Authorization que o EventSource
 *  nativo nao sabe enviar). */
export async function apiRaw(
  path: string,
  init: {
    method?: string
    body?: unknown
    headers?: Record<string, string>
    signal?: AbortSignal
  } = {},
): Promise<Response> {
  const doFetch = (token: string | null) =>
    fetch(`/api${path}`, {
      method: init.method ?? "GET",
      headers: {
        ...init.headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal,
    })

  let session = loadSession()
  let res = await doFetch(session?.accessToken ?? null)
  if (res.status === 401 && session) {
    session = await tryRefresh()
    if (!session) {
      window.location.assign("/login")
      throw new ApiError(401, "auth_error", "sessao expirada")
    }
    res = await doFetch(session.accessToken)
  }
  return res
}

export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const res = await apiRaw(path, { ...init, headers: { "Content-Type": "application/json" } })
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** Como `api`, mas devolve a Response crua (sem parsear json) — usado pelo
 *  download de CSV, que precisa do blob e nao de um corpo json. */
export async function apiBlob(path: string): Promise<Blob> {
  const res = await apiRaw(path)
  if (!res.ok) throw await parseError(res)
  return res.blob()
}
