import { api } from "@/lib/api"

export type TenantStatus = "ativa" | "teste" | "suspensa" | "inativa"

export type Tenant = {
  id: string
  slug: string
  name: string
  status: TenantStatus
  modules: Record<string, boolean>
}

export type PlatformUser = {
  id: string
  name: string
  email: string
  is_super_admin: boolean
  active: boolean
}

export type TenantLink = {
  user_id: string
  tenant_id: string
  role: "admin" | "supervisor" | "atendente" | "visualizador"
  active: boolean
}

export const KNOWN_MODULES = ["cadastros", "tickets", "relatorios", "galeria", "notificacoes"]

export const listTenants = () => api<Tenant[]>("/platform/tenants")

export const createTenant = (input: {
  slug: string
  name: string
  modules?: Record<string, boolean>
}) => api<Tenant>("/platform/tenants", { method: "POST", body: input })

export const setTenantStatus = (id: string, status: TenantStatus) =>
  api<Tenant>(`/platform/tenants/${id}/status`, { method: "PATCH", body: { status } })

export const setTenantModules = (id: string, modules: Record<string, boolean>) =>
  api<Tenant>(`/platform/tenants/${id}/modules`, { method: "PUT", body: { modules } })

export const listUsers = () => api<PlatformUser[]>("/platform/users")

export const createUser = (input: {
  name: string
  email: string
  password: string
  is_super_admin?: boolean
}) => api<PlatformUser>("/platform/users", { method: "POST", body: input })

export const setUserActive = (id: string, active: boolean) =>
  api<PlatformUser>(`/platform/users/${id}/active`, { method: "PATCH", body: { active } })

export const resetPassword = (id: string, password: string) =>
  api<void>(`/platform/users/${id}/password`, { method: "POST", body: { password } })

export const listLinks = (tenantId: string) =>
  api<TenantLink[]>(`/platform/tenants/${tenantId}/links`)

export const createLink = (tenantId: string, input: { user_id: string; role: TenantLink["role"] }) =>
  api<TenantLink>(`/platform/tenants/${tenantId}/links`, { method: "POST", body: input })

export const deleteLink = (tenantId: string, userId: string) =>
  api<void>(`/platform/tenants/${tenantId}/links/${userId}`, { method: "DELETE" })
