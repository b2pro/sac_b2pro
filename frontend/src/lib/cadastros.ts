import { api } from "@/lib/api"

export type CatalogPath = "marcas" | "defeitos" | "solucoes" | "canais"

export type CatalogItem = {
  id: string
  name: string
  description: string | null
  active: boolean
}

export type CatalogItemInput = { name: string; description?: string | null }

export type Customer = {
  id: string
  name: string
  document: string
  phone: string | null
  email: string | null
  cep: string | null
  street: string | null
  number: string | null
  complement: string | null
  neighborhood: string | null
  city: string | null
  state: string | null
  active: boolean
}

export type CustomerInput = Omit<Customer, "id" | "active">

export type Product = {
  id: string
  name: string
  sku: string
  segment: string | null
  description: string | null
  photo_key: string | null
  active: boolean
}

export type ProductInput = Pick<Product, "name" | "sku" | "segment" | "description">

export type Page<T> = { items: T[]; total: number; page: number; per_page: number }

export type CepAddress = {
  cep: string
  street: string
  neighborhood: string
  city: string
  state: string
}

export function canCreateCadastros(role: string | null): boolean {
  return role !== null && role !== "visualizador"
}

export function canManageCadastros(role: string | null): boolean {
  return role === "admin" || role === "supervisor"
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ""
}

export const listCatalog = (path: CatalogPath, params: { search?: string; active?: boolean } = {}) =>
  api<CatalogItem[]>(`/cadastros/${path}${query(params)}`)

export const createCatalogItem = (path: CatalogPath, input: CatalogItemInput) =>
  api<CatalogItem>(`/cadastros/${path}`, { method: "POST", body: input })

export const updateCatalogItem = (path: CatalogPath, id: string, input: CatalogItemInput) =>
  api<CatalogItem>(`/cadastros/${path}/${id}`, { method: "PUT", body: input })

export const setCatalogItemActive = (path: CatalogPath, id: string, active: boolean) =>
  api<CatalogItem>(`/cadastros/${path}/${id}/active`, { method: "PATCH", body: { active } })

export const listCustomers = (
  params: { search?: string; active?: boolean; page?: number; perPage?: number } = {},
) =>
  api<Page<Customer>>(
    `/cadastros/clientes${query({
      search: params.search,
      active: params.active,
      page: params.page,
      per_page: params.perPage,
    })}`,
  )

export const createCustomer = (input: CustomerInput) =>
  api<Customer>("/cadastros/clientes", { method: "POST", body: input })

export const updateCustomer = (id: string, input: CustomerInput) =>
  api<Customer>(`/cadastros/clientes/${id}`, { method: "PUT", body: input })

export const setCustomerActive = (id: string, active: boolean) =>
  api<Customer>(`/cadastros/clientes/${id}/active`, { method: "PATCH", body: { active } })

export const listProducts = (
  params: { search?: string; active?: boolean; page?: number; perPage?: number } = {},
) =>
  api<Page<Product>>(
    `/cadastros/produtos${query({
      search: params.search,
      active: params.active,
      page: params.page,
      per_page: params.perPage,
    })}`,
  )

export const createProduct = (input: ProductInput) =>
  api<Product>("/cadastros/produtos", { method: "POST", body: input })

export const updateProduct = (id: string, input: ProductInput) =>
  api<Product>(`/cadastros/produtos/${id}`, { method: "PUT", body: input })

export const setProductActive = (id: string, active: boolean) =>
  api<Product>(`/cadastros/produtos/${id}/active`, { method: "PATCH", body: { active } })

export const lookupCep = (cep: string) => api<CepAddress>(`/cep/${cep}`)
