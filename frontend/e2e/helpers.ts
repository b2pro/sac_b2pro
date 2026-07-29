import { expect, type APIRequestContext, type Page } from "@playwright/test"

export const SLUG = "e2e"
export const PASSWORD = "senha-e2e-12345"
export const API = "http://localhost:8000/api"

export const USERS = {
  admin: { email: "e2e-admin@b2pro.com", name: "Alice Admin" },
  supervisor: { email: "e2e-supervisor@b2pro.com", name: "Dora Supervisora" },
  atendente: { email: "e2e-atendente@b2pro.com", name: "Bruno Atendente" },
  viewer: { email: "e2e-viewer@b2pro.com", name: "Carla Viewer" },
} as const

export type Who = keyof typeof USERS

type SessionUser = { id: string; name: string; email: string }

/** Formato que o front guarda em localStorage sob a chave "sac.session". */
type Session = {
  accessToken: string
  refreshToken: string
  user: SessionUser
  tenantSlug: string | null
  role: string | null
}

const SESSION_KEY = "sac.session"

/**
 * O backend limita login a 5 tentativas por minuto por IP+tenant, entao a suite
 * autentica cada usuario uma vez e reaproveita a sessao (com retry em 429).
 */
const sessions = new Map<Who, Session>()

async function requestSession(request: APIRequestContext, who: Who): Promise<Session> {
  const cached = sessions.get(who)
  if (cached) return cached

  let lastBody = ""
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const res = await request.post(`${API}/auth/login`, {
      data: { email: USERS[who].email, password: PASSWORD, tenant_slug: SLUG },
    })
    if (res.ok()) {
      const body = (await res.json()) as {
        access_token: string
        refresh_token: string
        user: SessionUser
        tenant_slug: string | null
        role: string | null
      }
      const session: Session = {
        accessToken: body.access_token,
        refreshToken: body.refresh_token,
        user: body.user,
        tenantSlug: body.tenant_slug,
        role: body.role,
      }
      sessions.set(who, session)
      return session
    }
    lastBody = await res.text()
    if (res.status() !== 429) break
    await new Promise((resolve) => setTimeout(resolve, 15_000))
  }
  throw new Error(`login de ${who} falhou: ${lastBody}`)
}

export async function token(request: APIRequestContext, who: Who): Promise<string> {
  return (await requestSession(request, who)).accessToken
}

/** Entra pelo formulario de login (valida a propria tela de login). */
export async function loginViaForm(page: Page, who: Who): Promise<void> {
  await page.goto("/login")
  await page.locator("#tenant").fill(SLUG)
  await page.locator("#email").fill(USERS[who].email)
  await page.locator("#password").fill(PASSWORD)
  await page.getByRole("button", { name: "Entrar" }).click()
  await expect(page.getByRole("link", { name: "Tickets" })).toBeVisible()
}

/** Injeta a sessao autenticada, sem gastar tentativa de login no rate limit. */
export async function login(page: Page, request: APIRequestContext, who: Who): Promise<void> {
  const session = await requestSession(request, who)
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key as string, value as string),
    [SESSION_KEY, JSON.stringify(session)],
  )
  await page.goto("/tickets")
  await expect(page.getByRole("link", { name: "Tickets" })).toBeVisible()
}

async function authGet<T>(request: APIRequestContext, who: Who, path: string): Promise<T> {
  const res = await request.get(`${API}${path}`, {
    headers: { Authorization: `Bearer ${await token(request, who)}` },
  })
  expect(res.ok(), `GET ${path} falhou: ${await res.text()}`).toBeTruthy()
  return (await res.json()) as T
}

type Named = { id: string; name: string }

export async function catalogId(
  request: APIRequestContext,
  path: "marcas" | "defeitos" | "solucoes" | "canais",
  name?: string,
): Promise<string> {
  const items = await authGet<Named[]>(request, "admin", `/cadastros/${path}`)
  const found = name ? items.find((item) => item.name === name) : items[0]
  expect(found, `catalogo ${path} sem item ${name ?? "[primeiro]"}`).toBeTruthy()
  return found!.id
}

