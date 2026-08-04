import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { KeyRound, Pencil, Plus } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
import { useAuth } from "@/lib/auth"
import {
  createMember,
  listMembersAdmin,
  resetMemberPassword,
  updateMember,
  type MemberDetail,
  type MemberRole,
} from "@/lib/members"

const MEMBERS_KEY = ["membros-gerencia"]
const MIN_PASSWORD_LENGTH = 8

/** A descricao de cada papel fica no seletor, e nao numa coluna da tabela: ela
 *  muda uma decisao no momento em que o admin escolhe, e repetida em toda linha
 *  viraria ruido. Os textos espelham ROLE_PERMISSIONS do backend. */
const ROLES: { value: MemberRole; label: string; description: string }[] = [
  {
    value: "admin",
    label: "Administrador",
    description: "Tudo do supervisor, mais a gestao dos membros deste tenant.",
  },
  {
    value: "supervisor",
    label: "Supervisor",
    description: "Ve e decide qualquer ticket e gerencia todos os cadastros.",
  },
  {
    value: "atendente",
    label: "Atendente",
    description: "Cria e atende os proprios tickets; nao decide nem ve os dos outros.",
  },
  {
    value: "visualizador",
    label: "Visualizador",
    description: "So consulta: ve todos os tickets, sem alterar nada.",
  },
]

function roleLabel(role: MemberRole): string {
  return ROLES.find((item) => item.value === role)?.label ?? role
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

/** O cadastro responde 404 para dois casos que a API nao distingue DE PROPOSITO
 *  — o email e de um super admin da plataforma, ou pertence a outro tenant —,
 *  para que este formulario nao possa ser usado para descobrir quem existe na
 *  plataforma. A copia tem que preservar a ambiguidade: uma frase so, que serve
 *  aos dois casos e nao confirma qual deles aconteceu. A mensagem do backend
 *  ("usuario nao encontrado") e generica pelo mesmo motivo, mas le mal num
 *  formulario de cadastro, entao a troca aqui e de clareza, nao de conteudo. */
function createErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return "Nao foi possivel cadastrar este email neste tenant. Confira o endereco ou peca o vinculo ao administrador da plataforma."
  }
  return errorMessage(error)
}

