import { readFileSync } from "node:fs"
import { basename } from "node:path"

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

/** Entra pelo formulario com email/senha que NAO estao em `USERS` (ex.: membro
 *  recem-criado pelo proprio teste) e por isso nao tem sessao cacheada. Este
 *  login sempre gasta uma tentativa do rate limit de 5/minuto por IP+tenant,
 *  entao segue o mesmo formato de retry de `requestSession`: em 429, espera e
 *  tenta de novo, em vez de estourar a suite quando outros logins de formulario
 *  ja gastaram o bucket. */
export async function loginViaFormRetrying(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    await page.goto("/login")
    await page.locator("#tenant").fill(SLUG)
    await page.locator("#email").fill(email)
    await page.locator("#password").fill(password)
    const response = page.waitForResponse((res) => res.url().endsWith("/api/auth/login"))
    await page.getByRole("button", { name: "Entrar" }).click()
    if ((await response).status() !== 429) {
      await expect(page.getByRole("link", { name: "Tickets" })).toBeVisible()
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 15_000))
  }
  throw new Error(`login de ${email} excedeu tentativas de retry por 429`)
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

async function authPost<T>(
  request: APIRequestContext,
  who: Who,
  path: string,
  data: object,
): Promise<T> {
  const res = await request.post(`${API}${path}`, {
    headers: { Authorization: `Bearer ${await token(request, who)}` },
    data,
  })
  expect(res.ok(), `POST ${path} falhou: ${await res.text()}`).toBeTruthy()
  return (await res.json()) as T
}

type CatalogPath = "marcas" | "defeitos" | "solucoes" | "canais"

/**
 * Garante o item de catalogo pelo nome e devolve o id.
 *
 * O provisionamento de tenant nao semeia catalogo nenhum (ver
 * backend/src/sac/infrastructure/tenant_seeds.py): marca, defeito, solucao e
 * canal descrevem a operacao de quem contratou, entao quem monta o cenario do
 * e2e e esta suite. Idempotente de proposito: o tenant e2e sobrevive entre
 * execucoes e nao pode ganhar uma duplicata por rodada.
 */
export async function catalogId(
  request: APIRequestContext,
  path: CatalogPath,
  name: string,
): Promise<string> {
  const items = await authGet<Named[]>(request, "admin", `/cadastros/${path}`)
  const found = items.find((item) => item.name === name)
  if (found) return found.id
  return (await authPost<Named>(request, "admin", `/cadastros/${path}`, { name })).id
}

/** Id de um item qualquer do catalogo, criando `fallback` se estiver vazio.
 *  Para quando o teste so precisa de "um defeito", sem depender de qual. */
export async function anyCatalogId(
  request: APIRequestContext,
  path: CatalogPath,
  fallback: string,
): Promise<string> {
  const items = await authGet<Named[]>(request, "admin", `/cadastros/${path}`)
  if (items.length > 0) return items[0].id
  return catalogId(request, path, fallback)
}

/** Produto que casa com `busca`, criado se nenhum casar.
 *
 *  A busca (e nao o nome exato) e o criterio porque os specs procuram o produto
 *  digitando um trecho -- "Alicate", "Tesoura" -- e qualquer produto que case ja
 *  serve. Assim o fixture nao duplica o que o tenant ja tem, seja qual for o
 *  nome completo cadastrado la. */
export async function productId(
  request: APIRequestContext,
  busca: string,
  novo: { name: string; sku: string },
): Promise<string> {
  const path = `/cadastros/produtos?search=${encodeURIComponent(busca)}`
  const list = await authGet<{ items: Named[] }>(request, "admin", path)
  if (list.items.length > 0) return list.items[0].id
  return (await apiCreateProduct(request, "admin", novo)).id
}

/** O produto que o ticket de fixture leva. O spec 01 filtra a fila por
 *  "Alicate" e espera achar justamente este ticket. */
const PRODUTO_TICKET = {
  busca: "Alicate",
  novo: { name: "Alicate de Cuticula KODI", sku: "E2E-ALICATE" },
}