export async function firstProductId(request: APIRequestContext): Promise<string> {
  const list = await authGet<{ items: Named[] }>(request, "admin", "/cadastros/produtos")
  expect(list.items.length, "nenhum produto cadastrado no tenant e2e").toBeGreaterThan(0)
  return list.items[0].id
}

/** Cria um produto dedicado pela API. Usado quando o teste precisa de um
 *  produto isolado (ex.: foto/preview), em vez de reaproveitar o catalogo
 *  compartilhado do tenant e2e — evita interferencia entre execucoes. */
export async function apiCreateProduct(
  request: APIRequestContext,
  who: Who,
  body: { name: string; sku: string; segment?: string; description?: string },
): Promise<{ id: string; name: string; sku: string }> {
  const res = await request.post(`${API}/cadastros/produtos`, {
    headers: { Authorization: `Bearer ${await token(request, who)}` },
    data: body,
  })
  expect(res.ok(), `criacao de produto falhou: ${await res.text()}`).toBeTruthy()
  return (await res.json()) as { id: string; name: string; sku: string }
}

/** Le o photo_key atual do produto direto do backend (nao do cache do React
 *  Query da pagina) — usado para provar que uma acao de UI realmente mudou
 *  (ou nao mudou) o estado no servidor, e nao so fechou um dialog. */
export async function apiProductPhotoKey(
  request: APIRequestContext,
  sku: string,
): Promise<string | null> {
  const list = await authGet<{ items: Array<{ sku: string; photo_key: string | null }> }>(
    request,
    "admin",
    `/cadastros/produtos?search=${encodeURIComponent(sku)}`,
  )
  const found = list.items.find((item) => item.sku === sku)
  expect(found, `produto com sku ${sku} nao encontrado`).toBeTruthy()
  return found!.photo_key
}

type TicketPayload = Record<string, unknown>

export async function apiCreateTicket(
  request: APIRequestContext,
  who: Who,
  body: TicketPayload,
): Promise<{ id: string; number: number }> {
  const res = await request.post(`${API}/tickets`, {
    headers: { Authorization: `Bearer ${await token(request, who)}` },
    data: body,
  })
  expect(res.ok(), `criacao de ticket por ${who} falhou: ${await res.text()}`).toBeTruthy()
  return (await res.json()) as { id: string; number: number }
}

export async function apiFullTicket(
  request: APIRequestContext,
  who: Who,
  extra: TicketPayload = {},
): Promise<{ id: string; number: number }> {
  return apiCreateTicket(request, who, {
    brand_id: await catalogId(request, "marcas", "KODI"),
    priority: "media",
    description: "produto chegou com defeito",
    customer: { name: "Cliente E2E", document: randomCpf() },
    items: [
      {
        product_id: await firstProductId(request),
        defect_type_id: await catalogId(request, "defeitos"),
        quantity: 1,
      },
    ],
    ...extra,
  })
}

/** CPF valido e aleatorio, para exercitar o caminho de cliente novo em cada execucao. */
export function randomCpf(): string {
  const base = Array.from({ length: 9 }, () => Math.floor(Math.random() * 10))
  const digit = (slice: number[], startWeight: number): number => {
    const sum = slice.reduce((acc, value, index) => acc + value * (startWeight - index), 0)
    const rest = (sum * 10) % 11
    return rest === 10 ? 0 : rest
  }
  const d1 = digit(base, 10)
  const d2 = digit([...base, d1], 11)
  return [...base, d1, d2].join("")
}

export function formatCpf(digits: string): string {
  return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
}

/** Seleciona uma opcao de um Select (Radix) pelo id do trigger. */
export async function selectOption(
  page: Page,
  triggerId: string,
  optionName: string | RegExp,
): Promise<void> {
  await page.locator(`#${triggerId}`).click()
  await page.getByRole("option", { name: optionName }).first().click()
}
