import { useQuery } from "@tanstack/react-query"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { listMembers } from "@/lib/members"

const SEM_SUPERVISOR = "nenhum"

/** Seletor de supervisor do ticket: usado na criacao e no dialog de editar
 *  dados. Centraliza aqui a busca dos membros e o filtro por papel para nao
 *  duplicar essa logica nos dois lugares. GET /membros exige poder criar ou
 *  editar ticket — quem chega ate este seletor ja tem essa permissao, mas se
 *  a chamada falhar mesmo assim (ex.: 403), o erro fica so na query: o
 *  seletor apenas nao lista opcoes, sem travar o resto do formulario. */
export function SupervisorSelect({
  id,
  value,
  onChange,
}: {
  id: string
  value: string | null
  onChange: (value: string | null) => void
}) {
  const { data: members } = useQuery({
    queryKey: ["membros"],
    queryFn: listMembers,
    retry: false,
  })

  const supervisors = (members ?? []).filter(
    (member) => member.role === "admin" || member.role === "supervisor",
  )

  return (
    <Select
      value={value ?? SEM_SUPERVISOR}
      onValueChange={(next) => onChange(next === SEM_SUPERVISOR ? null : next)}
    >
      <SelectTrigger id={id} className="w-full">
        <SelectValue placeholder="Sem supervisor" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={SEM_SUPERVISOR}>Sem supervisor</SelectItem>
        {supervisors.map((member) => (
          <SelectItem key={member.id} value={member.id}>
            {`${member.name} (${member.role})`}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
