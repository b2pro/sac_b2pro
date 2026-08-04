import { ChevronDown, LogOut } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { GlobalSearch } from "@/components/layout/GlobalSearch"
import { NotificationBell } from "@/components/layout/NotificationBell"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/lib/auth"

export function Header() {
  const { session, logout } = useAuth()
  const navigate = useNavigate()

  function onLogout() {
    logout()
    navigate("/login")
  }

  return (
    <header className="flex h-14 items-center gap-1 border-b border-border bg-background px-4">
      {/* busca e notificacoes sao por tenant: sem tenant ativo (super admin na
          area de plataforma) nao ha o que buscar nem fila para ouvir */}
      <div className="flex flex-1 items-center">
        {session?.tenantSlug ? <GlobalSearch /> : null}
      </div>
      {session?.tenantSlug ? <NotificationBell /> : null}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="gap-2">
            {session?.user.name}
            <ChevronDown size={16} strokeWidth={1.5} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel className="font-mono text-xs">
            {session?.user.email}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={onLogout}>
            <LogOut size={16} strokeWidth={1.5} />
            Sair
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
