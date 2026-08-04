import { Outlet } from "react-router-dom"

import { Header } from "@/components/layout/Header"
import { Sidebar } from "@/components/layout/Sidebar"
import { useApplyThemePreference } from "@/lib/preferences"

export function AppShell() {
  // Um lugar so, e sempre autenticado (o AppShell fica dentro do RequireAuth):
  // o tema salvo no servidor vence o cache local deste navegador.
  useApplyThemePreference()

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