/** O produto que o spec 03 adiciona pelo card Itens, conferindo o nome na
 *  celula depois. */
const PRODUTO_ITEM = {
  busca: "Tesoura",
  novo: { name: "Tesoura Reta STALEKS", sku: "E2E-TESOURA" },
}

/**
 * Deixa o tenant e2e com o cenario que os specs esperam encontrar pronto.
 *
 * Nem tudo passa por helper: os specs 02 e 03 escolhem a marca ("KODI",
 * "STALEKS") e o canal ("SAC") pelo nome, direto na UI, e o 03 confere o nome do
 * produto na celula. Sem catalogo semeado pelo backend, isso precisa existir
 * antes do primeiro teste -- por isso o globalSetup do Playwright chama esta
 * funcao. Tudo aqui e idempotente: num tenant que ja tem os registros, a funcao
 * so le.
 */
export async function ensureCatalogoBase(request: APIRequestContext): Promise<void> {
  for (const marca of ["KODI", "STALEKS"]) {
    await catalogId(request, "marcas", marca)
  }
  await catalogId(request, "canais", "SAC")
  await anyCatalogId(request, "defeitos", "Danificado")
  // o dialog de finalizar ticket exige tipo de solucao: sem nenhum cadastrado o
  // select abre vazio e o teste trava no clique da opcao.
  await anyCatalogId(request, "solucoes", "Troca pelo mesmo item")
  await productId(request, PRODUTO_TICKET.busca, PRODUTO_TICKET.novo)
  await productId(request, PRODUTO_ITEM.busca, PRODUTO_ITEM.novo)
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

/** Le o estado da foto do produto direto do backend (nao do cache do React
 *  Query da pagina) — usado para provar que uma acao de UI realmente mudou
 *  (ou nao mudou) o estado no servidor, e nao so fechou um dialog. `photo_url`
 *  so vem preenchido quando o original E o preview existem. */
export async function apiProductPhoto(
  request: APIRequestContext,
  sku: string,
): Promise<{ photo_key: string | null; photo_url: string | null }> {
  const list = await authGet<{
    items: Array<{ sku: string; photo_key: string | null; photo_url: string | null }>
  }>(request, "admin", `/cadastros/produtos?search=${encodeURIComponent(sku)}`)
  const found = list.items.find((item) => item.sku === sku)
  expect(found, `produto com sku ${sku} nao encontrado`).toBeTruthy()
  return { photo_key: found!.photo_key, photo_url: found!.photo_url }
}

export async function apiProductPhotoKey(
  request: APIRequestContext,
  sku: string,
): Promise<string | null> {
  return (await apiProductPhoto(request, sku)).photo_key
}

/** Cria intencoes de upload sem confirmar. Cada uma deixa no servidor uma linha
 *  de anexo `pendente`, que ocupa vaga na cota de 10 do ticket mas nao aparece
 *  na listagem (que so devolve `disponivel`) — exatamente o estado em que a UI
 *  mostra 0/10 e o servidor responde 409. Usado para levar o ticket a beira do
 *  limite sem depender de dez uploads reais. */
export async function apiPendingIntents(
  request: APIRequestContext,
  who: Who,
  ticketId: string,
  quantidade: number,
): Promise<string[]> {
  const ids: string[] = []
  for (let i = 0; i < quantidade; i += 1) {
    const res = await request.post(`${API}/tickets/${ticketId}/anexos/intencao`, {
      headers: { Authorization: `Bearer ${await token(request, who)}` },
      data: { filename: `pendente-${i}.png`, content_type: "image/png", size_bytes: 1024 },
    })
    expect(res.ok(), `intencao ${i} falhou: ${await res.text()}`).toBeTruthy()
    ids.push(((await res.json()) as { attachment_id: string }).attachment_id)
  }
  return ids
}

/** Sobe um anexo pela API do jeito que o navegador faz: intencao, PUT direto na
 *  URL assinada e confirmacao. Usado para montar um ticket com anexo de OUTRO
 *  autor — cenario que a UI de um unico usuario logado nao consegue produzir. */
export async function apiUploadAttachment(
  request: APIRequestContext,
  who: Who,
  ticketId: string,
  caminho: string,
): Promise<string> {
  const bytes = readFileSync(caminho)
  const headers = { Authorization: `Bearer ${await token(request, who)}` }
  const intentRes = await request.post(`${API}/tickets/${ticketId}/anexos/intencao`, {
    headers,
    data: {
      filename: basename(caminho),
      content_type: "image/png",
      size_bytes: bytes.length,
    },
  })
  expect(intentRes.ok(), `intencao de anexo falhou: ${await intentRes.text()}`).toBeTruthy()
  const intent = (await intentRes.json()) as { attachment_id: string; upload_url: string }

  const put = await request.put(intent.upload_url, {
    headers: { "Content-Type": "image/png" },
    data: bytes,
  })
  expect(put.ok(), `PUT no storage falhou: ${put.status()}`).toBeTruthy()

  const confirmar = await request.post(
    `${API}/tickets/${ticketId}/anexos/${intent.attachment_id}/confirmar`,
    { headers },
  )
  expect(confirmar.ok(), `confirmacao de anexo falhou: ${await confirmar.text()}`).toBeTruthy()
  return intent.attachment_id
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
        // produto explicito, nao "o primeiro do tenant": o spec 01 filtra a fila
        // por "Alicate" e espera este ticket no resultado.
        product_id: await productId(request, PRODUTO_TICKET.busca, PRODUTO_TICKET.novo),
        defect_type_id: await anyCatalogId(request, "defeitos", "Danificado"),
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

/** Email unico por execucao, para cadastros que a propria suite cria (ex.:
 *  membro novo em 10-preferencias-e-membros.spec.ts) — um endereco fixo
 *  colidiria com o registro que a execucao anterior deixou no banco. */
export function randomEmail(prefixo: string): string {
  const marca = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`
  return `${prefixo}-${marca}@b2pro.com`
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

/** Localiza o card de um ticket na fila repaginada (`TicketQueueCard`): o card
 *  inteiro e um unico `<a>`, entao o numero basta para distinguir (nenhum
 *  outro link da tela — nav, "Novo ticket", paginacao em botoes — tem "#" no
 *  nome acessivel). O match e por fronteira (nao substring): `hasText: "#12"`
 *  tambem casaria "#120", entao a regex exige que o numero termine em fim de
 *  string ou em um caractere nao-digito logo depois. */
export function ticketCard(page: Page, number: number) {
  return page.getByRole("link").filter({ hasText: new RegExp(`#${number}(\\D|$)`) })
}

/** Zera as notificacoes nao lidas de `who` pela API — usado para dar a um
 *  teste de SSE uma base conhecida (0 nao lidas) sem depender de quantas
 *  notificacoes execucoes anteriores deixaram para esse usuario seedado. */
export async function apiMarkAllNotificationsRead(
  request: APIRequestContext,
  who: Who,
): Promise<void> {
  const res = await request.post(`${API}/notificacoes/marcar-lidas`, {
    headers: { Authorization: `Bearer ${await token(request, who)}` },
    data: { ids: null },
  })
  expect(res.ok(), `marcar-lidas de ${who} falhou: ${await res.text()}`).toBeTruthy()
}

export type ApiPreferences = {
  theme: "claro" | "escuro" | "sistema"
  notify_toast: boolean
  notify_sound: boolean
}

/** Le as preferencias de `who` direto do backend — usado para guardar o valor
 *  original antes de um teste mudar o tema, e devolve-lo depois. */
export async function apiGetPreferences(
  request: APIRequestContext,
  who: Who,
): Promise<ApiPreferences> {
  return authGet<ApiPreferences>(request, who, "/preferencias")
}

export async function apiSavePreferences(
  request: APIRequestContext,
  who: Who,
  preferences: ApiPreferences,
): Promise<void> {
  const res = await request.put(`${API}/preferencias`, {
    headers: { Authorization: `Bearer ${await token(request, who)}` },
    data: preferences,
  })
  expect(res.ok(), `salvar preferencias de ${who} falhou: ${await res.text()}`).toBeTruthy()
}
