import {
  Building2,
  ClipboardCheck,
  Contact,
  FileBarChart,
  Images,
  LayoutDashboard,
  Package,
  Store,
  Tags,
  Ticket,
  Users,
  Wrench,
} from "lucide-react"
import { NavLink } from "react-router-dom"

import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth"

type NavItem = { to: string; label: string; icon: typeof Building2 }

export function Sidebar() {
  const { session } = useAuth()

  const groups: { label: string; items: NavItem[] }[] = []
  if (session?.user.is_super_admin) {
    groups.push({
      label: "Plataforma",
      items: [
        { to: "/plataforma/tenants", label: "Tenants", icon: Building2 },
        { to: "/plataforma/usuarios", label: "Usuarios", icon: Users },
      ],
    })
  }
  if (session?.tenantSlug) {
    groups.push({
      label: "Operacao",
      items: [
        { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
        { to: "/tickets", label: "Tickets", icon: Ticket },
        { to: "/relatorios", label: "Relatorios", icon: FileBarChart },
        { to: "/midias", label: "Midias", icon: Images },
      ],
    })
    groups.push({
      label: "Cadastros",
      items: [
        { to: "/cadastros/marcas", label: "Marcas", icon: Tags },
        { to: "/cadastros/produtos", label: "Produtos", icon: Package },
        { to: "/cadastros/defeitos", label: "Defeitos", icon: Wrench },
        { to: "/cadastros/solucoes", label: "Solucoes", icon: ClipboardCheck },
        { to: "/cadastros/canais", label: "Canais", icon: Store },
        { to: "/cadastros/clientes", label: "Clientes", icon: Contact },
      ],
    })
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="border-b border-sidebar-border px-4 py-4 text-sm font-semibold tracking-wide text-sidebar-accent-foreground">
        SAC B2PRO
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {groups.map((group) => (
          <div key={group.label} className="mb-4">
            {/* /70 e nao /60: a 60% o rotulo do grupo dava 4,22:1 no tema claro
                e 4,48:1 no escuro, os dois abaixo de AA para texto normal */}
            <p className="px-4 py-2 text-xs uppercase tracking-wider text-sidebar-foreground/70">
              {group.label}
            </p>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 border-l-2 border-transparent px-4 py-2 text-sm",
                    "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                    isActive &&
                      "border-sidebar-primary bg-sidebar-accent text-sidebar-accent-foreground",
                  )
                }
              >
                <item.icon size={20} strokeWidth={1.5} />
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  )
}
