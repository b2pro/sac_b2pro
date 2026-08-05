import { useQuery } from "@tanstack/react-query"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { listMembers, type Member } from "@/lib/members"

function labelFor(member: Member): string {
  // Mesma regra do SupervisorSelect: um atendente inativo continua rotulado
  // como tal, nunca some silenciosamente da lista quando ele e o valor ja
  // atribuido (ver options abaixo).
  const papel = member.active ? member.role : `${member.role}, inativo`
  return `${member.name} (${papel})`
}

/** Seletor de atendente responsavel do ticket, usado so no dialog de editar
 *  dados: reatribuir exige EDITAR_QUALQUER_TICKET no backend, entao quem
 *  chega ate este campo ja e admin ou supervisor (ver `canDecide` em
 *  `lib/tickets`). Nunca oferece "nenhum" -- enviar attendant_user_id nulo e
 *  um no-op no backend, nao uma remocao de atribuicao, e todo ticket sempre
 *  tem um atendente. */
export function AttendantSelect({
  id,
  value,
  onChange,
}: {
  id: string
  value: string
  onChange: (value: string) => void
}) {
  const { data: members } = useQuery({
    queryKey: ["membros"],
    queryFn: listMembers,
    retry: false,
  })

  const elegiveis = (members ?? []).filter(
    (member) =>
      member.active &&
      (member.role === "admin" || member.role === "supervisor" || member.role === "atendente"),
  )

  // O atendente atual pode ter ficado inativo, ou trocado de papel, depois da
  // atribuicao. Ele nao entra no filtro acima, mas precisa continuar
  // aparecendo como opcao -- senao abrir e fechar o select sem tocar nele
  // trocaria o atendente do ticket por engano.
  const atualForaDaLista = members?.find((m) => m.id === value)
  const jaListado = elegiveis.some((m) => m.id === value)
  const atendentes = atualForaDaLista && !jaListado ? [...elegiveis, atualForaDaLista] : elegiveis

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {atendentes.map((member) => (
          <SelectItem key={member.id} value={member.id}>
            {labelFor(member)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
