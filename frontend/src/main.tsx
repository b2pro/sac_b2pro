import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { createBrowserRouter, RouterProvider } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { Toaster } from "@/components/ui/sonner"
import { AuthProvider } from "@/lib/auth"
import { RequireAuth, RequireSuperAdmin, RequireTenant } from "@/lib/guards"
import CatalogPage from "@/pages/cadastros/CatalogPage"
import ClientesPage from "@/pages/cadastros/ClientesPage"
import ProdutosPage from "@/pages/cadastros/ProdutosPage"
import LoginPage from "@/pages/LoginPage"
import TenantsPage from "@/pages/platform/TenantsPage"
import UsersPage from "@/pages/platform/UsersPage"
import TicketCreatePage from "@/pages/tickets/TicketCreatePage"
import TicketDetailPage from "@/pages/tickets/TicketDetailPage"
import TicketsListPage from "@/pages/tickets/TicketsListPage"
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
              { path: "/tickets", element: <TicketsListPage /> },
              { path: "/tickets/novo", element: <TicketCreatePage /> },
              { path: "/tickets/:id", element: <TicketDetailPage /> },
              { path: "/cadastros/marcas", element: <CatalogPage title="Marcas" path="marcas" /> },
              { path: "/cadastros/produtos", element: <ProdutosPage /> },
              {
                path: "/cadastros/defeitos",
                element: <CatalogPage title="Defeitos" path="defeitos" />,
              },
              {
                path: "/cadastros/solucoes",
                element: <CatalogPage title="Solucoes" path="solucoes" />,
              },
              {
                path: "/cadastros/canais",
                element: <CatalogPage title="Canais de compra" path="canais" />,
              },
              { path: "/cadastros/clientes", element: <ClientesPage /> },
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
