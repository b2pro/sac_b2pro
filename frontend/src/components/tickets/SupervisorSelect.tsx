import { useQuery } from "@tanstack/react-query"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { listMembers, type Member } from "@/lib/members"

const SEM_SUPERVISOR = "nenhum"

function labelFor(member: Member): string {
  // Um membro inativo continua rotulado como tal, nunca some silenciosamente
  // da lista quando ele e o valor ja atribuido (ver options abaixo).
  const papel = member.active ? member.role : `${member.role}, inativo`
  return `${member.name} (${papel})`
}

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

  const elegiveis = (members ?? []).filter(
    (member) => (member.role === "admin" || member.role === "supervisor") && member.active,
  )

  // Um ticket pode ja ter um supervisor atribuido que virou inativo (ou teve
  // o papel trocado) depois da atribuicao. Ele nao entra no filtro acima, mas
  // precisa continuar aparecendo como opcao — senao o campo mostraria
  // silenciosamente "Sem supervisor" para um ticket que tem supervisor, e
  // salvar o formulario sem tocar neste campo apagaria a atribuicao por
  // engano. Ele so entra na lista quando e o valor atual: nao aparece como
  // opcao escolhivel para um ticket diferente.
  const atualForaDaLista = value ? members?.find((m) => m.id === value) : undefined
  const jaListado = elegiveis.some((m) => m.id === value)
  const supervisors =
    atualForaDaLista && !jaListado ? [...elegiveis, atualForaDaLista] : elegiveis

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
            {labelFor(member)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
