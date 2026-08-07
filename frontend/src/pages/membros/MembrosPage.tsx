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
import { FieldError } from "@/components/ui/field-error"
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
import { fieldErrorProps } from "@/lib/field-error"
import {
  createMember,
  listMembersAdmin,
  resetMemberPassword,
  updateMember,
  type MemberDetail,
  type MemberRole,
} from "@/lib/members"
import { isValidEmail, MIN_PASSWORD_LENGTH } from "@/lib/validation"

const MEMBERS_KEY = ["membros-gerencia"]

/** A descricao de cada papel fica no seletor, e nao numa coluna da tabela: ela
 *  muda uma decisao no momento em que o admin escolhe, e repetida em toda linha
 *  viraria ruido. Os textos espelham ROLE_PERMISSIONS do backend. */
const ROLES: { value: MemberRole; label: string; description: string }[] = [
  {
    value: "admin",
    label: "Administrador",
    description: "Tudo do supervisor, mais a gestão dos membros deste tenant.",
  },
  {
    value: "supervisor",
    label: "Supervisor",
    description: "Vê e decide qualquer ticket e gerencia todos os cadastros.",
  },
  {
    value: "atendente",
    label: "Atendente",
    description: "Cria e atende os próprios tickets; não decide nem vê os dos outros.",
  },
  {
    value: "visualizador",
    label: "Visualizador",
    description: "Só consulta: vê todos os tickets, sem alterar nada.",
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
    return "Não foi possível cadastrar este email neste tenant. Confira o endereço ou peça o vínculo ao administrador da plataforma."
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
      {/* O SelectValue leva filho de proposito: sem filho nenhum, o Radix portala
       *  os filhos INTEIROS do item selecionado para dentro do trigger (dist/index.mjs,
       *  `hasChildren = children !== void 0` e o portal condicionado a
       *  `!valueNodeHasChildren`), o que arrastaria a descricao de 12px para dentro dos
       *  36px do trigger. A descricao serve a escolha, no menu aberto; fechado vale so
       *  o rotulo. */}
      <SelectTrigger id={id} className="w-full">
        <SelectValue>{roleLabel(value)}</SelectValue>
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

function CreateMemberForm({
  role,
  onRoleChange,
  onSubmit,
  submitting,
}: {
  role: MemberRole
  onRoleChange: (role: MemberRole) => void
  onSubmit: (values: { name: string; email: string; password: string }) => void
  submitting: boolean
}) {
  const [nameError, setNameError] = useState<string | null>(null)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const name = String(form.get("name")).trim()
    const email = String(form.get("email")).trim()
    const password = String(form.get("password"))

    const nextNameError = name ? null : "Informe o nome"
    const nextEmailError = !email
      ? "Informe o email"
      : !isValidEmail(email)
        ? "Informe um email válido, com @ e domínio (ex.: nome@empresa.com)"
        : null
    const nextPasswordError = !password
      ? "Informe a senha"
      : password.length < MIN_PASSWORD_LENGTH
        ? `A senha precisa ter ao menos ${MIN_PASSWORD_LENGTH} caracteres`
        : null
    setNameError(nextNameError)
    setEmailError(nextEmailError)
    setPasswordError(nextPasswordError)
    if (nextNameError || nextEmailError || nextPasswordError) return

    onSubmit({ name, email, password })
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="membro-nome">Nome</Label>
        <Input
          id="membro-nome"
          name="name"
          required
          autoComplete="off"
          {...fieldErrorProps("membro-nome", nameError)}
        />
        <FieldError fieldId="membro-nome" message={nameError} />
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
          {...fieldErrorProps("membro-email", emailError)}
        />
        <FieldError fieldId="membro-email" message={emailError} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="membro-papel">Papel</Label>
        <RoleSelect id="membro-papel" value={role} onChange={onRoleChange} />
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
          aria-invalid={passwordError != null}
          aria-describedby={passwordError ? "membro-senha-error" : "membro-senha-ajuda"}
        />
        {passwordError ? (
          <FieldError fieldId="membro-senha" message={passwordError} />
        ) : (
          <p id="membro-senha-ajuda" className="text-[12.5px] text-muted-foreground">
            Ao menos {MIN_PASSWORD_LENGTH} caracteres.
          </p>
        )}
      </div>
      <Button type="submit" disabled={submitting} className="mt-1">
        Cadastrar membro
      </Button>
    </form>
  )
}

function ResetPasswordForm({
  fieldId,
  onSubmit,
  submitting,
}: {
  fieldId: string
  onSubmit: (password: string) => void
  submitting: boolean
}) {
  const [passwordError, setPasswordError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const password = String(form.get("password"))
    const nextError = !password
      ? "Informe a senha"
      : password.length < MIN_PASSWORD_LENGTH
        ? `A senha precisa ter ao menos ${MIN_PASSWORD_LENGTH} caracteres`
        : null
    setPasswordError(nextError)
    if (nextError) return
    onSubmit(password)
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor={fieldId}>Nova senha</Label>
        <Input
          id={fieldId}
          name="password"
          type="password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          autoComplete="new-password"
          aria-invalid={passwordError != null}
          aria-describedby={passwordError ? `${fieldId}-error` : `${fieldId}-ajuda`}
        />
        {passwordError ? (
          <FieldError fieldId={fieldId} message={passwordError} />
        ) : (
          <p id={`${fieldId}-ajuda`} className="text-[12.5px] text-muted-foreground">
            Ao menos {MIN_PASSWORD_LENGTH} caracteres.
          </p>
        )}
      </div>
      <Button type="submit" disabled={submitting} className="mt-1">
        Redefinir senha
      </Button>
    </form>
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
  const [resetTarget, setResetTarget] = useState<MemberDetail | null>(null)

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
      setResetTarget(null)
      toast.success("Senha redefinida")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onCreateOpenChange(open: boolean) {
    setCreateOpen(open)
    if (!open) setCreateRole("atendente")
  }

  function onCreate(values: { name: string; email: string; password: string }) {
    // Nome e senha vao em TODA requisicao, sem ramo que os omita: o use case
    // exige os dois inclusive quando o email ja existe na plataforma e ele vai
    // descartar ambos. Ver o comentario de createMember em lib/members.ts.
    createMutation.mutate({ ...values, role: createRole })
  }

  function openEdit(member: MemberDetail) {
    setEditing(member)
    setEditRole(member.role)
    setEditActive(member.active)
  }

  function onEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing) return
    updateMutation.mutate({ userId: editing.id, role: editRole, active: editActive })
  }

  function onReset(password: string) {
    if (!resetTarget) return
    resetMutation.mutate({ userId: resetTarget.id, password })
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
            <CreateMemberForm
              role={createRole}
              onRoleChange={setCreateRole}
              onSubmit={onCreate}
              submitting={createMutation.isPending}
            />
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
              <TableHead className="px-3">Vínculo</TableHead>
              <TableHead className="w-56 px-3 text-right">Ações</TableHead>
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
                  Não foi possível carregar os membros. Recarregue a página para tentar de novo.
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
                            você
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
                        <span className="text-[12.5px] text-muted-foreground">sem ações</span>
                      ) : (
                        <span className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openEdit(member)}
                            aria-label={`Alterar acesso de ${member.name}`}
                          >
                            <Pencil size={16} strokeWidth={1.5} />
                            Alterar acesso
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setResetTarget(member)}
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
        Você não altera o próprio papel, o próprio vínculo nem a própria senha por esta tela. Peça a
        outro administrador do tenant.
      </p>

      <Dialog open={editing != null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Alterar acesso de {editing?.name}</DialogTitle>
            <DialogDescription className="font-mono">{editing?.email}</DialogDescription>
          </DialogHeader>
          {editing && (
            <form onSubmit={onEdit} noValidate className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="membro-editar-papel">Papel</Label>
                <RoleSelect id="membro-editar-papel" value={editRole} onChange={setEditRole} />
              </div>
              <div className="flex items-start justify-between gap-6 rounded-md border border-border px-3 py-3">
                <div className="min-w-0">
                  <Label htmlFor="membro-editar-ativo">Vínculo ativo</Label>
                  <p className="mt-1 text-[12.5px] text-muted-foreground">
                    Desativado, o membro deixa de entrar neste tenant e o histórico dele continua
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
                Salvar alterações
              </Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={resetTarget != null} onOpenChange={(open) => !open && setResetTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Redefinir senha de {resetTarget?.name}</DialogTitle>
            <DialogDescription>
              A senha atual para de valer assim que você salvar. Combine a nova com o membro.
            </DialogDescription>
          </DialogHeader>
          <ResetPasswordForm
            fieldId="membro-nova-senha"
            onSubmit={onReset}
            submitting={resetMutation.isPending}
          />
        </DialogContent>
      </Dialog>
    </section>
  )
}
