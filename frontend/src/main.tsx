import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { createBrowserRouter, RouterProvider } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { Toaster } from "@/components/ui/sonner"
import { AuthProvider } from "@/lib/auth"
import { RequireAuth, RequireSuperAdmin, RequireTenant } from "@/lib/guards"
import LoginPage from "@/pages/LoginPage"
import TenantsPage from "@/pages/platform/TenantsPage"
import UsersPage from "@/pages/platform/UsersPage"
import "./index.css"

const queryClient = new QueryClient()

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <p>Bem-vindo ao SAC-B2PRO</p> },
          {
            element: <RequireSuperAdmin />,
            children: [
              { path: "/plataforma/tenants", element: <TenantsPage /> },
              { path: "/plataforma/usuarios", element: <UsersPage /> },
            ],
          },
          {
            element: <RequireTenant />,
            children: [
              { path: "/cadastros/marcas", element: <p>Marcas</p> },
              { path: "/cadastros/produtos", element: <p>Produtos</p> },
              { path: "/cadastros/defeitos", element: <p>Defeitos</p> },
              { path: "/cadastros/solucoes", element: <p>Solucoes</p> },
              { path: "/cadastros/canais", element: <p>Canais</p> },
              { path: "/cadastros/clientes", element: <p>Clientes</p> },
            ],
          },
        ],
      },
    ],
  },
])

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
        <Toaster position="top-right" />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