function RoleSelect({
  id,
  value,
  onChange,
}: {
  id: string
  value: MemberRole
  onChange: (role: MemberRole) => void
}) {
  return (
    <Select value={value} onValueChange={(next) => onChange(next as MemberRole)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {ROLES.map((role) => (
          <SelectItem key={role.value} value={role.value}>
            <span className="flex flex-col items-start gap-0.5">
              <span>{role.label}</span>
              <span className="text-[12px] text-muted-foreground">{role.description}</span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export default function MembrosPage() {
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [createRole, setCreateRole] = useState<MemberRole>("atendente")
  const [editing, setEditing] = useState<MemberDetail | null>(null)
  const [editRole, setEditRole] = useState<MemberRole>("atendente")
  const [editActive, setEditActive] = useState(true)
  const [resetting, setResetting] = useState<MemberDetail | null>(null)

  const currentUserId = session?.user.id ?? null

  const {
    data: members,
    isLoading,
    isLoadingError,
  } = useQuery({
    queryKey: MEMBERS_KEY,
    queryFn: listMembersAdmin,
    // Sem as 3 tentativas do padrao: /membros e alcancavel por URL para quem nao
    // e admin, e ali o 403 e resposta definitiva, nao falha passageira. Com o
    // retry, a tabela ficava uns 7 segundos dizendo "Carregando membros..." para
    // quem nunca vai carregar nada.
    retry: false,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: MEMBERS_KEY })

  const createMutation = useMutation({
    mutationFn: createMember,
    onSuccess: (member) => {
      invalidate()
      onCreateOpenChange(false)
      toast.success(`${member.name} agora tem acesso a este tenant`)
    },
    onError: (error) => toast.error(createErrorMessage(error)),
  })

  const updateMutation = useMutation({
    mutationFn: ({ userId, role, active }: { userId: string; role: MemberRole; active: boolean }) =>
      updateMember(userId, { role, active }),
    onSuccess: () => {
      invalidate()
      setEditing(null)
      toast.success("Acesso atualizado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const resetMutation = useMutation({
    mutationFn: ({ userId, password }: { userId: string; password: string }) =>
      resetMemberPassword(userId, password),
    onSuccess: () => {
      setResetting(null)
      toast.success("Senha redefinida")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onCreateOpenChange(open: boolean) {
    setCreateOpen(open)
    if (!open) setCreateRole("atendente")
  }

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    // Nome e senha vao em TODA requisicao, sem ramo que os omita: o use case
    // exige os dois inclusive quando o email ja existe na plataforma e ele vai
    // descartar ambos. Ver o comentario de createMember em lib/members.ts.
    createMutation.mutate({
      name: String(form.get("name")).trim(),
      email: String(form.get("email")).trim(),
      password: String(form.get("password")),
      role: createRole,
    })
  }

  function onEditingChange(member: MemberDetail | null) {
    setEditing(member)
    if (member) {
      setEditRole(member.role)
      setEditActive(member.active)
    }
  }

  function onEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing) return
    updateMutation.mutate({ userId: editing.id, role: editRole, active: editActive })
  }

  function onReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!resetting) return
    const form = new FormData(event.currentTarget)
    resetMutation.mutate({ userId: resetting.id, password: String(form.get("password")) })
  }

  const rows = members ?? []
  const editDirty = editing != null && (editRole !== editing.role || editActive !== editing.active)

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-xl font-bold text-accent-foreground">Membros</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Quem tem acesso a este tenant e o que cada um pode fazer
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={onCreateOpenChange}>
          <DialogTrigger asChild>
            <Button>
              <Plus size={20} strokeWidth={1.5} />
              Novo membro
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo membro</DialogTitle>
              <DialogDescription>
                Defina o acesso e o papel de quem vai usar o SAC neste tenant.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={onCreate} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="membro-nome">Nome</Label>
                <Input id="membro-nome" name="name" required autoComplete="off" />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="membro-email">Email</Label>
                <Input
                  id="membro-email"
                  name="email"
                  type="email"
                  className="font-mono"
                  required
                  autoComplete="off"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="membro-papel">Papel</Label>
                <RoleSelect id="membro-papel" value={createRole} onChange={setCreateRole} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="membro-senha">Senha</Label>
                <Input
                  id="membro-senha"
                  name="password"
                  type="password"
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                  autoComplete="new-password"
                  aria-describedby="membro-senha-ajuda"
                />
                <p id="membro-senha-ajuda" className="text-[12.5px] text-muted-foreground">
                  Ao menos {MIN_PASSWORD_LENGTH} caracteres.
                </p>
              </div>
              <Button type="submit" disabled={createMutation.isPending} className="mt-1">
                Cadastrar membro
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="px-3">Nome</TableHead>
              <TableHead className="px-3">Email</TableHead>
              <TableHead className="px-3">Papel</TableHead>
              <TableHead className="px-3">Vinculo</TableHead>
              <TableHead className="w-56 px-3 text-right">Acoes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="px-3 text-center text-muted-foreground">
                  Carregando membros...
                </TableCell>
              </TableRow>
            ) : isLoadingError ? (
              <TableRow>
                <TableCell colSpan={5} className="px-3 text-center text-muted-foreground">
                  Nao foi possivel carregar os membros. Recarregue a pagina para tentar de novo.
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="px-3 text-center text-muted-foreground">
                  Nenhum membro neste tenant
                </TableCell>
              </TableRow>
            ) : (
              rows.map((member) => {
                const isSelf = member.id === currentUserId
                return (
                  <TableRow key={member.id}>
                    <TableCell className="px-3">
                      <span className="flex items-center gap-2">
                        {member.name}
                        {isSelf && (
                          <Badge variant="secondary" className="font-normal">
                            voce
                          </Badge>
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="px-3 font-mono text-[13px]">{member.email}</TableCell>
                    <TableCell className="px-3">{roleLabel(member.role)}</TableCell>
                    <TableCell className="px-3">
                      <span className="flex items-center gap-2">
                        <Badge variant="outline">{member.active ? "ativo" : "inativo"}</Badge>
                        {/* A conta global desativada vence o vinculo: o membro
                            aparece ativo aqui e ainda assim nao entra. So o super
                            admin da plataforma reverte, entao o aviso e
                            informativo — nao ha acao para o admin do tenant. */}
                        {!member.user_active && (
                          <span className="text-[12.5px] text-muted-foreground">
                            conta suspensa na plataforma
                          </span>
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="px-3 text-right">
                      {isSelf ? (
                        // Espelha a salvaguarda do backend em vez de deixar o
                        // clique cair num conflito garantido: ninguem altera o
                        // proprio vinculo nem a propria senha por aqui.
                        <span className="text-[12.5px] text-muted-foreground">sem acoes</span>
                      ) : (
                        <span className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onEditingChange(member)}
                            aria-label={`Alterar acesso de ${member.name}`}
                          >
                            <Pencil size={16} strokeWidth={1.5} />
                            Alterar acesso
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setResetting(member)}
                            aria-label={`Redefinir senha de ${member.name}`}
                          >
                            <KeyRound size={16} strokeWidth={1.5} />
                            Senha
                          </Button>
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>

      <p className="text-[12.5px] text-muted-foreground">
        Voce nao altera o proprio papel, o proprio vinculo nem a propria senha por esta tela. Peca a
        outro administrador do tenant.
      </p>

      <Dialog open={editing != null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Alterar acesso de {editing?.name}</DialogTitle>
            <DialogDescription className="font-mono">{editing?.email}</DialogDescription>
          </DialogHeader>
          {editing && (
            <form onSubmit={onEdit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="membro-editar-papel">Papel</Label>
                <RoleSelect id="membro-editar-papel" value={editRole} onChange={setEditRole} />
              </div>
              <div className="flex items-start justify-between gap-6 rounded-md border border-border px-3 py-3">
                <div className="min-w-0">
                  <Label htmlFor="membro-editar-ativo">Vinculo ativo</Label>
                  <p className="mt-1 text-[12.5px] text-muted-foreground">
                    Desativado, o membro deixa de entrar neste tenant e o historico dele continua
                    nos tickets.
                  </p>
                </div>
                <Switch
                  id="membro-editar-ativo"
                  checked={editActive}
                  onCheckedChange={setEditActive}
                  className="mt-0.5"
                />
              </div>
              <Button
                type="submit"
                disabled={updateMutation.isPending || !editDirty}
                className="mt-1"
              >
                Salvar alteracoes
              </Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={resetting != null} onOpenChange={(open) => !open && setResetting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Redefinir senha de {resetting?.name}</DialogTitle>
            <DialogDescription>
              A senha atual para de valer assim que voce salvar. Combine a nova com o membro.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onReset} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="membro-nova-senha">Nova senha</Label>
              <Input
                id="membro-nova-senha"
                name="password"
                type="password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                autoComplete="new-password"
                aria-describedby="membro-nova-senha-ajuda"
              />
              <p id="membro-nova-senha-ajuda" className="text-[12.5px] text-muted-foreground">
                Ao menos {MIN_PASSWORD_LENGTH} caracteres.
              </p>
            </div>
            <Button type="submit" disabled={resetMutation.isPending} className="mt-1">
              Redefinir senha
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  )
}
