import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ThemeProvider } from "next-themes"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { Toaster } from "@/components/ui/sonner"
import { useAuth, AuthProvider } from "@/lib/auth"
import { RequireAuth, RequireSuperAdmin, RequireTenant } from "@/lib/guards"
import CatalogPage from "@/pages/cadastros/CatalogPage"
import ClientesPage from "@/pages/cadastros/ClientesPage"
import ProdutosPage from "@/pages/cadastros/ProdutosPage"
import DashboardPage from "@/pages/dashboard/DashboardPage"
import LoginPage from "@/pages/LoginPage"
import MidiasPage from "@/pages/midias/MidiasPage"
import TenantsPage from "@/pages/platform/TenantsPage"
import UsersPage from "@/pages/platform/UsersPage"
import PreferenciasPage from "@/pages/preferencias/PreferenciasPage"
import RelatoriosPage from "@/pages/relatorios/RelatoriosPage"
import TicketCreatePage from "@/pages/tickets/TicketCreatePage"
import TicketDetailPage from "@/pages/tickets/TicketDetailPage"
import TicketsListPage from "@/pages/tickets/TicketsListPage"
import "./index.css"

const queryClient = new QueryClient()

// eslint-disable-next-line react-refresh/only-export-components -- entrypoint sem exports; fast refresh nao tem como isolar este componente local
function HomeRedirect() {
  const { session } = useAuth()
  if (session?.tenantSlug) return <Navigate to="/dashboard" replace />
  return <p>Bem-vindo ao SAC-B2PRO</p>
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <HomeRedirect /> },
          // Fora do RequireTenant de proposito: preferencia e do usuario, nao
          // do tenant — acompanha quem entra em qualquer tenant e existe
          // tambem para o super admin, que navega sem tenant ativo.
          { path: "/preferencias", element: <PreferenciasPage /> },
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
              { path: "/dashboard", element: <DashboardPage /> },
              { path: "/relatorios", element: <RelatoriosPage /> },
              { path: "/midias", element: <MidiasPage /> },
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
    {/* Mais externo que o resto porque o Toaster tambem consulta o tema. O
        valor do servidor entra depois, pelo useApplyThemePreference no
        AppShell; aqui o next-themes cuida so do cache local, que e o que evita
        o flash no reload.

        ACOPLADO a index.html: o script pre-paint de lá repete este contrato em
        HTML cru (chave "theme" do storageKey default, attribute "class" e o
        default "system" que vem do enableSystem) porque num SPA o script do
        proprio next-themes so roda depois do primeiro paint. Mudar storageKey,
        attribute ou enableSystem aqui obriga a mudar index.html no mesmo
        commit, senao o app abre num tema e troca para outro. */}
    <ThemeProvider attribute="class" themes={["light", "dark"]} enableSystem>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
          <Toaster position="top-right" />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
