import { Navigate, Outlet } from "react-router-dom"

import { useAuth } from "@/lib/auth"

export function RequireAuth() {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" replace />
  return <Outlet />
}

export function RequireSuperAdmin() {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" replace />
  if (!session.user.is_super_admin) return <Navigate to="/" replace />
  return <Outlet />
}

export function RequireAdmin() {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" replace />
  if (session.role !== "admin") return <Navigate to="/" replace />
  return <Outlet />
}

export function RequireTenant() {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" replace />
  if (!session.tenantSlug) return <Navigate to="/" replace />
  return <Outlet />
}
