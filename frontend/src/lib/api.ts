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

export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const doFetch = (token: string | null) =>
    fetch(`/api${path}`, {
      method: init.method ?? "GET",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
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
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
