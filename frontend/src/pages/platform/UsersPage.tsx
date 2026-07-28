import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { KeyRound, Plus, Users as UsersIcon } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiError } from "@/lib/api"
import {
  createUser,
  listUsers,
  resetPassword,
  setUserActive,
  type PlatformUser,
} from "@/lib/platform"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

export default function UsersPage() {
  const queryClient = useQueryClient()
  const { data: users, isLoading } = useQuery({ queryKey: ["platform-users"], queryFn: listUsers })
  const [createOpen, setCreateOpen] = useState(false)
  // Checkbox do shadcn (Radix) nao e um input nativo: nao aparece em FormData
  // por padrao. Controlamos o estado a parte e incluimos no payload na mao.
  const [isSuperAdmin, setIsSuperAdmin] = useState(false)
  const [resetUser, setResetUser] = useState<PlatformUser | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["platform-users"] })

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      toast.success("Usuario criado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const activeMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => setUserActive(id, active),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  const resetMutation = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      resetPassword(id, password),
    onSuccess: () => {
      setResetUser(null)
      toast.success("Senha redefinida")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onCreateOpenChange(open: boolean) {
    setCreateOpen(open)
    if (!open) setIsSuperAdmin(false)
  }

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    createMutation.mutate({
      name: String(form.get("name")),
      email: String(form.get("email")),
      password: String(form.get("password")),
      is_super_admin: isSuperAdmin,
    })
  }

  function onReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!resetUser) return
    const form = new FormData(event.currentTarget)
    resetMutation.mutate({ id: resetUser.id, password: String(form.get("password")) })
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <UsersIcon size={20} strokeWidth={1.5} className="text-muted-foreground" />
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Usuarios</h1>
        </div>
        <Dialog open={createOpen} onOpenChange={onCreateOpenChange}>
          <DialogTrigger asChild>
            <Button>
              <Plus size={20} strokeWidth={1.5} />
              Novo usuario
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo usuario</DialogTitle>
            </DialogHeader>
            <form onSubmit={onCreate} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="name">Nome</Label>
                <Input id="name" name="name" required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" name="email" type="email" className="font-mono" required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="password">Senha</Label>
                <Input id="password" name="password" type="password" required minLength={8} />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="is_super_admin"
                  checked={isSuperAdmin}
                  onCheckedChange={(checked) => setIsSuperAdmin(checked === true)}
                />
                <Label htmlFor="is_super_admin">Super admin</Label>
              </div>
              <Button type="submit" disabled={createMutation.isPending} className="mt-1">
                Criar
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Perfil</TableHead>
              <TableHead>Ativo</TableHead>
              <TableHead className="w-40 text-right">Acoes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Carregando usuarios...
                </TableCell>
              </TableRow>
            ) : (users ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Nenhum usuario cadastrado.
                </TableCell>
              </TableRow>
            ) : (
              (users ?? []).map((user) => (
                <TableRow key={user.id}>
                  <TableCell>{user.name}</TableCell>
                  <TableCell className="font-mono text-sm">{user.email}</TableCell>
                  <TableCell>
                    {user.is_super_admin ? <Badge variant="outline">super admin</Badge> : null}
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={user.active}
                      onCheckedChange={(checked) =>
                        activeMutation.mutate({ id: user.id, active: checked })
                      }
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => setResetUser(user)}>
                      <KeyRound size={16} strokeWidth={1.5} />
                      Redefinir senha
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={resetUser != null} onOpenChange={(open) => !open && setResetUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Redefinir senha de {resetUser?.name}</DialogTitle>
          </DialogHeader>
          <form onSubmit={onReset} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="new-password">Nova senha</Label>
              <Input id="new-password" name="password" type="password" required minLength={8} />
            </div>
            <Button type="submit" disabled={resetMutation.isPending} className="mt-1">
              Salvar
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  )
}
